from io import BytesIO
from unittest.mock import patch

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from reportlab.pdfgen import canvas
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.assignments.models import Assignment
from apps.grading.models import StudentSubmission, SubmissionImport

PRIVATE_TEST_STORAGE = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def pdf_with_pages(count):
    buffer = BytesIO()
    document = canvas.Canvas(buffer)
    for page in range(count):
        document.drawString(100, 750, f"Page {page + 1}")
        document.showPage()
    document.save()
    return buffer.getvalue()


@override_settings(STORAGES=PRIVATE_TEST_STORAGE)
class PrivateUploadTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            email="owner@example.com", full_name="Owner", password="StrongPass123!"
        )
        self.other = User.objects.create_user(
            email="stranger@example.com", full_name="Stranger", password="StrongPass123!"
        )
        self.client.force_authenticate(self.teacher)

    def make_assignment(self):
        return Assignment.objects.create(
            teacher=self.teacher, title="Biology", raw_assignment_text="Explain osmosis."
        )

    def test_assignment_file_keeps_original_name_and_requires_owner(self):
        response = self.client.post(
            reverse("assignment-list"),
            {
                "title": "Biology",
                "source_file": SimpleUploadedFile("my questions.txt", b"Explain osmosis."),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        assignment = Assignment.objects.get(pk=response.data["id"])
        self.assertEqual(response.data["source_filename"], "my questions.txt")
        self.assertTrue(default_storage.exists(assignment.source_file.name))
        url = response.data["source_file_url"]
        self.assertEqual(b"".join(self.client.get(url).streaming_content), b"Explain osmosis.")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(f"/media/{assignment.source_file.name}").status_code, 404)

    def test_replacing_assignment_file_removes_old_object_after_commit(self):
        response = self.client.post(
            reverse("assignment-list"),
            {"title": "Biology", "source_file": SimpleUploadedFile("first.txt", b"First question")},
            format="multipart",
        )
        assignment = Assignment.objects.get(pk=response.data["id"])
        old_name = assignment.source_file.name
        with self.captureOnCommitCallbacks(execute=True):
            updated = self.client.patch(
                reverse("assignment-detail", args=[assignment.id]),
                {"source_file": SimpleUploadedFile("second.txt", b"Second question")},
                format="multipart",
            )
        self.assertEqual(updated.status_code, 200)
        assignment.refresh_from_db()
        self.assertFalse(default_storage.exists(old_name))
        self.assertTrue(default_storage.exists(assignment.source_file.name))
        self.assertEqual(updated.data["source_filename"], "second.txt")

    def test_deleting_assignment_removes_all_originals_after_commit(self):
        assignment = self.make_assignment()
        upload = self.client.post(
            reverse("submission-list", args=[assignment.id]),
            {"student_name": "Alex", "response_file": SimpleUploadedFile("alex.txt", b"Answer")},
            format="multipart",
        )
        submission_name = StudentSubmission.objects.get(pk=upload.data["id"]).response_file.name
        self.assertTrue(default_storage.exists(submission_name))
        with self.captureOnCommitCallbacks(execute=True):
            deleted = self.client.delete(reverse("assignment-detail", args=[assignment.id]))
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(default_storage.exists(submission_name))

    def test_submission_and_csv_originals_are_private_and_retrievable(self):
        assignment = self.make_assignment()
        submission_response = self.client.post(
            reverse("submission-list", args=[assignment.id]),
            {
                "student_name": "Alex",
                "response_file": SimpleUploadedFile("alex.txt", b"Water moves."),
            },
            format="multipart",
        )
        self.assertEqual(submission_response.status_code, 201)
        submission = StudentSubmission.objects.get()
        self.assertTrue(default_storage.exists(submission.response_file.name))
        self.assertEqual(submission_response.data["response_filename"], "alex.txt")
        response_url = submission_response.data["response_file_url"]
        self.assertEqual(b"".join(self.client.get(response_url).streaming_content), b"Water moves.")

        csv_response = self.client.post(
            reverse("submission-import-csv", args=[assignment.id]),
            {
                "file": SimpleUploadedFile(
                    "class list.csv", b"student_name,response_text\nBob,Answer two\n"
                )
            },
            format="multipart",
        )
        self.assertEqual(csv_response.status_code, 201)
        csv_import = SubmissionImport.objects.get()
        self.assertEqual(csv_import.original_filename, "class list.csv")
        self.assertTrue(default_storage.exists(csv_import.source_file.name))
        imports = self.client.get(reverse("submission-import-list", args=[assignment.id])).data
        self.assertEqual(imports[0]["row_count"], 1)
        csv_url = imports[0]["source_file_url"]
        self.assertIn(b"Bob,Answer two", b"".join(self.client.get(csv_url).streaming_content))

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(response_url).status_code, 404)
        self.assertEqual(self.client.get(csv_url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("submission-import-list", args=[assignment.id])).status_code,
            404,
        )

    @override_settings(GRAIDER_MAX_UPLOAD_BYTES=10)
    def test_oversized_assignment_file_returns_413_without_storage(self):
        response = self.client.post(
            reverse("assignment-list"),
            {"title": "Too big", "source_file": SimpleUploadedFile("large.txt", b"a" * 11)},
            format="multipart",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(Assignment.objects.count(), 0)

    @override_settings(GRAIDER_MAX_PDF_PAGES=1)
    def test_pdf_page_limit_returns_413(self):
        response = self.client.post(
            reverse("assignment-list"),
            {
                "title": "Too many pages",
                "source_file": SimpleUploadedFile("pages.pdf", pdf_with_pages(2)),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(Assignment.objects.count(), 0)

    @override_settings(GRAIDER_MAX_ASSIGNMENT_CHARS=5)
    def test_assignment_text_limit_returns_413(self):
        response = self.client.post(
            reverse("assignment-list"),
            {"title": "Too long", "raw_assignment_text": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 413)

    @override_settings(GRAIDER_MAX_ASSIGNMENT_CHARS=5)
    def test_extracted_pdf_text_limit_returns_413(self):
        response = self.client.post(
            reverse("assignment-list"),
            {
                "title": "Too much PDF text",
                "source_file": SimpleUploadedFile("long.pdf", pdf_with_pages(1)),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(Assignment.objects.count(), 0)

    @override_settings(GRAIDER_MAX_RESPONSE_CHARS=5)
    def test_submission_text_limit_returns_413(self):
        assignment = self.make_assignment()
        response = self.client.post(
            reverse("submission-list", args=[assignment.id]),
            {"student_name": "Alex", "raw_response_text": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(StudentSubmission.objects.count(), 0)

    @override_settings(GRAIDER_MAX_CSV_BYTES=20)
    def test_csv_byte_limit_returns_413(self):
        assignment = self.make_assignment()
        response = self.client.post(
            reverse("submission-import-csv", args=[assignment.id]),
            {
                "file": SimpleUploadedFile(
                    "roster.csv", b"student_name,response_text\nAlex,Answer\n"
                )
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(SubmissionImport.objects.count(), 0)

    @override_settings(GRAIDER_MAX_CSV_ROWS=1)
    def test_csv_row_limit_returns_413(self):
        assignment = self.make_assignment()
        response = self.client.post(
            reverse("submission-import-csv", args=[assignment.id]),
            {
                "file": SimpleUploadedFile(
                    "roster.csv", b"student_name,response_text\nA,One\nB,Two\n"
                )
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(StudentSubmission.objects.count(), 0)

    @override_settings(GRAIDER_MAX_SUBMISSIONS_PER_ASSIGNMENT=1)
    def test_submission_count_limit_returns_413_and_cleans_object(self):
        assignment = self.make_assignment()
        StudentSubmission.objects.create(assignment=assignment, student_name="Existing")
        prefix = f"submissions/{self.teacher.id}/{assignment.id}"
        before = (
            set(default_storage.listdir(prefix)[1]) if default_storage.exists(prefix) else set()
        )
        response = self.client.post(
            reverse("submission-list", args=[assignment.id]),
            {"student_name": "New", "response_file": SimpleUploadedFile("new.txt", b"Answer")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(StudentSubmission.objects.count(), 1)
        self.assertEqual(set(default_storage.listdir(prefix)[1]), before)

    def test_csv_database_failure_cleans_uploaded_object(self):
        assignment = self.make_assignment()
        prefix = f"imports/{self.teacher.id}/{assignment.id}"
        before = (
            set(default_storage.listdir(prefix)[1]) if default_storage.exists(prefix) else set()
        )
        with patch.object(
            StudentSubmission.objects, "bulk_create", side_effect=RuntimeError("DB failure")
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("submission-import-csv", args=[assignment.id]),
                    {
                        "file": SimpleUploadedFile(
                            "roster.csv", b"student_name,response_text\nA,One\n"
                        )
                    },
                    format="multipart",
                )
        self.assertEqual(SubmissionImport.objects.count(), 0)
        self.assertEqual(set(default_storage.listdir(prefix)[1]), before)

    def test_storage_failure_cleans_partially_written_object(self):
        original_save = default_storage.save
        saved_names = []

        def fail_after_save(name, content, **kwargs):
            saved_names.append(original_save(name, content, **kwargs))
            raise RuntimeError("Storage response failed")

        with patch.object(default_storage, "save", side_effect=fail_after_save):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("assignment-list"),
                    {
                        "title": "Biology",
                        "source_file": SimpleUploadedFile("test.txt", b"Question"),
                    },
                    format="multipart",
                )
        self.assertEqual(Assignment.objects.count(), 0)
        self.assertEqual(len(saved_names), 1)
        self.assertFalse(default_storage.exists(saved_names[0]))

    def test_private_storage_uses_short_lived_signed_redirect(self):
        assignment = self.make_assignment()
        assignment.source_file = "assignments/example.txt"
        assignment.source_original_filename = "original.txt"
        assignment.save()
        storage_settings = {
            **PRIVATE_TEST_STORAGE,
            "default": {
                "BACKEND": "storages.backends.s3.S3Storage",
                "OPTIONS": {
                    "access_key": "test",
                    "secret_key": "test",
                    "bucket_name": "uploads",
                    "endpoint_url": "https://example.invalid",
                    "region_name": "us-east-2",
                    "addressing_style": "path",
                    "signature_version": "s3v4",
                    "querystring_auth": True,
                    "querystring_expire": 60,
                },
            },
        }
        with override_settings(STORAGES=storage_settings):
            with patch(
                "storages.backends.s3.S3Storage.url", return_value="https://signed.example/file"
            ) as url_mock:
                response = self.client.get(reverse("assignment-source-file", args=[assignment.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://signed.example/file")
        self.assertEqual(url_mock.call_args.args[0], "assignments/example.txt")
        self.assertIn(
            "attachment", url_mock.call_args.kwargs["parameters"]["ResponseContentDisposition"]
        )
