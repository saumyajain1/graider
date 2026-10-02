from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.urls import reverse
from pydantic import ValidationError
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.assignments.models import Assignment, QuestionPart

from .models import GradingResult, ReferenceAnswer, RubricCriterion, StudentSubmission
from .services.generation import generate_question_parts
from .services.schemas import GeneratedQuestionSetSchema
from .services.submission_workflow import (
    SubmissionNotReadyError,
    run_grading_pipeline,
    validate_submission_ready_for_grading,
)


class MarksWorkflowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="marks@example.com", password="test-only")
        self.client.force_authenticate(self.user)
        self.assignment = Assignment.objects.create(
            teacher=self.user,
            title="Biology",
            raw_assignment_text="Total: 8 marks.\n1.1 Define osmosis.\n1.2 Explain its effect on cells.",
        )
        self.question = QuestionPart.objects.create(
            assignment=self.assignment, part_key="Q1", text="Define osmosis.", max_marks=5
        )
        self.submission = StudentSubmission.objects.create(
            assignment=self.assignment, student_name="Test Student", raw_response_text="Osmosis."
        )
        ReferenceAnswer.objects.create(
            question_part=self.question, answer_text="A reference answer."
        )
        self.criterion = RubricCriterion.objects.create(
            question_part=self.question,
            title="Accuracy",
            description="Defines osmosis.",
            max_points=5,
        )

    def test_question_total_is_required_and_positive_but_context_is_unscored(self):
        url = reverse("question-list", args=[self.assignment.id])
        for marks in (None, "0", "-1", "1.234"):
            with self.subTest(marks=marks):
                response = self.client.post(
                    url, {"text": "Explain diffusion.", "max_marks": marks}, format="json"
                )
                self.assertEqual(response.status_code, 400)
        response = self.client.post(
            url, {"text": "Given a cell.", "part_type": "context", "max_marks": "5"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["max_marks"])

    def test_question_number_and_group_can_be_cleared(self):
        self.question.source_label = "1.1"
        self.question.parent_key = "1"
        self.question.save()
        response = self.client.patch(
            reverse("question-detail", args=[self.question.id]),
            {"source_label": "", "parent_key": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["parent_key"], "")
        self.assertEqual(response.data["display_label"], "Q1")

    def test_unmarked_structured_assignment_uses_whole_assignment_ai_prompt(self):
        proposed = GeneratedQuestionSetSchema(
            parts=[
                {"text": "Define osmosis.", "max_marks": 3, "source_label": "1.1"},
                {"text": "Explain its effect on cells.", "max_marks": 5, "source_label": "1.2"},
            ]
        )
        with patch("apps.grading.services.generation.OpenAIChatService") as service:
            parse = service.return_value.parse
            parse.return_value = proposed
            result = generate_question_parts(self.assignment)
        self.assertEqual(sum(part.max_marks for part in result.parts), 8)
        self.assertIn(self.assignment.raw_assignment_text, parse.call_args.kwargs["user_prompt"])
        self.assertIn("distribute its remaining marks", parse.call_args.kwargs["system_prompt"])

    def test_generated_questions_reject_missing_zero_and_nonfinite_totals(self):
        for marks in (None, 0, -1, float("nan"), float("inf"), 1.234):
            with self.subTest(marks=marks), self.assertRaises(ValidationError):
                GeneratedQuestionSetSchema(parts=[{"text": "Question", "max_marks": marks}])

    @patch("apps.grading.services.submission_workflow.map_submission_answers")
    def test_grading_rejects_missing_or_zero_marks_before_provider_call(self, mapping):
        for marks in (None, Decimal("0")):
            self.question.max_marks = marks
            self.question.save()
            with (
                self.subTest(marks=marks),
                self.assertRaisesMessage(SubmissionNotReadyError, "positive total marks"),
            ):
                run_grading_pipeline(self.submission)
        mapping.assert_not_called()
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.grading_status, "pending")

    def test_grading_rejects_rubric_mismatch_and_empty_reference(self):
        self.criterion.max_points = 4
        self.criterion.save()
        with self.assertRaisesMessage(SubmissionNotReadyError, "must total 5.00"):
            validate_submission_ready_for_grading(self.submission)
        self.criterion.max_points = 5
        self.criterion.save()
        ReferenceAnswer.objects.filter(question_part=self.question).update(answer_text=" ")
        with self.assertRaisesMessage(SubmissionNotReadyError, "Missing reference answers"):
            validate_submission_ready_for_grading(self.submission)

    @patch("apps.grading.views.generate_rubric_criteria")
    def test_invalid_ai_rubric_preserves_existing_criteria(self, generate):
        generate.return_value = SimpleNamespace(
            criteria=[SimpleNamespace(title="Wrong", description="Wrong total", max_points=4)]
        )
        response = self.client.post(
            reverse("rubric-generate", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 502)
        self.assertTrue(RubricCriterion.objects.filter(pk=self.criterion.pk).exists())

    @patch("apps.grading.views.generate_rubric_criteria")
    def test_rubric_generation_rejects_missing_total_before_ai(self, generate):
        self.question.max_marks = None
        self.question.save()
        response = self.client.post(
            reverse("rubric-generate", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        generate.assert_not_called()

    def test_manual_criteria_reject_nonpositive_points_and_context_targets(self):
        url = reverse("rubric-list", args=[self.assignment.id])
        payload = {
            "question_part_id": self.question.id,
            "title": "Accuracy",
            "description": "Description",
            "max_points": "0",
        }
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 400)
        self.assertEqual(
            self.client.patch(
                reverse("rubric-criterion-detail", args=[self.criterion.id]),
                {"max_points": "0"},
                format="json",
            ).status_code,
            400,
        )
        context = QuestionPart.objects.create(
            assignment=self.assignment, part_key="Context", text="Setup", part_type="context"
        )
        payload.update(question_part_id=context.id, max_points="1")
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 400)
        self.assertEqual(
            self.client.post(
                reverse("reference-answer-list", args=[self.assignment.id]),
                {"question_part_id": context.id, "answer_text": "Answer"},
                format="json",
            ).status_code,
            400,
        )

    def test_csv_export_preserves_zero_total(self):
        self.submission.total_score = 0
        self.submission.grading_status = "graded"
        self.submission.save()
        GradingResult.objects.create(
            submission=self.submission,
            question_part=self.question,
            max_score=5,
            ai_score=0,
            final_score=None,
        )
        response = self.client.get(reverse("assignment-export-csv", args=[self.assignment.id]))
        import csv
        from io import StringIO

        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual(rows[0]["total_score"], "0.00")
        self.assertEqual(rows[0]["Q1_score"], "0.00")
