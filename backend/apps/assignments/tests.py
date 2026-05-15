from io import BytesIO
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
