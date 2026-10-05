import os
import socket
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from django.conf import settings
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from openai import APIConnectionError, RateLimitError
from rest_framework.test import APIClient

from apps.grading.models import GradingResult, LLMQuotaLock, LLMUsage
from apps.grading.services.schemas import (
    GeneratedQuestionGradeSchema,
    GeneratedQuestionSetSchema,
    GeneratedReferenceAnswerSchema,
    GeneratedRubricSchema,
    SubmissionAnswerMappingSchema,
)

from .accounting import AttemptAccounting, RecipeService
from .engine import claim_next, heartbeat, run_claim
from .models import AIJob, AIJobAttempt, AIJobStep, JobState
from .recipes import execute_recipe
from .runtime import Worker, notify_worker
from .services import JobConflict, cancel_job, retry_job
from .tests import JobFixtures


@override_settings(GRAIDER_AI_JOBS_ENABLED=True)
class ExecutionTests(JobFixtures, TransactionTestCase):
    def setUp(self):
        super().setUp()
        LLMQuotaLock.objects.get_or_create(pk=1)
        self.context.parent_key = "shared"
        self.context.save()
        self.calls, self.callback = [], None
        self.provider_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=self.provider))
        )

    def provider(self, **kwargs):
        self.assertFalse(connection.in_atomic_block)
        self.calls.append(kwargs)
        if self.callback:
            self.callback(kwargs)
        schema = kwargs["response_format"]
        if schema == SubmissionAnswerMappingSchema:
            output = {
                "answers": [
                    {
                        "part_key": q.part_key,
                        "extracted_answer_text": "2+2=4",
                        "mapping_confidence": 0.9,
                    }
                    for q in self.assignment.question_parts.filter(part_type="question")
                ]
            }
        elif schema == GeneratedQuestionGradeSchema:
            output = {
                "criteria": [
                    {
                        "criterion_id": c.id,
                        "score": float(c.max_points) - 1,
                        "feedback": "Evidence-based deduction",
                    }
                    for c in self.question.rubric_criteria.all()
                ],
                "feedback": "Overall feedback",
                "reasoning_summary": "Used reference and rubric",
                "confidence_score": 0.8,
                "needs_review": True,
            }
        elif schema == GeneratedReferenceAnswerSchema:
            output = {"answer_text": "New model answer"}
        elif schema == GeneratedRubricSchema:
            output = {
                "criteria": [
                    {
                        "title": "New criterion",
                        "description": "Concrete assessment",
                        "max_points": 5,
                    }
                ]
            }
        elif schema == GeneratedQuestionSetSchema:
            output = {
                "parts": [
                    {
                        "part_type": "question",
                        "source_label": "1",
                        "text": "New question",
                        "max_marks": 5,
                    }
                ]
            }
        else:
            raise AssertionError(schema)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(parsed=schema.model_validate(output), refusal=None)
                )
            ],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=30, total_tokens=130),
            _request_id="private-test-request",
        )

    def run_step(self, claim=None):
        run_claim(*(claim or claim_next()), client=self.provider_client)

    def drain(self):
        for _ in range(50):
            claim = claim_next()
            if not claim:
                return
            self.run_step(claim)
        raise AssertionError("Worker failed to drain")

    def test_complete_student_uses_rubric_reference_context_and_publishes_atomically(self):
        job = self.enqueue()
        self.run_step()
        self.assertFalse(GradingResult.objects.exists())
        self.run_step()
        self.assertFalse(GradingResult.objects.exists())
        self.assertIsNone(claim_next())
        result = GradingResult.objects.get()
        self.assertEqual(result.ai_score, 3)
        self.assertEqual(result.final_score, 3)
        self.assertEqual(len(result.criterion_results), 2)
        prompt = self.calls[-1]["messages"][-1]["content"]
        for text in ("Reference answer:", "Method", "Answer", "Use x=2.", "2+2=4"):
            self.assertIn(text, prompt)
        self.assertRegex(prompt, r"Reference answer:\s*4\b")
        job.refresh_from_db()
        self.assertEqual(job.state, "succeeded")
        self.assertEqual(job.result_reference["submission_id"], self.submission.id)
        self.assertEqual(LLMUsage.objects.count(), 2)
        self.assertEqual(AIJobAttempt.objects.filter(state="succeeded").count(), 2)

    def test_saved_model_and_reasoning_survive_env_changes(self):
        with patch.dict(
            os.environ,
            {"OPENAI_GRADING_MODEL": "saved-model", "OPENAI_GRADING_REASONING_EFFORT": "low"},
        ):
            self.enqueue()
        with patch.dict(
            os.environ,
            {"OPENAI_GRADING_MODEL": "changed-model", "OPENAI_GRADING_REASONING_EFFORT": "high"},
        ):
            self.drain()
        self.assertEqual(self.calls[-1]["model"], "saved-model")
        self.assertEqual(self.calls[-1]["reasoning_effort"], "low")

    def test_generation_publishes_all_three_artifact_types(self):
        for operation in ("reference_answers", "rubric"):
            job = self.enqueue(operation, options={"replace_existing": True})
            self.drain()
            job.refresh_from_db()
            self.assertEqual(job.state, "succeeded")
        self.question.refresh_from_db()
        self.assertEqual(self.question.reference_answer.answer_text, "New model answer")
        self.assertEqual(self.question.rubric_criteria.get().title, "New criterion")
        job = self.enqueue("questions")
        self.drain()
        job.refresh_from_db()
        self.assertEqual(job.state, "succeeded")
        self.assertEqual(self.assignment.question_parts.get().text, "New question")

    def test_saved_response_replays_after_death_before_checkpoint(self):
        job = self.enqueue("reference_answers", options={"replace_existing": True})
        step_id, token = claim_next()
        step = AIJobStep.objects.select_related("job").get(pk=step_id)
        execute_recipe(step, RecipeService(step, token, client=self.provider_client))
        AIJobStep.objects.filter(pk=step_id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.drain()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(LLMUsage.objects.count(), 1)
        job.refresh_from_db()
        self.assertEqual(job.state, "succeeded")

    def test_stale_owner_cannot_checkpoint_or_extend_expired_lease(self):
        self.enqueue()
        old = claim_next()
        AIJobStep.objects.filter(pk=old[0]).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        heartbeat([old])
        replacement = claim_next()
        self.assertNotEqual(old[1], replacement[1])
        self.run_step(old)
        self.assertFalse(self.calls)
        self.run_step(replacement)
        self.drain()
        self.assertEqual(len(self.calls), 2)

    def test_unknown_charge_requires_explicit_retry_and_retains_reservation(self):
        job = self.enqueue()

        def disconnect(kwargs):
            raise APIConnectionError(request=httpx.Request("POST", "https://provider.invalid"))

        self.callback = disconnect
        self.run_step()
        job.refresh_from_db()
        usage = LLMUsage.objects.get()
        self.assertEqual(job.state, "needs_attention")
        self.assertEqual(usage.status, "uncertain")
        self.assertGreater(usage.reserved_tokens, 0)
        self.assertIsNone(claim_next())
        with self.assertRaises(JobConflict):
            retry_job(owner=self.owner, job_id=job.id)
        self.callback = None
        retry_job(owner=self.owner, job_id=job.id, confirm_possible_charge=True)
        self.drain()
        self.assertEqual(LLMUsage.objects.count(), 3)
        usage.refresh_from_db()
        self.assertEqual(usage.status, "uncertain")

    def test_restart_after_dispatch_marks_charge_unknown_without_repeating(self):
        job = self.enqueue()
        claim = claim_next()
        AttemptAccounting(job.steps.get(key="map"), claim[1]).reserve(
            user=self.owner, operation="answer_mapping", model="test-model", estimated_tokens=1000
        )
        AIJobStep.objects.filter(pk=claim[0]).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertIsNone(claim_next())
        job.refresh_from_db()
        self.assertEqual(job.state, "needs_attention")
        self.assertEqual(LLMUsage.objects.get().status, "uncertain")
        self.assertEqual(LLMUsage.objects.get().reserved_tokens, 1000)
        self.assertFalse(self.calls)

    @override_settings(GRAIDER_USER_DAILY_TOKENS=1)
    def test_quota_pause_neither_dispatches_nor_consumes_usage(self):
        job = self.enqueue()
        self.run_step()
        job.refresh_from_db()
        self.assertEqual(job.state, "paused_quota")
        self.assertFalse(self.calls)
        self.assertFalse(LLMUsage.objects.exists())

    @override_settings(GRAIDER_AI_SAFE_RETRIES=1)
    def test_safe_rate_limit_retry_is_bounded(self):
        job = self.enqueue()

        def rate_limit(kwargs):
            response = httpx.Response(
                429, request=httpx.Request("POST", "https://provider.invalid")
            )
            raise RateLimitError(
                "Rate limited", response=response, body={"error": {"code": "rate_limit_exceeded"}}
            )

        self.callback = rate_limit
        self.run_step()
        job.refresh_from_db()
        self.assertEqual(job.state, "retry_wait")
        self.assertIsNone(claim_next())
        AIJob.objects.filter(pk=job.id).update(retry_after=timezone.now() - timedelta(seconds=1))
        self.run_step()
        job.refresh_from_db()
        self.assertEqual(job.state, "failed")
        self.assertEqual(LLMUsage.objects.count(), 2)
        self.assertFalse(LLMUsage.objects.exclude(reserved_tokens=0).exists())

    def test_edits_before_claim_block_calls_and_edits_during_calls_block_publication(self):
        job = self.enqueue()
        self.question.text = "Changed"
        self.question.save()
        self.assertIsNone(claim_next())
        job.refresh_from_db()
        self.assertEqual(job.state, "superseded")
        self.assertFalse(self.calls)
        job = self.enqueue()

        def edit(kwargs):
            self.submission.raw_response_text = "Teacher changed submission"
            self.submission.save()

        self.callback = edit
        self.run_step()
        self.assertIsNone(claim_next())
        job.refresh_from_db()
        self.assertEqual(job.state, "superseded")
        self.assertFalse(GradingResult.objects.exists())

    def test_cancellation_during_request_keeps_charge_but_blocks_publication(self):
        job = self.enqueue()
        self.callback = lambda kwargs: cancel_job(owner=self.owner, job_id=job.id)
        self.run_step()
        job.refresh_from_db()
        self.assertEqual(job.state, "cancelled")
        self.assertEqual(LLMUsage.objects.get().total_tokens, 130)
        self.assertFalse(GradingResult.objects.exists())
        self.assertFalse(job.targets.filter(active=True).exists())

    def test_teacher_criterion_overrides_and_feedback_survive_regrading(self):
        self.enqueue()
        self.drain()
        result = GradingResult.objects.get()
        rows = result.criterion_results
        rows[0]["final_score"], rows[0]["final_feedback"] = "3", "Teacher explanation"
        result.final_score, result.final_feedback, result.criterion_results = (
            4,
            "Teacher overall",
            rows,
        )
        # Older published results may still contain an outdated denominator.
        result.max_score = 0
        result.save()
        self.enqueue(options={"regrade": True})
        self.drain()
        result.refresh_from_db()
        self.assertEqual(result.ai_score, 3)
        self.assertEqual(result.final_score, 4)
        self.assertEqual(result.max_score, self.question.max_marks)
        self.assertEqual(result.final_feedback, "Teacher overall")
        self.assertEqual(result.criterion_results[0]["final_feedback"], "Teacher explanation")

    @override_settings(GRAIDER_AI_STUDENT_CONCURRENCY=1)
    def test_student_result_publishes_while_next_student_is_unfinished(self):
        second = self.make_submission("Student Two")
        parent = self.enqueue("grade_batch")
        first = claim_next()
        self.assertIsNone(claim_next())
        self.run_step(first)
        self.run_step()
        next_student = claim_next()
        self.submission.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.submission.grading_status, "graded")
        self.assertEqual(second.grading_status, "pending")
        self.assertFalse(second.grading_results.exists())
        parent.refresh_from_db()
        self.assertEqual(parent.completed_steps, 2)
        self.run_step(next_student)
        self.drain()
        parent.refresh_from_db()
        self.assertEqual(parent.state, "succeeded")
        self.assertEqual(parent.completed_steps, 4)

    def test_failed_student_does_not_block_others(self):
        self.make_submission("Student Two")
        parent = self.enqueue("grade_batch")

        def disconnect(kwargs):
            raise APIConnectionError(request=httpx.Request("POST", "https://provider.invalid"))

        self.callback = disconnect
        self.run_step()
        self.callback = None
        self.drain()
        self.assertEqual(parent.children.filter(state="succeeded").count(), 1)
        self.assertEqual(parent.children.filter(state="needs_attention").count(), 1)

    def test_interactive_priority_and_aging(self):
        grade = self.enqueue()
        interactive = self.enqueue("reference_answers", options={"replace_existing": True})
        claim = claim_next()
        self.assertEqual(AIJobStep.objects.get(pk=claim[0]).job_id, interactive.id)
        AIJob.objects.filter(pk=grade.id).update(updated_at=timezone.now() - timedelta(seconds=100))
        claim = claim_next()
        self.assertEqual(AIJobStep.objects.get(pk=claim[0]).job_id, grade.id)

    @override_settings(GRAIDER_AI_CONCURRENCY=1)
    def test_concurrent_schedulers_share_global_capacity(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locking required")
        self.enqueue()
        self.enqueue("reference_answers", options={"replace_existing": True})
        barrier = threading.Barrier(2)

        def claim():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return claim_next()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: claim(), range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_unsupported_version_and_disabled_mode_do_not_call_provider(self):
        job = self.enqueue()
        with override_settings(GRAIDER_AI_JOBS_ENABLED=False):
            self.assertIsNone(claim_next())
            self.assertFalse(notify_worker())
        AIJob.objects.filter(pk=job.id).update(version=999)
        self.assertIsNone(claim_next())
        job.refresh_from_db()
        self.assertEqual(job.error_code, "unsupported_version")
        self.assertFalse(self.calls)

    def test_retry_api_requires_ready_worker_and_csrf(self):
        job = self.enqueue()
        job.state = JobState.PAUSED_QUOTA
        job.save()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        client.get("/api/docs/")
        token = client.cookies["csrftoken"].value
        with patch("apps.ai_jobs.views.notify_worker", return_value=True):
            response = client.post(
                f"/api/ai/jobs/{job.id}/retry/", {}, format="json", HTTP_X_CSRFTOKEN=token
            )
        self.assertEqual(response.status_code, 202)

    def test_idle_worker_waits_without_db_scans_and_socket_wakes_it(self):
        if connection.vendor != "postgresql":
            self.skipTest("Cross-thread database test uses PostgreSQL")
        with (
            tempfile.TemporaryDirectory() as directory,
            override_settings(
                GRAIDER_AI_WAKE_SOCKET=f"{directory}/wake.sock", GRAIDER_AI_SCAN_SECONDS=0.05
            ),
        ):
            worker, errors = Worker(), []

            def run():
                try:
                    worker.run()
                except Exception as exc:
                    errors.append(exc)

            with patch("apps.ai_jobs.runtime.claim_next", wraps=claim_next) as scan:
                thread = threading.Thread(target=run)
                thread.start()
                try:
                    deadline = time.monotonic() + 5
                    while not worker.ready and time.monotonic() < deadline:
                        time.sleep(0.01)
                    before = scan.call_count
                    time.sleep(0.15)
                    self.assertEqual(scan.call_count, before)
                    self.assertEqual(
                        os.stat(settings.GRAIDER_AI_WAKE_SOCKET).st_mode & 0o777, 0o600
                    )
                    self.assertTrue(notify_worker())
                    deadline = time.monotonic() + 5
                    while scan.call_count == before and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertGreater(scan.call_count, before)
                finally:
                    worker.stop()
                    thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
                self.assertFalse(errors)

    def test_stale_socket_replaced_but_live_socket_preserved(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            override_settings(GRAIDER_AI_WAKE_SOCKET=f"{directory}/wake.sock"),
        ):
            old = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            old.bind(settings.GRAIDER_AI_WAKE_SOCKET)
            old.close()
            worker = Worker()
            try:
                worker.listen()
                with self.assertRaises(RuntimeError):
                    Worker().listen()
                self.assertTrue(Path(settings.GRAIDER_AI_WAKE_SOCKET).exists())
            finally:
                worker.stop()
                worker.listener.close()

    def test_supervisor_stops_survivor_when_sibling_exits(self):
        import supervisor

        commands = [
            [sys.executable, "-c", "import time;time.sleep(0.2);raise SystemExit(2)"],
            [sys.executable, "-c", "import time;time.sleep(60)"],
        ]
        started = time.monotonic()
        self.assertEqual(supervisor.supervise(commands, 1), 2)
        self.assertLess(time.monotonic() - started, 3)

    def test_worker_runs_rolling_concurrent_students_and_publishes_before_slowest_finishes(self):
        if connection.vendor != "postgresql":
            self.skipTest("Cross-thread execution uses PostgreSQL")
        self.submission.raw_response_text = "slowly solving 2+2=4"
        self.submission.save()
        for index in range(3):
            self.make_submission(f"Quick student {index}")
        parent = self.enqueue("grade_batch")
        mutex = threading.Lock()
        inflight, peak, observed_early = 0, 0, []
        first_three = threading.Barrier(3)
        faster_published = threading.Event()
        observing = threading.Event()
        observing.set()
        entered = 0

        def observe():
            close_old_connections()
            try:
                while observing.is_set():
                    if self.assignment.submissions.filter(grading_status="graded").exists():
                        faster_published.set()
                        return
                    time.sleep(0.01)
            finally:
                connections.close_all()

        def delayed(kwargs):
            nonlocal inflight, peak, entered
            slow = "slowly" in kwargs["messages"][-1]["content"]
            with mutex:
                inflight += 1
                peak = max(peak, inflight)
                entered += 1
                position = entered
            if position <= 3:
                first_three.wait(timeout=10)
            if slow:
                observed_early.append(faster_published.wait(timeout=10))
            else:
                time.sleep(0.01)
            with mutex:
                inflight -= 1

        self.callback = delayed
        worker = Worker(runner=lambda *claim: run_claim(*claim, client=self.provider_client))
        observer = threading.Thread(target=observe)
        observer.start()
        try:
            with override_settings(GRAIDER_AI_SCAN_SECONDS=0.01):
                worker.run(once=True)
        finally:
            observing.clear()
            observer.join(timeout=5)
        parent.refresh_from_db()
        self.assertEqual(parent.state, "succeeded")
        self.assertEqual(peak, 3)
        self.assertEqual(observed_early, [True])
        self.assertEqual(len(self.calls), 8)

    def test_bulk_reference_outputs_remain_private_until_all_steps_succeed(self):
        self.make_question("Q2")
        job = self.enqueue("reference_answers", options={"replace_existing": True})
        self.run_step()
        self.question.refresh_from_db()
        self.assertEqual(self.question.reference_answer.answer_text, "4")
        self.run_step()
        self.question.refresh_from_db()
        self.assertEqual(self.question.reference_answer.answer_text, "4")
        self.assertIsNone(claim_next())
        self.question.refresh_from_db()
        self.assertEqual(self.question.reference_answer.answer_text, "New model answer")
        job.refresh_from_db()
        self.assertEqual(job.state, "succeeded")

    def test_database_failure_after_provider_response_requires_billing_acknowledgement(self):
        from django.db import DatabaseError

        job = self.enqueue()
        claim = claim_next()
        with (
            patch(
                "apps.ai_jobs.accounting.AttemptAccounting.finish",
                side_effect=DatabaseError("simulated outage"),
            ),
            self.assertRaises(DatabaseError),
        ):
            self.run_step(claim)
        AIJobStep.objects.filter(pk=claim[0]).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertIsNone(claim_next())
        job.refresh_from_db()
        self.assertEqual(job.state, "needs_attention")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(LLMUsage.objects.get().status, "uncertain")

    def test_cancelling_batch_children_does_not_leave_parent_queued_forever(self):
        parent = self.enqueue("grade_batch")
        cancel_job(owner=self.owner, job_id=parent.children.get().id)
        self.assertIsNone(claim_next())
        parent.refresh_from_db()
        self.assertNotIn(parent.state, ("queued", "running", "retry_wait"))

    def test_regrade_does_not_erase_legacy_teacher_total(self):
        GradingResult.objects.create(
            submission=self.submission,
            question_part=self.question,
            max_score=5,
            ai_score=2,
            final_score=4,
            final_feedback="Teacher total",
        )
        job = self.enqueue(options={"regrade": True})
        self.drain()
        job.refresh_from_db()
        self.assertEqual(job.state, "needs_attention")
        self.assertEqual(GradingResult.objects.get().final_score, 4)
        self.assertEqual(job.completed_steps, 2)

    def test_deleted_assignment_supersedes_saved_result_without_publishing(self):
        job = self.enqueue("reference_answers", options={"replace_existing": True})
        self.callback = lambda kwargs: self.assignment.delete()
        self.run_step()
        self.assertIsNone(claim_next())
        job.refresh_from_db()
        self.assertEqual(job.state, "superseded")
        self.assertIsNone(job.assignment_id)
        self.assertEqual(LLMUsage.objects.get().total_tokens, 130)

    def test_deleted_job_does_not_crash_worker_or_erase_existing_usage(self):
        job = self.enqueue("reference_answers", options={"replace_existing": True})
        self.callback = lambda kwargs: AIJob.objects.filter(pk=job.id).delete()
        self.run_step()
        self.assertFalse(AIJob.objects.filter(pk=job.id).exists())
        self.assertEqual(LLMUsage.objects.get().total_tokens, 130)
        self.assertEqual(LLMUsage.objects.get().status, "succeeded")

    def test_independent_reference_jobs_both_publish(self):
        second = self.make_question("Q2")
        jobs = [
            self.enqueue(
                "reference_answers",
                options={"question_part_id": question.id, "replace_existing": True},
            )
            for question in (self.question, second)
        ]
        self.drain()
        for job in jobs:
            job.refresh_from_db()
            self.assertEqual(job.state, "succeeded")
        self.assertEqual(len(self.calls), 2)
        second.refresh_from_db()
        self.assertEqual(second.reference_answer.answer_text, "New model answer")

    def test_independent_rubric_jobs_both_publish(self):
        second = self.make_question("Q2")
        jobs = [
            self.enqueue(
                "rubric", options={"question_part_id": question.id, "replace_existing": True}
            )
            for question in (self.question, second)
        ]
        self.drain()
        for job in jobs:
            job.refresh_from_db()
            self.assertEqual(job.state, "succeeded")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(second.rubric_criteria.get().title, "New criterion")

    def test_target_reference_edit_still_supersedes_generation(self):
        job = self.enqueue(
            "reference_answers",
            options={"question_part_id": self.question.id, "replace_existing": True},
        )

        def edit_target(kwargs):
            answer = self.question.reference_answer
            answer.answer_text = "Teacher changed this while AI ran"
            answer.save()

        self.callback = edit_target
        self.drain()
        job.refresh_from_db()
        self.assertEqual(job.state, "superseded")
        self.question.refresh_from_db()
        self.assertEqual(
            self.question.reference_answer.answer_text, "Teacher changed this while AI ran"
        )
