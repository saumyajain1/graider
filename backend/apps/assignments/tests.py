from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from reportlab.pdfgen import canvas
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import Assignment, QuestionPart


def build_pdf(text):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 750, text)
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


class AssignmentApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="teacher@example.com",
            full_name="Teacher",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            full_name="Other",
            password="StrongPass123!",
        )
        self.client.force_authenticate(self.user)

    def test_assignment_list_is_scoped_to_teacher(self):
        own_assignment = Assignment.objects.create(
            teacher=self.user,
            title="Owned Assignment",
            raw_assignment_text="Question 1",
        )
        Assignment.objects.create(
            teacher=self.other_user,
            title="Hidden Assignment",
            raw_assignment_text="Question 2",
        )

        response = self.client.get(reverse("assignment-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], own_assignment.id)

    def test_other_teacher_cannot_read_or_change_assignment_and_questions(self):
        other_assignment = Assignment.objects.create(
            teacher=self.other_user,
            title="Private Assignment",
            raw_assignment_text="Private question",
        )
        other_question = QuestionPart.objects.create(
            assignment=other_assignment,
            part_key="Q1",
            text="Private question",
            display_order=0,
        )

        for response in (
            self.client.get(reverse("assignment-detail", args=[other_assignment.id])),
            self.client.patch(
                reverse("assignment-detail", args=[other_assignment.id]),
                {"title": "Changed"},
                format="json",
            ),
            self.client.get(reverse("question-list", args=[other_assignment.id])),
            self.client.patch(
                reverse("question-detail", args=[other_question.id]),
                {"text": "Changed"},
                format="json",
            ),
        ):
            self.assertEqual(response.status_code, 404)

        other_assignment.refresh_from_db()
        other_question.refresh_from_db()
        self.assertEqual(other_assignment.title, "Private Assignment")
        self.assertEqual(other_question.text, "Private question")

    def test_create_assignment_from_raw_text(self):
        response = self.client.post(
            reverse("assignment-list"),
            {
                "title": "Midterm Essay",
                "course_name": "English 101",
                "description": "Short-answer and essay questions.",
                "raw_assignment_text": "1. Compare two themes from the novel.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        assignment = Assignment.objects.get()
        self.assertEqual(assignment.raw_assignment_text, "1. Compare two themes from the novel.")

    def test_create_assignment_from_txt_upload_extracts_text(self):
        upload = SimpleUploadedFile(
            "assignment.txt",
            b"Question 1: Explain osmosis.",
            content_type="text/plain",
        )

        response = self.client.post(
            reverse("assignment-list"),
            {
                "title": "Biology Quiz",
                "source_file": upload,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        assignment = Assignment.objects.get()
        self.assertEqual(assignment.raw_assignment_text, "Question 1: Explain osmosis.")

    def test_create_assignment_from_pdf_upload_extracts_text(self):
        upload = SimpleUploadedFile(
            "assignment.pdf",
            build_pdf("Question 1: Define opportunity cost."),
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("assignment-list"),
            {
                "title": "Economics Quiz",
                "source_file": upload,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        assignment = Assignment.objects.get()
        self.assertIn("Question 1: Define opportunity cost.", assignment.raw_assignment_text)

    def test_create_assignment_rejects_unsupported_upload(self):
        upload = SimpleUploadedFile(
            "assignment.docx",
            b"Question 1",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        response = self.client.post(
            reverse("assignment-list"),
            {
                "title": "Unsupported Upload",
                "source_file": upload,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Assignment.objects.count(), 0)
        self.assertIn("source_file", response.data)

    def test_question_create_update_reorder_and_delete(self):
        assignment = Assignment.objects.create(
            teacher=self.user,
            title="History Paper",
            raw_assignment_text="Question 1",
        )
        question_list_url = reverse("question-list", args=[assignment.id])

        first = self.client.post(
            question_list_url,
            {
                "text": "Explain the main cause of the revolution.",
                "max_marks": "5",
            },
            format="json",
        )
        second = self.client.post(
            question_list_url,
            {
                "text": "Name one major outcome.",
                "max_marks": "3",
            },
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        update_response = self.client.patch(
            reverse("question-detail", args=[first.data["id"]]),
            {"text": "Explain two causes of the revolution.", "max_marks": "6"},
            format="json",
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data["text"], "Explain two causes of the revolution.")

        reorder_response = self.client.post(
            reverse("question-reorder", args=[assignment.id]),
            {"question_ids": [second.data["id"], first.data["id"]]},
            format="json",
        )
        self.assertEqual(reorder_response.status_code, 200)
        self.assertEqual(reorder_response.data[0]["id"], second.data["id"])

        delete_response = self.client.delete(reverse("question-detail", args=[first.data["id"]]))
        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(QuestionPart.objects.count(), 1)
        self.assertEqual(QuestionPart.objects.first().source_label, "Q2")

    def test_assignment_delete_removes_teacher_owned_assignment(self):
        assignment = Assignment.objects.create(
            teacher=self.user,
            title="Delete Me",
            raw_assignment_text="Question 1",
        )

        response = self.client.delete(reverse("assignment-detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Assignment.objects.filter(id=assignment.id).exists())

    @patch("apps.assignments.views.generate_question_parts")
    def test_generate_questions_with_mocked_llm(self, generate_question_parts_mock):
        assignment = Assignment.objects.create(
            teacher=self.user,
            title="Generated Questions",
            raw_assignment_text="1. Explain osmosis.\n2. Give an example.",
        )
        generate_question_parts_mock.return_value = SimpleNamespace(
            parts=[
                SimpleNamespace(
                    part_type="question",
                    source_label="1.1",
                    text="Explain osmosis.",
                    max_marks=5,
                    parent_key=None,
                ),
                SimpleNamespace(
                    part_type="question",
                    source_label="1.2",
                    text="Give an example.",
                    max_marks=3,
                    parent_key=None,
                ),
            ]
        )

        response = self.client.post(
            reverse("question-generate", args=[assignment.id]),
            {"replace_existing": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(QuestionPart.objects.filter(assignment=assignment).count(), 2)
        self.assertTrue(all(item["created_by_ai"] for item in response.data))
        self.assertEqual(response.data[0]["source_label"], "1.1")
        self.assertEqual(response.data[1]["source_label"], "1.2")

    @patch("apps.assignments.views.generate_question_parts")
    def test_question_generation_surfaces_llm_failures(self, generate_question_parts_mock):
        from apps.grading.services import LLMGenerationError

        assignment = Assignment.objects.create(
            teacher=self.user,
            title="Failed Generation",
            raw_assignment_text="1. Explain osmosis.",
        )
        generate_question_parts_mock.side_effect = LLMGenerationError("Malformed model output.")

        response = self.client.post(
            reverse("question-generate", args=[assignment.id]),
            {"replace_existing": True},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["detail"], "AI request failed. Please try again.")
