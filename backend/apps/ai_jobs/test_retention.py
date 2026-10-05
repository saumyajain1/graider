import tempfile
from datetime import timedelta
from io import StringIO
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.grading.models import GradingResult, LLMUsage, ReferenceAnswer

from .models import AIJob, AIJobAttempt, AIJobStep, AIJobTarget
from .retention import prune_jobs
from .tests import JobFixtures


class RetentionTests(JobFixtures, TestCase):
    def job(self, state="succeeded", age=40, parent=None):
        return AIJob.objects.create(
            owner=self.owner,
            assignment=self.assignment,
            submission=self.submission,
            parent=parent,
            operation="grade_submission",
            state=state,
            input_snapshot={"private": "discard old diagnostics"},
            input_fingerprint="unused",
            request_fingerprint="unused",
            finished_at=timezone.now() - timedelta(days=age),
        )

    def attempt(self, job, status="uncertain"):
        step = AIJobStep.objects.create(
            job=job, key="map", position=0, state="succeeded", checkpoint={"saved": "answer"}
        )
        usage = LLMUsage.objects.create(
            user=self.owner,
            operation="answer_mapping",
            model="test-only",
            status=status,
            reserved_tokens=500,
        )
        AIJobAttempt.objects.create(
            step=step,
            number=1,
            claim_token=uuid4(),
            usage=usage,
            state="uncertain",
            output={"saved": "response"},
        )
        return usage

    def test_command_previews_by_default_and_apply_removes_only_diagnostics(self):
        job = self.job()
        usage = self.attempt(job)
        AIJobTarget.objects.create(job=job, key="old", active=False)
        result = GradingResult.objects.create(
            submission=self.submission,
            question_part=self.question,
            ai_score=4,
            final_score=4,
            max_score=5,
            criterion_results=[{"final_score": "4"}],
        )
        with (
            tempfile.TemporaryDirectory() as folder,
            self.settings(
                MEDIA_ROOT=folder,
                STORAGES={
                    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                    "staticfiles": {
                        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                    },
                },
            ),
        ):
            self.assignment.source_file.save("retention.txt", ContentFile(b"Preserve upload"))
            preview = StringIO()
            call_command("prune_ai_jobs", stdout=preview)
            self.assertIn("Would delete 1", preview.getvalue())
            self.assertTrue(AIJob.objects.filter(pk=job.pk).exists())
            applied = StringIO()
            call_command("prune_ai_jobs", apply=True, stdout=applied)
            self.assertIn("Deleted 1", applied.getvalue())
            self.assertEqual(self.assignment.source_file.read(), b"Preserve upload")
        self.assertFalse(AIJob.objects.exists())
        self.assertFalse(AIJobAttempt.objects.exists())
        self.assertFalse(AIJobStep.objects.exists())
        self.assertFalse(AIJobTarget.objects.exists())
        result.refresh_from_db()
        usage.refresh_from_db()
        self.assertEqual(result.final_score, 4)
        self.assertEqual(usage.reserved_tokens, 500)
        self.assertEqual(usage.status, "uncertain")
        self.assertTrue(ReferenceAnswer.objects.filter(question_part=self.question).exists())
        self.assertTrue(self.question.rubric_criteria.exists())
        self.assertTrue(type(self.submission).objects.filter(pk=self.submission.pk).exists())

    def test_active_paused_attention_and_unknown_states_are_never_pruned(self):
        for state in (
            "queued",
            "running",
            "retry_wait",
            "paused_quota",
            "needs_attention",
            "future_state",
        ):
            self.job(state=state)
        self.assertEqual(prune_jobs(apply=True), {"roots": 0, "jobs": 0})
        self.assertEqual(AIJob.objects.count(), 6)

    def test_recent_or_unfinished_terminal_jobs_are_retained(self):
        self.job(age=2)
        unfinished = self.job()
        AIJob.objects.filter(pk=unfinished.pk).update(finished_at=None)
        self.assertEqual(prune_jobs(apply=True)["jobs"], 0)

    def test_batch_is_retained_if_a_child_is_active_recent_or_unknown(self):
        for state, age in (("paused_quota", 40), ("failed", 2), ("future_state", 40)):
            root = self.job()
            self.job(state=state, age=age, parent=root)
        self.assertEqual(prune_jobs(apply=True)["jobs"], 0)
        self.assertEqual(AIJob.objects.count(), 6)

    def test_complete_old_batch_is_deleted_as_one_tree_in_bounded_transactions(self):
        root = self.job()
        self.job(parent=root)
        self.job(state="failed", parent=root)
        self.job(state="cancelled")
        self.job(state="superseded")
        self.assertEqual(prune_jobs(batch_size=1, apply=True), {"roots": 3, "jobs": 5})
        self.assertFalse(AIJob.objects.exists())

    def test_active_target_running_step_and_pending_usage_protect_terminal_jobs(self):
        target = self.job()
        AIJobTarget.objects.create(job=target, key="active", active=True)
        running = self.job()
        AIJobStep.objects.create(job=running, key="map", position=0, state="running")
        pending = self.job()
        self.attempt(pending, status="pending")
        self.assertEqual(prune_jobs(apply=True)["jobs"], 0)

    def test_invalid_retention_arguments_fail_without_deletion(self):
        self.job()
        for options in ({"days": 0}, {"days": -1}, {"batch_size": 0}, {"batch_size": 101}):
            with self.subTest(options=options), self.assertRaises(CommandError):
                call_command("prune_ai_jobs", apply=True, **options)
        self.assertEqual(AIJob.objects.count(), 1)

    def test_unrecognized_nested_tree_is_preserved(self):
        root = self.job()
        child = self.job(parent=root)
        self.job(state="paused_quota", parent=child)
        self.assertEqual(prune_jobs(apply=True)["jobs"], 0)
        self.assertEqual(AIJob.objects.count(), 3)
