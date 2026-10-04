"""Container entrypoint: supervise independent web and AI worker process groups."""

import os
import signal
import subprocess
import sys
import time


def supervise(commands, grace_seconds):
    stopping = False
    children = []

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    exit_code = 0
    try:
        for command in commands:
            children.append(subprocess.Popen(command, start_new_session=True))
        while not stopping:
            exited = next((child for child in children if child.poll() is not None), None)
            if exited:
                exit_code = exited.returncode or 1
                break
            time.sleep(0.2)
    finally:
        for child in children:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + grace_seconds
        for child in children:
            try:
                child.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return exit_code


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.conf import settings

    commands = [
        [
            sys.executable,
            "-m",
            "gunicorn",
            "--config",
            "gunicorn.conf.py",
            "config.wsgi:application",
        ]
    ]
    if not settings.GRAIDER_AI_JOBS_ENABLED:
        os.execv(sys.executable, commands[0])
    if settings.GRAIDER_AI_JOBS_ENABLED:
        commands.insert(0, [sys.executable, "manage.py", "run_ai_worker"])
    return supervise(commands, settings.GRAIDER_AI_DRAIN_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
