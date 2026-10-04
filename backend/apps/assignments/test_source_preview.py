import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import Assignment


class ReplacementSourceTests(APITestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = override_settings(MEDIA_ROOT=self.directory.name)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.user = User.objects.create_user(email="files@example.com")
        self.client.force_authenticate(self.user)
        self.assignment = Assignment.objects.create(
            teacher=self.user, title="Assignment", raw_assignment_text="Edited biology text"
        )
        self.url = reverse("assignment-detail", args=[self.assignment.pk])
        self.preview = reverse("assignment-source-preview", args=[self.assignment.pk])

    def upload(self):
        return SimpleUploadedFile(
            "chemistry.txt", b"New chemistry questions", content_type="text/plain"
        )

    def test_preview_does_not_replace_saved_file_or_text(self):
        response = self.client.post(
            self.preview, {"source_file": self.upload()}, format="multipart"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["extracted_text"], "New chemistry questions")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.raw_assignment_text, "Edited biology text")
        self.assertFalse(self.assignment.source_file)

    def test_explicit_file_choice_overrides_submitted_old_text(self):
        response = self.client.patch(
            self.url,
            {
                "source_file": self.upload(),
                "raw_assignment_text": "Edited biology text",
                "source_text_mode": "file",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.raw_assignment_text, "New chemistry questions")

    def test_keep_text_choice_preserves_teacher_edits(self):
        response = self.client.patch(
            self.url,
            {
                "source_file": self.upload(),
                "raw_assignment_text": "Keep these edits",
                "source_text_mode": "text",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.raw_assignment_text, "Keep these edits")
        self.assertEqual(self.assignment.source_original_filename, "chemistry.txt")

    def test_empty_extraction_and_missing_file_are_rejected(self):
        response = self.client.post(
            self.preview, {"source_file": SimpleUploadedFile("empty.txt", b" ")}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.patch(self.url, {"source_text_mode": "file"}, format="json").status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                self.url,
                {"source_file": self.upload(), "source_text_mode": "text"},
                format="multipart",
            ).status_code,
            400,
        )

    def test_preview_checks_type_size_and_teacher_access(self):
        with override_settings(GRAIDER_MAX_UPLOAD_BYTES=2):
            self.assertEqual(
                self.client.post(
                    self.preview, {"source_file": self.upload()}, format="multipart"
                ).status_code,
                413,
            )
        self.assertEqual(
            self.client.post(
                self.preview,
                {"source_file": SimpleUploadedFile("bad.csv", b"hello")},
                format="multipart",
            ).status_code,
            400,
        )
        self.client.force_authenticate(User.objects.create_user(email="other-files@example.com"))
        self.assertEqual(
            self.client.post(
                self.preview, {"source_file": self.upload()}, format="multipart"
            ).status_code,
            404,
        )
