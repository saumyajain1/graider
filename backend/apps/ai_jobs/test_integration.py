from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.grading.models import GradingResult, LLMQuotaLock, LLMUsage
from apps.grading.services.schemas import (
    GeneratedQuestionGradeSchema,
    SubmissionAnswerMappingSchema,
)

from .engine import claim_next, run_claim
from .models import AIJob, JobState
from .tests import JobFixtures


@override_settings(GRAIDER_AI_JOBS_ENABLED=True)
class WorkflowAPITests(JobFixtures, TransactionTestCase):
    def setUp(self):
        super().setUp()
        LLMQuotaLock.objects.get_or_create(pk=1)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.readiness = patch("apps.ai_jobs.admission.notify_worker", return_value=True)
        self.readiness.start()
        self.addCleanup(self.readiness.stop)

    def test_all_ai_actions_return_owned_job_receipts_without_provider_work(self):
        assignment = f"/api/assignments/{self.assignment.id}"
        actions = [
            (f"{assignment}/questions/generate", {"replace_existing": True}, "questions"),
            (
                f"{assignment}/reference-answers/generate",
                {"replace_existing": True, "question_part_id": self.question.id},
                "reference_answers",
            ),
            (
                f"{assignment}/rubric/generate",
                {"replace_existing": True, "question_part_id": self.question.id},
                "rubric",
            ),
            (f"/api/submissions/{self.submission.id}/grade", {}, "grade_submission"),
            (f"{assignment}/grade-all", {}, "grade_batch"),
        ]
        with patch("apps.grading.services.openai_client.OpenAI") as provider:
            for path, payload, operation in actions:
                with self.subTest(operation=operation):
                    AIJob.objects.all().delete()
                    response = self.client.post(path, payload, format="json")
                    self.assertEqual(response.status_code, 202, response.data)
                    self.assertEqual(response.data["operation"], operation)
                    self.assertEqual(response.data["state"], "queued")
                    self.assertEqual(response.data["assignment_title"], "Math")
                    self.assertNotIn("input_snapshot", response.data)
                    self.assertNotIn("checkpoint", str(response.data))
                    self.assertEqual(AIJob.objects.get(id=response.data["id"]).owner, self.owner)
            provider.assert_not_called()
        self.assertFalse(LLMUsage.objects.exists())
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.grading_status, "pending")

    def test_known_worker_unavailability_never_admits_work_and_ownership_still_applies(self):
        path = f"/api/submissions/{self.submission.id}/grade"
        with patch("apps.ai_jobs.admission.notify_worker", return_value=False):
            self.assertEqual(self.client.post(path, {}, format="json").status_code, 503)
            self.client.force_authenticate(self.other)
            self.assertEqual(self.client.post(path, {}, format="json").status_code, 404)
        self.assertFalse(AIJob.objects.exists())

    @override_settings(GRAIDER_AI_JOBS_ENABLED=False)
    def test_maintenance_mode_rejects_all_ai_actions_without_sync_fallback(self):
        assignment = f"/api/assignments/{self.assignment.id}"
        paths = [
            f"{assignment}/questions/generate",
            f"{assignment}/reference-answers/generate",
            f"{assignment}/rubric/generate",
            f"/api/submissions/{self.submission.id}/grade",
            f"{assignment}/grade-all",
        ]
        with patch("apps.grading.services.openai_client.OpenAI") as provider:
            for path in paths:
                response = self.client.post(path, {}, format="json")
                self.assertEqual(response.status_code, 503, response.data)
                self.assertIn("maintenance", str(response.data))
                self.client.force_authenticate(self.other)
                self.assertEqual(self.client.post(path, {}, format="json").status_code, 404)
                self.client.force_authenticate(self.owner)
            provider.assert_not_called()
        self.assertFalse(AIJob.objects.exists())
        self.assertFalse(LLMUsage.objects.exists())
        self.assertEqual(self.client.get(assignment).status_code, 200)

    def test_rubric_admission_requires_reference_before_any_job_is_written(self):
        self.question.reference_answer.delete()
        response = self.client.post(
            f"/api/assignments/{self.assignment.id}/rubric/generate",
            {"replace_existing": True},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AIJob.objects.exists())

    def test_action_key_replays_receipt_but_changed_intent_conflicts(self):
        path = f"/api/submissions/{self.submission.id}/grade"
        first = self.client.post(path, {}, format="json", HTTP_IDEMPOTENCY_KEY="lost-response")
        repeat = self.client.post(path, {}, format="json", HTTP_IDEMPOTENCY_KEY="lost-response")
        changed = self.client.post(
            path, {"regrade": True}, format="json", HTTP_IDEMPOTENCY_KEY="lost-response"
        )
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.data["id"], repeat.data["id"])
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(AIJob.objects.count(), 1)

    def test_regrading_is_explicit_and_finalized_results_are_protected(self):
        self.submission.grading_status = "graded"
        self.submission.total_score = 4
        self.submission.save()
        path = f"/api/submissions/{self.submission.id}/grade"
        self.assertEqual(self.client.post(path, {}, format="json").status_code, 409)
        self.assertEqual(self.client.post(path, {"regrade": True}, format="json").status_code, 202)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.total_score, 4)
        AIJob.objects.all().delete()
        self.submission.grading_status = "finalized"
        self.submission.save()
        self.assertEqual(self.client.post(path, {"regrade": True}, format="json").status_code, 409)

    def test_ten_by_ten_batch_uses_background_limits_and_admits_atomically(self):
        for index in range(2, 11):
            self.make_question(f"Q{index}")
            self.make_submission(f"Student {index}")
        response = self.client.post(
            f"/api/assignments/{self.assignment.id}/grade-all", {}, format="json"
        )
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(len(response.data["children"]), 10)
        self.assertEqual(response.data["total_steps"], 110)
        self.assertFalse(LLMUsage.objects.exists())
        AIJob.objects.all().delete()
        self.make_submission("One too many")
        self.assertEqual(
            self.client.post(
                f"/api/assignments/{self.assignment.id}/grade-all", {}, format="json"
            ).status_code,
            400,
        )
        self.assertFalse(AIJob.objects.exists())

    def test_missing_only_and_single_question_scopes_remain_discoverable(self):
        second = self.make_question("Q2")
        second.reference_answer.delete()
        response = self.client.post(
            f"/api/assignments/{self.assignment.id}/reference-answers/generate", {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["question_part_ids"], [second.id])
        self.assertIsNone(response.data["question_part_id"])
        self.assertFalse(response.data["replace_existing"])
        response = self.client.post(
            f"/api/assignments/{self.assignment.id}/rubric/generate",
            {"question_part_id": self.question.id, "replace_existing": True},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["question_part_id"], self.question.id)
        self.assertEqual(response.data["question_part_ids"], [self.question.id])

    def test_active_discovery_finds_paused_jobs_beyond_recent_history(self):
        paused = self.enqueue()
        paused.state = JobState.PAUSED_QUOTA
        paused.save()
        for _ in range(25):
            AIJob.objects.create(
                owner=self.owner,
                assignment=self.assignment,
                operation="questions",
                state="succeeded",
                input_snapshot={},
                input_fingerprint="unused",
                request_fingerprint="unused",
            )
        response = self.client.get("/api/ai/jobs/?active_only=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [str(paused.id)])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/ai/jobs/?active_only=true").data["results"], [])

    def test_session_admission_still_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        path = f"/api/submissions/{self.submission.id}/grade"
        self.assertEqual(client.post(path, {}, format="json").status_code, 403)
        client.get("/api/auth/me")
        response = client.post(
            path, {}, format="json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value
        )
        self.assertEqual(response.status_code, 202)

    def test_first_student_is_visible_through_api_before_batch_finishes(self):
        second = self.make_submission("Student Two")
        response = self.client.post(
            f"/api/assignments/{self.assignment.id}/grade-all", {}, format="json"
        )
        self.assertEqual(response.status_code, 202)

        def provider(**kwargs):
            self.assertFalse(connection.in_atomic_block)
            schema = kwargs["response_format"]
            if schema == SubmissionAnswerMappingSchema:
                data = {
                    "answers": [
                        {"part_key": "Q1", "extracted_answer_text": "4", "mapping_confidence": 0.9}
                    ]
                }
            else:
                self.assertEqual(schema, GeneratedQuestionGradeSchema)
                data = {
                    "criteria": [
                        {
                            "criterion_id": row.id,
                            "score": float(row.max_points),
                            "feedback": "Correct",
                        }
                        for row in self.question.rubric_criteria.all()
                    ],
                    "feedback": "Correct",
                    "reasoning_summary": "Reference and rubric used",
                    "confidence_score": 0.9,
                    "needs_review": False,
                }
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(parsed=schema.model_validate(data), refusal=None)
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                _request_id="test",
            )

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=provider)))
        run_claim(*claim_next(), client=client)
        self.assertFalse(GradingResult.objects.exists())
        run_claim(*claim_next(), client=client)
        self.assertFalse(GradingResult.objects.exists())  # Both mappings remain private.
        run_claim(*claim_next(), client=client)
        self.assertIsNotNone(claim_next())  # Publishes student one, then claims student two.
        rows = self.client.get(f"/api/assignments/{self.assignment.id}/submissions").data
        self.assertEqual(
            next(row for row in rows if row["id"] == self.submission.id)["grading_status"], "graded"
        )
        self.assertEqual(
            next(row for row in rows if row["id"] == second.id)["grading_status"], "pending"
        )
        result = self.client.get(f"/api/submissions/{self.submission.id}/grading").data
        self.assertEqual(len(result["grading_results"][0]["criterion_results"]), 2)
        self.assertNotEqual(
            self.client.get(f"/api/ai/jobs/{response.data['id']}/").data["state"], "succeeded"
        )
