import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIClient

from apps.assignments.models import Assignment, QuestionPart
from apps.grading.models import (
    GradingResult,
    LLMUsage,
    ReferenceAnswer,
    RubricCriterion,
    StudentSubmission,
)

from .models import AIJob, AIJobAttempt, AIJobCoordinator, AIJobStep, AIJobTarget, JobState
from .services import JobConflict, QueueFull, cancel_job, enqueue_job, retry_job
from .snapshots import fingerprint


class JobFixtures:
    def setUp(self):
        super().setUp()
        AIJobCoordinator.objects.get_or_create(pk=1)
        self.owner = get_user_model().objects.create_user(
            email="jobs@example.test", password="JobTest2026!"
        )
        self.other = get_user_model().objects.create_user(
            email="other-jobs@example.test", password="JobTest2026!"
        )
        self.assignment = Assignment.objects.create(
            teacher=self.owner,
            title="Math",
            course_name="MATH101",
            raw_assignment_text="Solve both questions.",
            source_original_filename="math.txt",
        )
        self.context = QuestionPart.objects.create(
            assignment=self.assignment,
            part_key="shared",
            part_type="context",
            text="Use x=2.",
        )
        self.question = self.make_question("Q1")
        self.submission = self.make_submission("Student One")

    def make_question(self, key):
        question = QuestionPart.objects.create(
            assignment=self.assignment,
            part_key=key,
            parent_key="shared",
            text="What is x+x?",
            max_marks=Decimal("5"),
            display_order=self.assignment.question_parts.count(),
        )
        ReferenceAnswer.objects.create(question_part=question, answer_text="4", source="teacher")
        RubricCriterion.objects.create(
            question_part=question, title="Method", description="Add x to x.", max_points=3
        )
        RubricCriterion.objects.create(
            question_part=question, title="Answer", description="Obtain 4.", max_points=2
        )
        return question

    def make_submission(self, name):
        return StudentSubmission.objects.create(
            assignment=self.assignment, student_name=name, raw_response_text="2+2=4"
        )

    def enqueue(self, operation=AIJob.Operation.GRADE, **kwargs):
        if operation == AIJob.Operation.QUESTIONS:
            kwargs.setdefault("options", {"replace_existing": True})
        return enqueue_job(
            owner=self.owner,
            operation=operation,
            assignment_id=self.assignment.id,
            **({"submission_id": self.submission.id} if operation == AIJob.Operation.GRADE else {}),
            **kwargs,
        )[0]

    def fail_job(self, job, state=JobState.FAILED):
        job.state = state
        job.save(update_fields=("state", "updated_at"))
        if state == JobState.FAILED:
            job.targets.update(active=False)
        return job


class AdmissionTests(JobFixtures, TestCase):
    def test_admission_captures_complete_recipe_without_provider_or_usage(self):
        with patch("apps.grading.services.openai_client.OpenAI") as provider:
            job = self.enqueue()
            provider.assert_not_called()
        self.assertFalse(LLMUsage.objects.exists())
        snapshot = job.input_snapshot
        self.assertEqual(snapshot["configuration"]["submission_grading"]["model"], "gpt-6-luna")
        self.assertIn(
            snapshot["configuration"]["submission_grading"]["reasoning_effort"],
            ("none", "low", "medium", "high", "xhigh", "max"),
        )
        self.assertEqual(snapshot["parts"][0]["text"], "Use x=2.")
        self.assertEqual(snapshot["parts"][1]["reference"]["text"], "4")
        self.assertEqual(
            [c["max_points"] for c in snapshot["parts"][1]["rubric"]], ["3.00", "2.00"]
        )
        self.assertEqual(snapshot["submission"]["text"], "2+2=4")
        self.assertEqual(snapshot["assignment"]["course_name"], "MATH101")
        self.assertEqual(job.input_fingerprint, fingerprint(snapshot))
        self.assertEqual(
            list(job.steps.values_list("key", flat=True)), ["map", f"grade:{self.question.id}"]
        )
        self.assertEqual(job.total_steps, 2)
        self.assignment.raw_assignment_text = "Changed after enqueue."
        self.assignment.save()
        job.refresh_from_db()
        self.assertEqual(job.input_snapshot["assignment"]["text"], "Solve both questions.")
        self.assertNotIn("API_KEY", str(snapshot))
        self.assertNotIn("AWS", str(snapshot))

    def test_question_extraction_requires_explicit_replacement_of_existing_parts(self):
        with self.assertRaises(ValidationError):
            self.enqueue("questions", options={})
        self.assertFalse(AIJob.objects.exists())
        job = self.enqueue("questions", options={"replace_existing": True})
        self.assertTrue(job.input_snapshot["options"]["replace_existing"])
        self.assertEqual(self.assignment.question_parts.count(), 2)

    def test_identity_and_snapshot_are_immutable(self):
        job = self.enqueue()
        job.input_snapshot["assignment"]["text"] = "Changed"
        with self.assertRaises(ValueError):
            job.save()
        job.refresh_from_db()
        self.assertEqual(job.input_snapshot["assignment"]["text"], "Solve both questions.")

    def test_idempotency_replays_even_after_inputs_change_and_rejects_different_intent(self):
        job = self.enqueue(request_key="button-click")
        self.assignment.raw_assignment_text = "Changed"
        self.assignment.save()
        replay, created = enqueue_job(
            owner=self.owner,
            operation="grade_submission",
            assignment_id=self.assignment.id,
            submission_id=self.submission.id,
            request_key="button-click",
            options={"regrade": False},
        )
        self.assertEqual(replay.id, job.id)
        self.assertFalse(created)
        with self.assertRaises(JobConflict):
            self.enqueue(request_key="button-click", options={"regrade": True})
        self.assertEqual(AIJob.objects.count(), 1)

    def test_duplicate_without_key_conflicts(self):
        self.enqueue()
        with self.assertRaises(JobConflict):
            self.enqueue()
        self.assertEqual(AIJob.objects.count(), 1)

    def test_bulk_generation_conflicts_with_single_question_and_atomic_batch(self):
        self.make_question("Q2")
        single = self.enqueue(
            "reference_answers",
            options={"question_part_id": self.question.id, "replace_existing": True},
        )
        with self.assertRaises(JobConflict):
            self.enqueue("reference_answers", options={"replace_existing": True})
        self.assertEqual(AIJob.objects.count(), 1)
        cancel_job(owner=self.owner, job_id=single.id)
        bulk = self.enqueue("reference_answers", options={"replace_existing": True})
        self.assertEqual(bulk.steps.count(), 2)
        with self.assertRaises(JobConflict):
            self.enqueue(
                "reference_answers",
                options={"question_part_id": self.question.id, "replace_existing": True},
            )

    def test_each_generation_operation_has_scoped_steps(self):
        extraction = self.enqueue("questions")
        self.assertEqual(list(extraction.steps.values_list("key", flat=True)), ["extract"])
        rubric = self.enqueue("rubric", options={"replace_existing": True})
        self.assertEqual(
            list(rubric.targets.values_list("key", flat=True)), [f"rubric:{self.question.id}"]
        )
        self.assertLess(rubric.priority, self.enqueue().priority)

    def test_fill_missing_does_not_overwrite_existing_artifacts(self):
        with self.assertRaises(ValidationError):
            self.enqueue("reference_answers")
        missing = self.make_question("Q2")
        missing.reference_answer.delete()
        job = self.enqueue("reference_answers")
        self.assertEqual(
            list(job.targets.values_list("key", flat=True)), [f"reference_answers:{missing.id}"]
        )
        self.assertEqual(ReferenceAnswer.objects.get(question_part=self.question).answer_text, "4")

    def test_ownership_and_input_validation_do_not_write_jobs(self):
        invalid = [
            {"owner": self.other},
            {"assignment_id": 987654},
            {"submission_id": 987654},
            {"options": {"regrade": "true"}},
            {"request_key": "x" * 129},
            {"operation": "unknown"},
        ]
        for override in invalid:
            with self.subTest(override=override), self.assertRaises((NotFound, ValidationError)):
                enqueue_job(
                    **(
                        {
                            "owner": self.owner,
                            "operation": "grade_submission",
                            "assignment_id": self.assignment.id,
                            "submission_id": self.submission.id,
                        }
                        | override
                    )
                )
        self.assertFalse(AIJob.objects.exists())

    def test_batch_default_skips_complete_and_finalized_students(self):
        complete = self.make_submission("Already graded")
        complete.grading_status = "graded"
        complete.save()
        final = self.make_submission("Finalized")
        final.grading_status = "finalized"
        final.save()
        second = self.make_submission("Student Two")
        parent = self.enqueue("grade_batch")
        self.assertEqual(parent.children.count(), 2)
        self.assertEqual(
            set(parent.children.values_list("submission_id", flat=True)),
            {self.submission.id, second.id},
        )
        self.assertEqual(parent.total_steps, 4)
        self.assertFalse(parent.steps.exists())
        self.assertFalse(parent.targets.exists())
        self.assertEqual(parent.input_snapshot["submission_ids"], [self.submission.id, second.id])
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.grading_status, "pending")

    def test_batch_rolls_back_every_child_if_any_input_or_target_is_invalid(self):
        second = self.make_submission("Student Two")
        second.raw_response_text = ""
        second.save()
        with self.assertRaises(ValidationError):
            self.enqueue("grade_batch")
        self.assertFalse(AIJob.objects.exists())
        second.raw_response_text = "4"
        second.save()
        self.enqueue()
        with self.assertRaises(JobConflict):
            self.enqueue("grade_batch")
        self.assertEqual(AIJob.objects.count(), 1)
        self.assertEqual(AIJobTarget.objects.count(), 1)

    @override_settings(GRAIDER_AI_USER_QUEUE_LIMIT=1)
    def test_batch_parent_does_not_count_but_children_do(self):
        second = self.make_submission("Student Two")
        with self.assertRaises(QueueFull):
            self.enqueue("grade_batch")
        self.assertFalse(AIJob.objects.exists())
        second.delete()
        parent = self.enqueue("grade_batch")
        self.assertEqual(parent.children.count(), 1)

    @override_settings(GRAIDER_AI_GLOBAL_QUEUE_LIMIT=1)
    def test_paused_work_counts_and_completed_work_releases_capacity(self):
        job = self.fail_job(self.enqueue(), JobState.PAUSED_QUOTA)
        with self.assertRaises(QueueFull):
            self.enqueue("questions")
        cancel_job(owner=self.owner, job_id=job.id)
        self.enqueue("questions")

    def test_maximum_demo_batch_is_ten_students_with_ten_questions(self):
        for index in range(2, 11):
            self.make_question(f"Q{index}")
            self.make_submission(f"Student {index}")
        job = self.enqueue("grade_batch")
        self.assertEqual(job.children.count(), 10)
        self.assertEqual(job.total_steps, 110)  # Each student has mapping plus ten questions.

    def test_oversized_batch_and_question_count_are_rejected(self):
        for index in range(10):
            self.make_submission(f"Extra {index}")
        with self.assertRaises(ValidationError):
            self.enqueue("grade_batch")
        for index in range(10):
            self.make_question(f"Extra {index}")
        with self.assertRaises(ValidationError):
            self.enqueue()
        self.assertFalse(AIJob.objects.exists())

    def test_regrading_requires_explicit_choice_and_preserves_grades(self):
        result = GradingResult.objects.create(
            submission=self.submission,
            question_part=self.question,
            ai_score=4,
            final_score=5,
            max_score=5,
            final_feedback="Teacher edit",
        )
        self.submission.grading_status = "reviewed"
        self.submission.save()
        with self.assertRaises(JobConflict):
            self.enqueue()
        job = self.enqueue(options={"regrade": True})
        result.refresh_from_db()
        self.assertEqual(result.final_score, 5)
        self.assertEqual(result.final_feedback, "Teacher edit")
        self.assertEqual(job.input_snapshot["submission"]["published_results"][0]["id"], result.id)

    def test_database_constraints_protect_targets_step_order_and_progress(self):
        job = self.enqueue()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AIJobTarget.objects.create(job=job, key=job.targets.get().key)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AIJobStep.objects.create(job=job, key="another", position=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AIJob.objects.filter(pk=job.id).update(completed_steps=3)

    def test_idempotency_keys_are_scoped_to_each_owner(self):
        self.enqueue(request_key="shared-key")
        foreign = Assignment.objects.create(
            teacher=self.other, title="Other", raw_assignment_text="Extract."
        )
        other_job, created = enqueue_job(
            owner=self.other,
            operation="questions",
            assignment_id=foreign.id,
            request_key="shared-key",
        )
        self.assertTrue(created)
        self.assertEqual(other_job.owner_id, self.other.id)
        self.assertEqual(AIJob.objects.count(), 2)

    def test_failure_during_child_creation_rolls_back_parent_and_previous_children(self):
        from . import services

        self.make_submission("Student Two")
        create = services.create_job
        calls = 0

        def fail_third(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise IntegrityError("Simulated database failure creating second child")
            return create(*args, **kwargs)

        with (
            patch("apps.ai_jobs.services.create_job", side_effect=fail_third),
            self.assertRaises(IntegrityError),
        ):
            self.enqueue("grade_batch")
        self.assertFalse(AIJob.objects.exists())
        self.assertFalse(AIJobStep.objects.exists())
        self.assertFalse(AIJobTarget.objects.exists())


class ControlTests(JobFixtures, TestCase):
    def test_cancel_is_idempotent_and_keeps_completed_checkpoints(self):
        job = self.enqueue()
        step = job.steps.first()
        step.state = JobState.SUCCEEDED
        step.checkpoint = {"mapped": "answer"}
        step.save()
        cancelled = cancel_job(owner=self.owner, job_id=job.id)
        self.assertEqual(cancelled.state, JobState.CANCELLED)
        self.assertFalse(cancelled.targets.filter(active=True).exists())
        self.assertEqual(cancel_job(owner=self.owner, job_id=job.id).state, JobState.CANCELLED)
        step.refresh_from_db()
        self.assertEqual(step.state, JobState.SUCCEEDED)
        self.assertEqual(step.checkpoint, {"mapped": "answer"})

    def test_running_cancel_keeps_claim_until_worker_acknowledges(self):
        job = self.enqueue()
        job.state = JobState.RUNNING
        job.save()
        result = cancel_job(owner=self.owner, job_id=job.id)
        self.assertTrue(result.cancel_requested)
        self.assertEqual(result.state, JobState.RUNNING)
        self.assertTrue(result.targets.filter(active=True).exists())
        with self.assertRaises(JobConflict):
            self.enqueue()

    def test_batch_cancel_preserves_completed_students(self):
        self.make_submission("Student Two")
        parent = self.enqueue("grade_batch")
        complete = parent.children.first()
        complete.state = JobState.SUCCEEDED
        complete.save()
        complete.targets.update(active=False)
        cancel_job(owner=self.owner, job_id=parent.id)
        complete.refresh_from_db()
        self.assertEqual(complete.state, JobState.SUCCEEDED)
        self.assertEqual(parent.children.filter(state=JobState.CANCELLED).count(), 1)

    def test_retry_keeps_completed_steps_and_requires_billing_acknowledgement(self):
        job = self.fail_job(self.enqueue(), JobState.NEEDS_ATTENTION)
        completed = job.steps.first()
        completed.state = JobState.SUCCEEDED
        completed.checkpoint = {"mapped": "answer"}
        completed.save()
        usage = LLMUsage.objects.create(
            user=self.owner,
            operation="submission_grading",
            model="test-model",
            status="uncertain",
            reserved_tokens=2500,
        )
        step = job.steps.last()
        AIJobAttempt.objects.create(
            step=step, number=1, claim_token=uuid.uuid4(), usage=usage, state="uncertain"
        )
        with self.assertRaises(JobConflict):
            retry_job(owner=self.owner, job_id=job.id)
        retried = retry_job(owner=self.owner, job_id=job.id, confirm_possible_charge=True)
        self.assertEqual(retried.state, JobState.QUEUED)
        completed.refresh_from_db()
        self.assertEqual(completed.state, JobState.SUCCEEDED)
        self.assertEqual(completed.checkpoint, {"mapped": "answer"})
        usage.refresh_from_db()
        self.assertEqual(usage.reserved_tokens, 2500)
        self.assertEqual(step.attempts.count(), 1)

    def test_changed_inputs_supersede_job_and_release_target_without_erasing_checkpoints(self):
        job = self.fail_job(self.enqueue())
        self.question.text = "Changed question"
        self.question.save()
        with self.assertRaises(JobConflict):
            retry_job(owner=self.owner, job_id=job.id)
        job.refresh_from_db()
        self.assertEqual(job.state, JobState.SUPERSEDED)
        self.assertFalse(job.targets.filter(active=True).exists())
        self.assertEqual(job.steps.count(), 2)

    def test_deleted_submission_is_retained_as_superseded_diagnostic(self):
        job = self.fail_job(self.enqueue())
        self.submission.delete()
        job.refresh_from_db()
        self.assertIsNone(job.submission_id)
        with self.assertRaises(JobConflict):
            retry_job(owner=self.owner, job_id=job.id)
        job.refresh_from_db()
        self.assertEqual(job.state, JobState.SUPERSEDED)

    def test_retry_uses_original_configuration_and_preserves_manual_overrides(self):
        job = self.fail_job(self.enqueue())
        with patch.dict("os.environ", {"OPENAI_GRADING_MODEL": "different-model"}):
            retried = retry_job(owner=self.owner, job_id=job.id)
        self.assertEqual(
            retried.input_snapshot["configuration"]["submission_grading"]["model"], "gpt-6-luna"
        )

    def test_retry_cannot_steal_a_target_from_a_new_job(self):
        old = self.fail_job(self.enqueue())
        self.enqueue()
        with self.assertRaises(JobConflict):
            retry_job(owner=self.owner, job_id=old.id)
        old.refresh_from_db()
        self.assertEqual(old.state, JobState.FAILED)

    def test_batch_retry_requeues_only_failed_student(self):
        self.make_submission("Student Two")
        parent = self.enqueue("grade_batch")
        complete, failed = list(parent.children.order_by("submission_id"))
        complete.state = JobState.SUCCEEDED
        complete.save()
        complete.targets.update(active=False)
        self.fail_job(failed)
        self.fail_job(parent)
        retry_job(owner=self.owner, job_id=parent.id)
        complete.refresh_from_db()
        failed.refresh_from_db()
        self.assertEqual(complete.state, JobState.SUCCEEDED)
        self.assertEqual(failed.state, JobState.QUEUED)

    def test_cross_owner_control_and_finished_cancel_are_rejected(self):
        job = self.enqueue()
        with self.assertRaises(NotFound):
            cancel_job(owner=self.other, job_id=job.id)
        with self.assertRaises(NotFound):
            retry_job(owner=self.other, job_id=job.id)
        job.state = JobState.SUCCEEDED
        job.save()
        with self.assertRaises(JobConflict):
            cancel_job(owner=self.owner, job_id=job.id)

    @override_settings(GRAIDER_AI_GLOBAL_QUEUE_LIMIT=1)
    def test_retry_rechecks_queue_capacity_without_losing_checkpoints(self):
        failed = self.fail_job(self.enqueue())
        self.enqueue("questions")
        with self.assertRaises(QueueFull):
            retry_job(owner=self.owner, job_id=failed.id)
        failed.refresh_from_db()
        self.assertEqual(failed.state, JobState.FAILED)
        self.assertEqual(failed.steps.count(), 2)

    def test_manual_review_during_failed_regrade_supersedes_old_job(self):
        result = GradingResult.objects.create(
            submission=self.submission,
            question_part=self.question,
            max_score=5,
            final_score=3,
            final_feedback="Original",
        )
        failed = self.fail_job(self.enqueue())
        result.final_feedback = "Teacher revised this after job admission"
        result.final_score = 5
        result.save()
        with self.assertRaises(JobConflict):
            retry_job(owner=self.owner, job_id=failed.id)
        result.refresh_from_db()
        self.assertEqual(result.final_score, 5)
        self.assertEqual(result.final_feedback, "Teacher revised this after job admission")

    def test_one_stale_batch_child_does_not_strand_another_paused_child(self):
        second = self.make_submission("Student Two")
        parent = self.enqueue("grade_batch")
        self.fail_job(parent, JobState.PAUSED_QUOTA)
        for child in parent.children.all():
            self.fail_job(child, JobState.PAUSED_QUOTA)
        second.raw_response_text = "New answer"
        second.save()
        with self.assertRaises(JobConflict):
            retry_job(owner=self.owner, job_id=parent.id)
        parent.refresh_from_db()
        self.assertEqual(parent.state, JobState.NEEDS_ATTENTION)
        retry_job(owner=self.owner, job_id=parent.id)
        self.assertEqual(parent.children.filter(state=JobState.SUPERSEDED).count(), 1)
        self.assertEqual(parent.children.filter(state=JobState.QUEUED).count(), 1)

    def test_retrying_a_child_reopens_parent_progress(self):
        parent = self.enqueue("grade_batch")
        failed = self.fail_job(parent.children.get())
        self.fail_job(parent)
        retry_job(owner=self.owner, job_id=failed.id)
        parent.refresh_from_db()
        self.assertEqual(parent.state, JobState.QUEUED)


class JobAPITests(JobFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.job = self.enqueue()
        self.base = f"/api/ai/jobs/{self.job.id}/"

    def test_list_and_detail_show_owned_metadata_without_inputs_or_checkpoints(self):
        self.assignment.teacher = self.other
        self.assignment.save()
        foreign = enqueue_job(
            owner=self.other,
            operation="questions",
            assignment_id=self.assignment.id,
            options={"replace_existing": True},
        )[0]
        response = self.client.get("/api/ai/jobs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        detail = self.client.get(self.base).json()
        self.assertEqual(detail["id"], str(self.job.id))
        self.assertNotIn("input_snapshot", detail)
        self.assertNotIn("steps", detail)
        self.assertNotIn("owner", detail)
        self.assertEqual(self.client.get(f"/api/ai/jobs/{foreign.id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/ai/jobs/?state=garbage").status_code, 400)
        self.assertEqual(
            self.client.get("/api/ai/jobs/?assignment_id=not-a-number").status_code, 400
        )
        self.client.logout()
        self.assertEqual(self.client.get(self.base).status_code, 403)

    def csrf(self):
        self.client.get("/api/docs/")
        return self.client.cookies["csrftoken"].value

    def test_write_routes_enforce_csrf_and_retry_reports_worker_unavailable(self):
        self.assertEqual(self.client.post(self.base + "cancel/").status_code, 403)
        self.assertEqual(self.client.post(self.base + "retry/", {}, format="json").status_code, 403)
        token = self.csrf()
        retry = self.client.post(self.base + "retry/", {}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(retry.status_code, 503)
        self.assertEqual(
            self.client.post(self.base + "cancel/", HTTP_X_CSRFTOKEN=token).status_code, 200
        )
        self.job.refresh_from_db()
        self.assertEqual(self.job.state, JobState.CANCELLED)

    def test_other_owner_gets_404_for_all_control_routes(self):
        self.client.force_login(self.other)
        token = self.csrf()
        for suffix in ("cancel/", "retry/"):
            self.assertEqual(
                self.client.post(
                    self.base + suffix, {}, format="json", HTTP_X_CSRFTOKEN=token
                ).status_code,
                404,
            )
        self.assertEqual(self.client.get(self.base).status_code, 404)

    def test_detail_flags_uncertain_charge_without_revealing_provider_identifier(self):
        AIJobAttempt.objects.create(
            step=self.job.steps.first(),
            number=1,
            claim_token=uuid.uuid4(),
            state="uncertain",
            provider_request_id="private-request-id",
        )
        response = self.client.get(self.base)
        self.assertTrue(response.json()["possible_duplicate_charge"])
        self.assertNotIn("private-request-id", response.content.decode())


class ConcurrentAdmissionTests(JobFixtures, TransactionTestCase):
    def race(self, requests):
        if connection.vendor != "postgresql":
            self.skipTest("Cross-connection row locking requires PostgreSQL.")
        barrier = Barrier(len(requests))

        def admit(request):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                job, created = enqueue_job(**request)
                return str(job.id), created
            except (JobConflict, QueueFull) as exc:
                return exc.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            return list(pool.map(admit, requests))

    def request(self, **kwargs):
        return {
            "owner": self.owner,
            "operation": "grade_submission",
            "assignment_id": self.assignment.id,
            "submission_id": self.submission.id,
        } | kwargs

    def test_competing_identical_keys_return_one_job(self):
        results = self.race([self.request(request_key="same"), self.request(request_key="same")])
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(result[1] for result in results), [False, True])
        self.assertEqual(AIJob.objects.count(), 1)

    def test_competing_targets_admit_only_one(self):
        results = self.race([self.request(), self.request()])
        self.assertEqual(results.count(409), 1)
        self.assertEqual(AIJob.objects.count(), 1)

    @override_settings(GRAIDER_AI_GLOBAL_QUEUE_LIMIT=1)
    def test_global_capacity_is_serialized_across_different_owners(self):
        foreign = Assignment.objects.create(
            teacher=self.other, title="Other", raw_assignment_text="Extract this."
        )
        results = self.race(
            [
                self.request(),
                {"owner": self.other, "operation": "questions", "assignment_id": foreign.id},
            ]
        )
        self.assertEqual(results.count(429), 1)
        self.assertEqual(AIJob.objects.count(), 1)

    def test_batch_and_single_admission_cannot_duplicate_a_student(self):
        self.make_submission("Student Two")
        results = self.race(
            [self.request(), self.request(operation="grade_batch", submission_id=None)]
        )
        self.assertEqual(results.count(409), 1)
        self.assertEqual(
            AIJobTarget.objects.filter(key=f"grade:{self.submission.id}", active=True).count(), 1
        )


class MigrationUpgradeTests(TransactionTestCase):
    def test_additive_upgrade_preserves_existing_accounts_assignment_grades_and_usage(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate([("ai_jobs", None)])
        try:
            user = get_user_model().objects.create_user(email="upgrade@example.test")
            assignment = Assignment.objects.create(
                teacher=user, title="Existing assignment", source_file="existing/file.txt"
            )
            question = QuestionPart.objects.create(
                assignment=assignment, part_key="Q1", text="Question", max_marks=5
            )
            submission = StudentSubmission.objects.create(
                assignment=assignment, student_name="Existing student", total_score=4
            )
            result = GradingResult.objects.create(
                submission=submission,
                question_part=question,
                max_score=5,
                ai_score=3,
                final_score=4,
                final_feedback="Existing teacher feedback",
                criterion_results=[{"title": "Existing criterion"}],
            )
            usage = LLMUsage.objects.create(
                user=user, operation="submission_grading", model="existing-model", total_tokens=200
            )
            MigrationExecutor(connection).migrate(latest)
            self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())
            assignment.refresh_from_db()
            result.refresh_from_db()
            usage.refresh_from_db()
            self.assertEqual(assignment.source_file.name, "existing/file.txt")
            self.assertEqual(result.final_score, 4)
            self.assertEqual(result.final_feedback, "Existing teacher feedback")
            self.assertEqual(result.criterion_results, [{"title": "Existing criterion"}])
            self.assertEqual(usage.total_tokens, 200)
            self.assertTrue(AIJobCoordinator.objects.filter(pk=1).exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
