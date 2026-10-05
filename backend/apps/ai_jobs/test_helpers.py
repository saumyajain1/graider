"""Execute API test jobs through real recipes with explicitly supplied AI replies."""

from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection

from .engine import claim_next, run_claim
from .models import AIJobCoordinator
from .services import enqueue_job


class JobExecutionMixin:
    def setUp(self):
        super().setUp()
        self.enterContext(self.settings(GRAIDER_AI_JOBS_ENABLED=True))
        self.enterContext(patch("apps.ai_jobs.admission.notify_worker", return_value=True))
        AIJobCoordinator.objects.get_or_create(pk=1)
        self.ai_outputs = {}
        self.atomic_depth = len(connection.atomic_blocks)

        def reply(**kwargs):
            # APITestCase itself owns a transaction; execution must not add one.
            self.assertEqual(len(connection.atomic_blocks), self.atomic_depth)
            output = self.ai_outputs[kwargs["operation"]]
            if isinstance(output, Exception):
                raise output
            if callable(output):
                output = output(**kwargs)
            if hasattr(output, "model_dump"):
                output = output.model_dump(mode="json")
            return kwargs["response_format"].model_validate(output)

        self.ai_provider = self.enterContext(
            patch("apps.ai_jobs.accounting.RecipeService.parse", side_effect=reply)
        )

    def drain_jobs(self):
        for _ in range(250):
            claim = claim_next()
            if claim is None:
                return
            run_claim(*claim, client=SimpleNamespace())
        self.fail("Test worker did not drain its runnable jobs.")

    def run_submission_job(self, submission, *, regrade=False):
        job, _ = enqueue_job(
            owner=submission.assignment.teacher,
            assignment_id=submission.assignment_id,
            submission_id=submission.id,
            operation="grade_submission",
            options={"regrade": regrade},
        )
        self.drain_jobs()
        job.refresh_from_db()
        return job
