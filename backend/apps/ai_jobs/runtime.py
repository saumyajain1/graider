"""Local notifications only: no timer touches PostgreSQL while the worker is idle."""

import logging
import os
import signal
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError, close_old_connections, connection, connections

from .engine import claim_next, heartbeat, run_claim
from .models import AIJob, JobState

logger = logging.getLogger(__name__)


def notify_worker():
    if not settings.GRAIDER_AI_JOBS_ENABLED:
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(settings.GRAIDER_AI_WAKE_SOCKET)
            client.sendall(b"wake")
            return client.recv(16) == b"ready"
    except OSError:
        return False


class Worker:
    def __init__(self, *, runner=run_claim):
        self.runner = runner
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.ready = False
        self.futures = {}
        self.listener = None
        self.listener_thread = None
        self.pool = None
        self.last_heartbeat = time.monotonic()
        self.parallelism = 1 if connection.vendor == "sqlite" else settings.GRAIDER_AI_CONCURRENCY

    def stop(self):
        self.stopping.set()
        self.wake.set()

    def listen(self):
        path = Path(settings.GRAIDER_AI_WAKE_SOCKET)
        if path.exists():
            # Do not remove another live process's socket, even if it reports busy.
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(1)
                try:
                    probe.connect(str(path))
                except (ConnectionRefusedError, FileNotFoundError):
                    path.unlink(missing_ok=True)
                else:
                    raise RuntimeError("An AI worker already owns this wake socket.")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        os.chmod(path, 0o600)
        listener.listen(16)
        listener.settimeout(0.5)
        self.listener = listener

        def receive():
            while not self.stopping.is_set():
                try:
                    client, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with client:
                    client.settimeout(1)
                    try:
                        if client.recv(16) == b"wake":
                            self.wake.set()
                        client.sendall(b"ready" if self.ready else b"busy")
                    except OSError:
                        pass

        self.listener_thread = threading.Thread(target=receive, daemon=True)
        self.listener_thread.start()

    def _execute(self, claim):
        close_old_connections()
        try:
            self.runner(*claim)
        finally:
            connections.close_all()

    def cycle(self):
        close_old_connections()
        for claim, future in list(self.futures.items()):
            if future.done():
                del self.futures[claim]
                future.result()
        if (
            self.futures
            and time.monotonic() - self.last_heartbeat >= settings.GRAIDER_AI_HEARTBEAT_SECONDS
        ):
            heartbeat(list(self.futures))
            self.last_heartbeat = time.monotonic()
        while not self.stopping.is_set() and len(self.futures) < self.parallelism:
            claim = claim_next()
            if not claim:
                break
            self.futures[claim] = self.pool.submit(self._execute, claim)
        self.ready = True
        return (
            bool(self.futures)
            or AIJob.objects.filter(
                state__in=(JobState.QUEUED, JobState.RUNNING, JobState.RETRY_WAIT)
            ).exists()
        )

    def run(self, *, once=False):
        if not settings.GRAIDER_AI_JOBS_ENABLED:
            raise RuntimeError(
                "Enable GRAIDER_AI_JOBS_ENABLED explicitly to run the staged worker."
            )
        self.pool = ThreadPoolExecutor(max_workers=self.parallelism)
        stopped_at = None
        try:
            if not once:
                self.listen()
            active = True  # Startup scan recovers committed jobs and missed notifications.
            while True:
                # Clear BEFORE scanning; a notification during the scan remains set.
                self.wake.clear()
                try:
                    active = self.cycle()
                except DatabaseError:
                    self.ready = False
                    close_old_connections()
                    logger.warning("AI worker database unavailable; retrying safely.")
                    active = True
                if self.stopping.is_set():
                    stopped_at = stopped_at or time.monotonic()
                    if (
                        not self.futures
                        or time.monotonic() - stopped_at >= settings.GRAIDER_AI_DRAIN_SECONDS
                    ):
                        break
                elif once and not active:
                    break
                if active or self.stopping.is_set():
                    self.wake.wait(
                        min(settings.GRAIDER_AI_SCAN_SECONDS, settings.GRAIDER_AI_HEARTBEAT_SECONDS)
                    )
                else:
                    # Close the persistent connection before waiting without a DB timer.
                    connections.close_all()
                    self.wake.wait()
        finally:
            self.ready = False
            self.pool.shutdown(wait=not self.futures, cancel_futures=True)
            if self.listener:
                self.listener.close()
                Path(settings.GRAIDER_AI_WAKE_SOCKET).unlink(missing_ok=True)
            connections.close_all()

    def install_signals(self):
        def stop(signum, frame):
            if self.stopping.is_set():
                os._exit(128 + signum)
            self.stop()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
