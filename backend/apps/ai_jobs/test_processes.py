"""Real process death, PostgreSQL rollback and competing worker checks."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote, urlencode
from uuid import uuid4

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.grading.models import GradingResult, LLMQuotaLock, LLMUsage
from apps.grading.services.openai_client import OPERATION_OUTPUT_CAPS, _estimate_tokens
from apps.grading.services.schemas import GeneratedReferenceAnswerSchema

from .models import AIJob, AIJobStep
from .recipes import execute_recipe
from .runtime import notify_worker
from .services import JobConflict, retry_job
from .tests import JobFixtures

HELPER = Path(__file__).resolve().parents[3] / "scripts/ai_jobs_verification/worker_process.py"


@override_settings(GRAIDER_AI_JOBS_ENABLED=True)
class ProcessRecoveryTests(JobFixtures, TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Subprocess tests require a shared disposable PostgreSQL test database.")
        super().setUp()
        LLMQuotaLock.objects.get_or_create(pk=1)
        self.temporary = tempfile.TemporaryDirectory(prefix="graider-process-check-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.children = []
        self.events = self.folder / "events.jsonl"
        self.addCleanup(self.stop_children)

    def stop_children(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            child.communicate()

    def start(self, mode="drain", fault=None, **extra_env):
        config = connection.settings_dict
        app_name = "graider-verify-" + uuid4().hex[:12]
        url = (
            f"postgresql://{quote(config['USER'])}:{quote(config['PASSWORD'])}"
            f"@{config['HOST']}:{config['PORT']}/{quote(config['NAME'])}?"
            + urlencode({"application_name": app_name})
        )
        marker = self.folder / uuid4().hex
        env = {
            **os.environ,
            "DJANGO_DEBUG": "true",
            "DJANGO_SECRET_KEY": "process-test-only-secret",
            "DATABASE_URL": url,
            "OPENAI_API_KEY": "fake-process-test-key",
            "AWS_ENDPOINT_URL_S3": "",
            "AWS_ACCESS_KEY_ID": "",
            "AWS_SECRET_ACCESS_KEY": "",
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "BREVO_API_KEY": "",
            "GRAIDER_AI_JOBS_ENABLED": "true",
            "GRAIDER_AI_CONCURRENCY": "3",
            "GRAIDER_AI_STUDENT_CONCURRENCY": "3",
            "GRAIDER_AI_SCAN_SECONDS": "1",
            "GRAIDER_VERIFY_EVENTS": str(self.events),
            "GRAIDER_VERIFY_MARKER": str(marker),
            "GRAIDER_VERIFY_DELAY": "0",
            "GRAIDER_VERIFY_SLOW_DELAY": "0",
            "GRAIDER_VERIFY_FAULT": "",
            "GRAIDER_USER_AI_REQUESTS_PER_MINUTE": "1000",
            "GRAIDER_USER_DAILY_TOKENS": "250000",
            "GRAIDER_USER_MONTHLY_TOKENS": "500000",
            "GRAIDER_GLOBAL_MONTHLY_TOKENS": "2000000",
            **extra_env,
        }
        command = [sys.executable, str(HELPER.resolve()), mode]
        if fault:
            command += ["--fault", fault]
        child = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.children.append(child)
        return child, marker, app_name

    def wait_until(self, condition, child=None):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if condition():
                return
            if child and child.poll() is not None:
                self.fail(child.communicate()[1].decode())
            time.sleep(0.02)
        self.fail("Timed out waiting for subprocess verification boundary.")

    def done(self, child):
        output, error = child.communicate(timeout=30)
        self.assertEqual(child.returncode, 0, error.decode())
        self.assertTrue(json.loads(output)["finished"])

    def run_process(self, mode="drain", **env):
        child, _, _ = self.start(mode, **env)
        self.done(child)

    def crash(self, fault, mode="single"):
        child, marker, _ = self.start(mode, fault)
        self.wait_until(marker.exists, child)
        child.kill()
        child.wait(timeout=5)
        self.assertLess(child.returncode, 0)
        return marker

    def expire(self):
        AIJobStep.objects.filter(state="running").update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )

    def starts(self):
        if not self.events.exists():
            return []
        return [
            json.loads(line)
            for line in self.events.read_text().splitlines()
            if json.loads(line)["event"] == "start"
        ]

    def assert_complete(self, job, calls, questions=1):
        job.refresh_from_db()
        self.assertEqual(job.state, "succeeded")
        self.assertEqual(len(self.starts()), calls)
        self.assertEqual(GradingResult.objects.count(), questions)
        self.assertEqual(LLMUsage.objects.count(), calls)
        self.assertFalse(LLMUsage.objects.filter(status="pending").exists())

    def test_mapping_response_survives_sigkill_before_checkpoint(self):
        self.make_question("Q2")
        job = self.enqueue()
        self.crash("response")
        self.assertTrue(job.steps.get(key="map").attempts.get().output)
        self.assertFalse(GradingResult.objects.exists())
        self.expire()
        self.run_process()
        self.assert_complete(job, 3, questions=2)

    def test_question_response_survives_sigkill_and_keeps_mapping_checkpoint(self):
        self.make_question("Q2")
        job = self.enqueue()
        self.run_process("single")
        self.crash("checkpoint")
        self.expire()
        self.run_process()
        self.assert_complete(job, 3, questions=2)
        self.assertEqual(job.steps.get(key="map").attempts.count(), 1)

    def test_sigkill_during_publication_rolls_back_all_student_results(self):
        self.make_question("Q2")
        job = self.enqueue()
        for _ in range(3):
            self.run_process("single")
        child, marker, _ = self.start("publish", "publication")
        self.wait_until(marker.exists, child)
        self.assertFalse(GradingResult.objects.exists())
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.grading_status, "pending")
        child.kill()
        child.wait(timeout=5)
        self.assertFalse(GradingResult.objects.exists())
        self.run_process("publish")
        self.assert_complete(job, 3, questions=2)

    def test_restart_after_committed_publication_does_not_repeat_ai(self):
        job = self.enqueue()
        self.run_process("single")
        self.run_process("single")
        self.crash("published", "publish")
        self.assert_complete(job, 2)
        self.run_process()
        self.assert_complete(job, 2)

    def test_sigkill_after_dispatch_pauses_and_requires_billing_confirmation(self):
        job = self.enqueue()
        self.crash("dispatch")
        self.expire()
        self.run_process()
        job.refresh_from_db()
        self.assertEqual(job.state, "needs_attention")
        self.assertEqual(len(self.starts()), 1)
        usage = LLMUsage.objects.get()
        self.assertEqual(usage.status, "uncertain")
        self.assertGreater(usage.reserved_tokens, 0)
        with self.assertRaises(JobConflict):
            retry_job(owner=self.owner, job_id=job.id)
        retry_job(owner=self.owner, job_id=job.id, confirm_possible_charge=True)
        self.run_process()
        self.assert_complete(job, 3)
        usage.refresh_from_db()
        self.assertEqual(usage.status, "uncertain")

    def test_expired_live_process_cannot_overwrite_a_successor(self):
        job = self.enqueue()
        child, marker, _ = self.start("single", "claim")
        self.wait_until(marker.exists, child)
        self.expire()
        self.run_process()
        self.assert_complete(job, 2)
        Path(str(marker) + ".release").touch()
        self.done(child)
        self.assert_complete(job, 2)

    def test_real_database_disconnect_after_dispatch_does_not_repeat_request(self):
        job = self.enqueue()
        child, marker, _ = self.start("single", "dispatch")
        self.wait_until(marker.exists, child)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_terminate_backend(%s)", [int(marker.read_text())])
            self.assertTrue(cursor.fetchone()[0])
        Path(str(marker) + ".release").touch()
        child.communicate(timeout=20)
        self.assertNotEqual(child.returncode, 0)
        self.expire()
        self.run_process()
        job.refresh_from_db()
        self.assertEqual(job.state, "needs_attention")
        self.assertEqual(LLMUsage.objects.get().status, "uncertain")
        self.assertEqual(len(self.starts()), 1)
        self.assertFalse(GradingResult.objects.exists())

    def test_competing_processes_obey_global_three_call_limit(self):
        for index in range(2, 5):
            self.make_question(f"Q{index}")
        for question in self.assignment.question_parts.filter(part_type="question"):
            self.enqueue(
                "reference_answers",
                options={"question_part_id": question.id, "replace_existing": True},
            )
        holders = []
        for _ in range(3):
            child, marker, _ = self.start("single", "claim")
            self.wait_until(marker.exists, child)
            holders.append((child, marker))
        self.run_process("single")
        self.assertEqual(AIJobStep.objects.filter(state="running").count(), 3)
        self.assertFalse(self.starts())
        for child, marker in holders:
            Path(str(marker) + ".release").touch()
        for child, _ in holders:
            self.done(child)
        self.run_process()
        self.assertEqual(len(self.starts()), 4)
        self.assertFalse(
            AIJob.objects.filter(assignment=self.assignment).exclude(state="succeeded").exists()
        )

    def test_cross_process_quota_reservation_blocks_an_overlapping_request(self):
        second = self.make_question("Q2")
        first_job = self.enqueue(
            "reference_answers",
            options={"question_part_id": self.question.id, "replace_existing": True},
        )
        second_job = self.enqueue(
            "reference_answers", options={"question_part_id": second.id, "replace_existing": True}
        )
        captured = {}

        class Capture:
            def parse(self, **kwargs):
                captured.update(kwargs)
                return GeneratedReferenceAnswerSchema(answer_text="4")

        execute_recipe(first_job.steps.get(), Capture())
        allowance = _estimate_tokens(
            captured["system_prompt"],
            captured["user_prompt"],
            captured["response_format"],
            min(settings.GRAIDER_MAX_OUTPUT_TOKENS, OPERATION_OUTPUT_CAPS[captured["operation"]]),
        )
        child, marker, _ = self.start(
            "single", "dispatch", GRAIDER_GLOBAL_MONTHLY_TOKENS=str(allowance)
        )
        self.wait_until(marker.exists, child)
        self.run_process("single", GRAIDER_GLOBAL_MONTHLY_TOKENS=str(allowance))
        second_job.refresh_from_db()
        self.assertEqual(second_job.state, "paused_quota")
        self.assertEqual(LLMUsage.objects.count(), 1)
        Path(str(marker) + ".release").touch()
        self.done(child)
        self.run_process()
        retry_job(owner=self.owner, job_id=second_job.id)
        self.run_process()
        first_job.refresh_from_db()
        second_job.refresh_from_db()
        self.assertEqual((first_job.state, second_job.state), ("succeeded", "succeeded"))
        self.assertEqual(len(self.starts()), 2)

    def test_duplicate_notifications_do_not_duplicate_work_and_idle_worker_disconnects(self):
        job = self.enqueue("reference_answers", options={"replace_existing": True})
        socket = str(self.folder / "wake.sock")
        child, _, app_name = self.start(
            "worker", GRAIDER_AI_WAKE_SOCKET=socket, GRAIDER_VERIFY_DELAY="0.2"
        )
        with override_settings(GRAIDER_AI_WAKE_SOCKET=socket):
            self.wait_until(notify_worker, child)
            for _ in range(12):
                self.assertTrue(notify_worker())
            self.wait_until(lambda: type(job).objects.get(pk=job.id).state == "succeeded", child)

        def disconnected():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s", [app_name]
                )
                return cursor.fetchone()[0] == 0

        self.wait_until(disconnected, child)
        scans = sum(
            json.loads(line)["event"] == "scan" for line in self.events.read_text().splitlines()
        )
        time.sleep(1.2)  # Cover an active scan interval with no further notifications.
        self.assertTrue(disconnected())
        self.assertEqual(
            sum(
                json.loads(line)["event"] == "scan" for line in self.events.read_text().splitlines()
            ),
            scans,
            "Idle work must not open and close connections just to scan the queue.",
        )
        self.assertIsNone(child.poll())
        self.assertEqual(len(self.starts()), 1)


class LocalPersistenceTests(SimpleTestCase):
    def test_sqlite_upload_and_saved_response_survive_process_death(self):
        with tempfile.TemporaryDirectory(prefix="graider-local-process-") as directory:
            folder = Path(directory)
            database = folder / "jobs.sqlite3"
            marker = folder / "response-saved"
            events = folder / "events.jsonl"
            env = {
                **os.environ,
                "DJANGO_DEBUG": "true",
                "DJANGO_SECRET_KEY": "local-process-test-only",
                "DATABASE_URL": "sqlite:///" + str(database),
                "OPENAI_API_KEY": "fake-local-test-key",
                "AWS_ENDPOINT_URL_S3": "",
                "AWS_ACCESS_KEY_ID": "",
                "AWS_SECRET_ACCESS_KEY": "",
                "GOOGLE_CLIENT_ID": "",
                "GOOGLE_CLIENT_SECRET": "",
                "BREVO_API_KEY": "",
                "GRAIDER_AI_JOBS_ENABLED": "true",
                "GRAIDER_VERIFY_EVENTS": str(events),
                "GRAIDER_VERIFY_MARKER": str(marker),
                "GRAIDER_VERIFY_MEDIA_ROOT": str(folder / "media"),
                "GRAIDER_VERIFY_FAULT": "",
                "GRAIDER_VERIFY_DELAY": "0",
                "GRAIDER_VERIFY_SLOW_DELAY": "0",
            }
            migrated = subprocess.run(
                [sys.executable, str(settings.BASE_DIR / "manage.py"), "migrate", "--noinput"],
                env=env,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(migrated.returncode, 0, migrated.stderr.decode())

            def run(mode):
                result = subprocess.run(
                    [sys.executable, str(HELPER.resolve()), mode],
                    env=env,
                    capture_output=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertTrue(json.loads(result.stdout)["finished"])

            run("seed-local")
            child = subprocess.Popen(
                [sys.executable, str(HELPER.resolve()), "single", "--fault", "response"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                deadline = time.monotonic() + 20
                while not marker.exists() and time.monotonic() < deadline:
                    if child.poll() is not None:
                        self.fail(child.communicate()[1].decode())
                    time.sleep(0.02)
                self.assertTrue(marker.exists())
                child.kill()
                child.wait(timeout=5)
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)
            with sqlite3.connect(database) as local:
                local.execute(
                    "UPDATE ai_jobs_aijobstep SET lease_expires_at='2000-01-01 00:00:00' WHERE state='running'"
                )
            run("drain")
            run("verify-local")
            run("drain")
            run("verify-local")
            starts = [
                json.loads(line)
                for line in events.read_text().splitlines()
                if json.loads(line)["event"] == "start"
            ]
            self.assertEqual(len(starts), 1)
