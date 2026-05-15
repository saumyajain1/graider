from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.assignments.models import Assignment, QuestionPart

from .models import ReferenceAnswer, RubricCriterion


class GradingArtifactApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="grader@example.com",
            full_name="Grader",
            password="StrongPass123!",
        )
        self.client.force_authenticate(self.user)
        self.assignment = Assignment.objects.create(
            teacher=self.user,
            title="Mocked Artifact Assignment",
            raw_assignment_text="1. Explain osmosis.",
        )
        self.question = QuestionPart.objects.create(
            assignment=self.assignment,
            part_key="Q1",
            text="Explain osmosis.",
            max_marks="5",
            display_order=0,
        )

    @patch("apps.grading.views.generate_reference_answer")
    def test_generate_reference_answers_with_mocked_llm(self, generate_reference_answer_mock):
        generate_reference_answer_mock.return_value.answer_text = "A strong answer defines osmosis."

        response = self.client.post(
            reverse("reference-answer-generate", args=[self.assignment.id]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ReferenceAnswer.objects.count(), 1)
        self.assertEqual(response.data[0]["answer_text"], "A strong answer defines osmosis.")

    @patch("apps.grading.views.generate_reference_answer")
    def test_reference_answer_generation_surfaces_llm_failures(self, generate_reference_answer_mock):
        from apps.grading.services import LLMGenerationError

        generate_reference_answer_mock.side_effect = LLMGenerationError("Malformed model output.")

        response = self.client.post(
            reverse("reference-answer-generate", args=[self.assignment.id]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["detail"], "Malformed model output.")

    def test_manual_reference_answer_create_and_patch(self):
        create_response = self.client.post(
            reverse("reference-answer-list", args=[self.assignment.id]),
            {"question_part_id": self.question.id, "answer_text": "Manual answer text."},
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        answer_id = create_response.data["id"]

        patch_response = self.client.patch(
            reverse("reference-answer-detail", args=[answer_id]),
            {"answer_text": "Edited manual answer."},
            format="json",
        )

        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data["answer_text"], "Edited manual answer.")

    @patch("apps.grading.views.generate_rubric_criteria")
    def test_generate_rubric_with_mocked_llm(self, generate_rubric_mock):
        ReferenceAnswer.objects.create(
            question_part=self.question,
            answer_text="Reference answer",
            source=ReferenceAnswer.Source.TEACHER,
        )
        generate_rubric_mock.return_value.criteria = [
            type(
                "Criterion",
                (),
                {"title": "Core concept", "description": "Defines osmosis correctly.", "max_points": 3},
            )(),
            type(
                "Criterion",
                (),
                {"title": "Example", "description": "Gives a sensible example.", "max_points": 2},
            )(),
        ]

        response = self.client.post(
            reverse("rubric-generate", args=[self.assignment.id]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RubricCriterion.objects.count(), 2)
        self.assertEqual(response.data[0]["criteria"][0]["title"], "Core concept")

    def test_manual_rubric_create_patch_and_delete(self):
        create_response = self.client.post(
            reverse("rubric-list", args=[self.assignment.id]),
            {
                "question_part_id": self.question.id,
                "title": "Accuracy",
                "description": "Matches the scientific definition.",
                "max_points": "5",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        criterion_id = create_response.data["id"]

        patch_response = self.client.patch(
            reverse("rubric-criterion-detail", args=[criterion_id]),
            {"description": "Matches the correct scientific definition."},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)

        delete_response = self.client.delete(reverse("rubric-criterion-detail", args=[criterion_id]))
        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(RubricCriterion.objects.count(), 0)
