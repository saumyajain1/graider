from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.ai_jobs.models import AIJob
from apps.ai_jobs.test_helpers import JobExecutionMixin
from apps.assignments.models import Assignment, QuestionPart

from . import test_criterion_grading as criterion_tests
from .models import ReferenceAnswer, RubricCriterion
from .services.openai_client import LLMGenerationError


class ReviewCompletionTests(JobExecutionMixin, APITestCase):
    def setUp(self):
        super().setUp()
        criterion_tests.CriterionGradingTests.setup_fixture(self)
        self.finalize_url = reverse("submission-finalize", args=[self.submission.pk])

    def save_review(self, scores=("1.00", "2.00"), flagged=False):
        payload = criterion_tests.CriterionGradingTests.review_payload(self, scores)
        payload["needs_review"] = flagged
        return self.client.patch(self.url, payload, format="json")

    def test_finalize_rejects_ungraded_and_partial_results(self):
        self.assertEqual(self.client.post(self.finalize_url).status_code, 400)
        self.assertEqual(self.save_review(("1.00", None)).status_code, 200)
        self.assertEqual(self.client.post(self.finalize_url).status_code, 400)
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.finalized_at)

    def test_finalize_requires_cleared_flags_and_preserves_rejected_state(self):
        self.assertEqual(self.save_review(flagged=True).status_code, 200)
        result = self.client.post(self.finalize_url)
        self.assertEqual(result.status_code, 400)
        self.assertIn("flags", result.json()["detail"])
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.grading_status, "reviewed")
        self.assertIsNone(self.submission.finalized_at)
        self.assertEqual(self.save_review().status_code, 200)
        self.assertEqual(self.client.post(self.finalize_url).status_code, 200)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.total_score, Decimal("3.00"))
        finalized = self.submission.finalized_at
        self.assertEqual(self.client.post(self.finalize_url).status_code, 200)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.finalized_at, finalized)

    def test_editing_finalized_review_clears_completion_timestamp(self):
        self.save_review()
        self.client.post(self.finalize_url)
        self.assertEqual(self.save_review(("0.00", "0.00")).status_code, 200)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.grading_status, "reviewed")
        self.assertIsNone(self.submission.finalized_at)
        self.assertEqual(self.submission.total_score, 0)

    def test_finalize_rejects_grading_and_other_teachers(self):
        self.submission.grading_status = "grading"
        self.submission.save()
        self.assertEqual(self.client.post(self.finalize_url).status_code, 409)
        other = self.teacher.__class__.objects.create_user(email="other@example.com")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(self.finalize_url).status_code, 404)

    def test_finalize_rejects_missing_question_and_invalid_snapshot(self):
        self.save_review()
        second = QuestionPart.objects.create(
            assignment=self.assignment, part_key="Q2", text="Other", max_marks=1
        )
        self.assertEqual(self.client.post(self.finalize_url).status_code, 400)
        second.delete()
        result = self.submission.grading_results.get()
        result.criterion_results[0]["final_score"] = "NaN"
        result.save()
        self.assertEqual(self.client.post(self.finalize_url).status_code, 400)
        result.criterion_results[0]["final_score"] = "10.00"
        result.save()
        self.assertEqual(self.client.post(self.finalize_url).status_code, 400)


class SetupAndReplacementTests(JobExecutionMixin, APITestCase):
    def setUp(self):
        super().setUp()
        criterion_tests.CriterionGradingTests.setup_fixture(self)

    def test_failed_bulk_replacement_keeps_every_existing_answer(self):
        saved = self.question.reference_answer.answer_text
        second = QuestionPart.objects.create(
            assignment=self.assignment, part_key="Q2", text="Other", max_marks=1
        )
        ReferenceAnswer.objects.create(question_part=second, answer_text="Second teacher answer")
        replies = iter(
            [{"answer_text": "First replacement"}, LLMGenerationError("Synthetic provider failure")]
        )

        def provider(**kwargs):
            output = next(replies)
            if isinstance(output, Exception):
                raise output
            return output

        self.ai_outputs["reference_answer"] = provider
        response = self.client.post(
            reverse("reference-answer-generate", args=[self.assignment.pk]),
            {"replace_existing": True},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        self.assertEqual(AIJob.objects.get(id=response.data["id"]).state, "failed")
        self.assertEqual(self.ai_provider.call_count, 2)
        self.assertEqual(
            ReferenceAnswer.objects.get(question_part=self.question).answer_text, saved
        )
        self.assertEqual(
            ReferenceAnswer.objects.get(question_part=second).answer_text, "Second teacher answer"
        )

    def test_badges_follow_valid_marks_answers_and_rubric(self):
        self.assertEqual(
            self.assignment.workflow_status, Assignment.WorkflowStatus.SUBMISSIONS_UPLOADED
        )
        self.criteria[0].max_points = 1
        self.criteria[0].save()
        self.assertEqual(
            self.assignment.workflow_status, Assignment.WorkflowStatus.REFERENCE_ANSWERS_READY
        )
        self.question.reference_answer.delete()
        self.assertEqual(self.assignment.workflow_status, Assignment.WorkflowStatus.QUESTIONS_READY)
        self.question.max_marks = None
        self.question.save()
        self.assertEqual(self.assignment.workflow_status, Assignment.WorkflowStatus.DRAFT)

    def test_blank_reference_and_empty_criterion_description_are_not_ready(self):
        answer = self.question.reference_answer
        answer.answer_text = " "
        answer.save()
        self.assertEqual(self.assignment.workflow_status, "questions_ready")
        answer.answer_text = "Reference"
        answer.save()
        self.criteria[0].description = " "
        self.criteria[0].save()
        self.assertEqual(self.assignment.workflow_status, "reference_answers_ready")
        self.submission.grading_status = "finalized"
        self.submission.save()
        self.assertEqual(self.assignment.workflow_status, "reference_answers_ready")

    def test_answer_generation_fills_missing_and_requires_explicit_replacement(self):
        url = reverse("reference-answer-generate", args=[self.assignment.pk])
        saved = self.question.reference_answer.answer_text
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)
        self.ai_provider.assert_not_called()
        missing = QuestionPart.objects.create(
            assignment=self.assignment, part_key="Q2", text="Other", max_marks=1
        )
        self.ai_outputs["reference_answer"] = {"answer_text": "New AI answer"}
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        self.assertEqual(self.ai_provider.call_count, 1)
        self.assertEqual(
            ReferenceAnswer.objects.get(question_part=self.question).answer_text, saved
        )
        self.assertEqual(
            ReferenceAnswer.objects.get(question_part=missing).answer_text, "New AI answer"
        )
        self.assertEqual(
            self.client.post(
                url, {"question_part_id": self.question.pk, "replace_existing": True}, format="json"
            ).status_code,
            202,
        )
        self.drain_jobs()
        self.assertEqual(
            ReferenceAnswer.objects.get(question_part=self.question).answer_text, "New AI answer"
        )

    def test_rubric_generation_preserves_existing_without_confirmation(self):
        url = reverse("rubric-generate", args=[self.assignment.pk])
        ids = list(self.question.rubric_criteria.values_list("id", flat=True))
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)
        self.ai_provider.assert_not_called()
        self.ai_outputs["rubric_generation"] = {
            "criteria": [{"title": "New", "description": "New rubric", "max_points": 5}]
        }
        response = self.client.post(
            url, {"question_part_id": self.question.pk, "replace_existing": True}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        self.assertNotEqual(list(self.question.rubric_criteria.values_list("id", flat=True)), ids)
        self.assertEqual(self.question.rubric_criteria.get().title, "New")

    def test_teacher_answer_added_during_ai_call_is_preserved(self):
        self.question.reference_answer.delete()

        def provider(**kwargs):
            ReferenceAnswer.objects.create(
                question_part=self.question, answer_text="Teacher added during generation"
            )
            return {"answer_text": "Late AI answer"}

        self.ai_outputs["reference_answer"] = provider
        response = self.client.post(
            reverse("reference-answer-generate", args=[self.assignment.pk]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        self.assertEqual(AIJob.objects.get(id=response.data["id"]).state, "superseded")
        self.assertEqual(
            ReferenceAnswer.objects.get(question_part=self.question).answer_text,
            "Teacher added during generation",
        )

    def test_teacher_rubric_added_during_ai_call_is_preserved(self):
        self.question.rubric_criteria.all().delete()

        def provider(**kwargs):
            RubricCriterion.objects.create(
                question_part=self.question,
                title="Teacher criterion",
                description="Entered while generating",
                max_points=5,
            )
            return {"criteria": [{"title": "Late AI", "description": "AI", "max_points": 5}]}

        self.ai_outputs["rubric_generation"] = provider
        response = self.client.post(
            reverse("rubric-generate", args=[self.assignment.pk]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        self.assertEqual(AIJob.objects.get(id=response.data["id"]).state, "superseded")
        self.assertEqual(self.question.rubric_criteria.get().title, "Teacher criterion")
