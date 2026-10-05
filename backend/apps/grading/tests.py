from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from reportlab.pdfgen import canvas
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.ai_jobs.models import AIJob
from apps.ai_jobs.test_helpers import JobExecutionMixin
from apps.assignments.models import Assignment, QuestionPart

from .models import (
    GradingResult,
    ReferenceAnswer,
    RubricCriterion,
    StudentSubmission,
    SubmissionAnswerPart,
)
from .services.generation import build_shared_context, generate_question_parts


def build_pdf(text):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 750, text)
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


class GradingArtifactApiTests(JobExecutionMixin, APITestCase):
    def setUp(self):
        super().setUp()
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

    def test_generate_reference_answers_with_mocked_llm(self):
        self.ai_outputs["reference_answer"] = {"answer_text": "A strong answer defines osmosis."}
        response = self.client.post(
            reverse("reference-answer-generate", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.assertFalse(ReferenceAnswer.objects.exists())
        self.ai_provider.assert_not_called()
        self.drain_jobs()
        self.assertEqual(
            ReferenceAnswer.objects.get().answer_text, "A strong answer defines osmosis."
        )

    def test_other_teacher_cannot_read_or_change_grading_records(self):
        other_teacher = User.objects.create_user(
            email="private@example.com", full_name="Private", password="StrongPass123!"
        )
        other_assignment = Assignment.objects.create(
            teacher=other_teacher, title="Private Assignment", raw_assignment_text="Private"
        )
        other_question = QuestionPart.objects.create(
            assignment=other_assignment, part_key="Q1", text="Private", display_order=0
        )
        other_answer = ReferenceAnswer.objects.create(
            question_part=other_question, answer_text="Private answer"
        )
        other_submission = StudentSubmission.objects.create(
            assignment=other_assignment, student_name="Private Student", raw_response_text="Private"
        )
        other_result = GradingResult.objects.create(
            submission=other_submission, question_part=other_question, max_score="5"
        )

        for response in (
            self.client.get(reverse("reference-answer-list", args=[other_assignment.id])),
            self.client.get(reverse("submission-list", args=[other_assignment.id])),
            self.client.get(reverse("submission-detail", args=[other_submission.id])),
            self.client.patch(
                reverse("reference-answer-detail", args=[other_answer.id]),
                {"answer_text": "Changed"},
                format="json",
            ),
            self.client.patch(
                reverse("grading-result-detail", args=[other_result.id]),
                {"final_score": "4"},
                format="json",
            ),
        ):
            self.assertEqual(response.status_code, 404)

        other_answer.refresh_from_db()
        other_result.refresh_from_db()
        self.assertEqual(other_answer.answer_text, "Private answer")
        self.assertIsNone(other_result.final_score)

    def test_reference_answer_generation_surfaces_llm_failures(self):
        from .services import LLMGenerationError

        self.ai_outputs["reference_answer"] = LLMGenerationError("Malformed model output.")
        response = self.client.post(
            reverse("reference-answer-generate", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        job = AIJob.objects.get(id=response.data["id"])
        self.assertEqual(job.state, "failed")
        self.assertEqual(job.error_message, "AI request failed. Please try again.")

    def test_quota_exhaustion_pauses_accepted_job(self):
        from .services.usage import LLMQuotaExceeded

        self.ai_outputs["reference_answer"] = LLMQuotaExceeded(
            "Your daily AI allowance is used up."
        )
        response = self.client.post(
            reverse("reference-answer-generate", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        job = AIJob.objects.get(id=response.data["id"])
        self.assertEqual(job.state, "paused_quota")
        self.assertIn("allowance", job.error_message)

    def test_provider_spend_limit_pauses_job_with_safe_message(self):
        from .services.openai_client import LLMSpendLimitError

        self.ai_outputs["reference_answer"] = LLMSpendLimitError("Sensitive provider details")
        response = self.client.post(
            reverse("reference-answer-generate", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        job = AIJob.objects.get(id=response.data["id"])
        self.assertEqual(job.state, "paused_quota")
        self.assertIn("spending limit", job.error_message)
        self.assertNotIn("Sensitive", job.error_message)

    def test_rubric_ai_call_does_not_hold_database_transaction(self):
        ReferenceAnswer.objects.create(question_part=self.question, answer_text="Reference")
        self.ai_outputs["rubric_generation"] = {
            "criteria": [{"title": "Accuracy", "description": "Accurate", "max_points": 5}]
        }
        response = self.client.post(
            reverse("rubric-generate", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.ai_provider.assert_not_called()
        self.drain_jobs()  # The test provider asserts no additional transaction is held.
        self.assertEqual(AIJob.objects.get().state, "succeeded")

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

    def test_generate_rubric_with_mocked_llm(self):
        ReferenceAnswer.objects.create(question_part=self.question, answer_text="Reference answer")
        self.ai_outputs["rubric_generation"] = {
            "criteria": [
                {
                    "title": "Core concept",
                    "description": "Defines osmosis correctly.",
                    "max_points": 3,
                },
                {"title": "Example", "description": "Gives a sensible example.", "max_points": 2},
            ]
        }
        response = self.client.post(
            reverse("rubric-generate", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        self.assertEqual(RubricCriterion.objects.count(), 2)
        self.assertEqual(RubricCriterion.objects.first().title, "Core concept")

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

        delete_response = self.client.delete(
            reverse("rubric-criterion-detail", args=[criterion_id])
        )
        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(RubricCriterion.objects.count(), 0)

    def test_csv_import_creates_submissions(self):
        csv_bytes = (
            "student_name,student_id,response_text\nAlice,1001,Answer one\nBob,1002,Answer two\n"
        ).encode("utf-8")
        upload = SimpleUploadedFile("submissions.csv", csv_bytes, content_type="text/csv")

        response = self.client.post(
            reverse("submission-import-csv", args=[self.assignment.id]),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(StudentSubmission.objects.count(), 2)

    def test_manual_submission_pdf_upload_extracts_text(self):
        upload = SimpleUploadedFile(
            "submission.pdf",
            build_pdf("Student answer: gradient descent converges."),
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("submission-list", args=[self.assignment.id]),
            {
                "student_name": "Taylor",
                "student_identifier": "2001",
                "response_file": upload,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        submission = StudentSubmission.objects.get(student_name="Taylor")
        self.assertEqual(submission.upload_source, StudentSubmission.UploadSource.FILE)
        self.assertIn("gradient descent converges", submission.raw_response_text)
        self.assertIn("submission", submission.response_file.name)
        self.assertTrue(submission.response_file.name.endswith(".pdf"))

    def prepare_grading(self, score=4):
        ReferenceAnswer.objects.get_or_create(
            question_part=self.question, defaults={"answer_text": "Reference answer"}
        )
        criterion, _ = RubricCriterion.objects.get_or_create(
            question_part=self.question,
            defaults={"title": "Accuracy", "description": "Accurate", "max_points": 5},
        )
        self.ai_outputs["answer_mapping"] = {
            "answers": [
                {
                    "part_key": "Q1",
                    "extracted_answer_text": "Mapped answer",
                    "mapping_confidence": 0.9,
                }
            ]
        }
        self.ai_outputs["submission_grading"] = {
            "criteria": [
                {
                    "criterion_id": criterion.id,
                    "score": score,
                    "feedback": "Correct core definition.",
                }
            ],
            "feedback": "Good",
            "reasoning_summary": "Matches reference",
            "confidence_score": 0.9,
            "needs_review": False,
        }
        return StudentSubmission.objects.create(
            assignment=self.assignment, student_name="Alice", raw_response_text="Answer"
        )

    def test_grade_submission_job_with_mocked_llm(self):
        submission = self.prepare_grading()
        response = self.client.post(
            reverse("submission-grade", args=[submission.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.ai_provider.assert_not_called()
        self.drain_jobs()
        submission.refresh_from_db()
        self.assertEqual(submission.grading_status, "graded")
        self.assertEqual(str(submission.total_score), "4.00")
        self.assertEqual(SubmissionAnswerPart.objects.count(), 1)
        self.assertEqual(GradingResult.objects.count(), 1)

    def test_grading_failure_does_not_expose_provider_details(self):
        from .services import LLMGenerationError

        submission = self.prepare_grading()
        self.ai_outputs["answer_mapping"] = LLMGenerationError(
            "provider request id and private details"
        )
        response = self.client.post(
            reverse("submission-grade", args=[submission.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        job = AIJob.objects.get(id=response.data["id"])
        self.assertEqual(job.state, "failed")
        self.assertEqual(job.error_message, "AI request failed. Please try again.")
        self.assertNotIn("private details", str(self.client.get(f"/api/ai/jobs/{job.id}/").data))
        self.assertNotIn(
            "private details",
            str(self.client.get(reverse("submission-detail", args=[submission.id])).data),
        )

    def test_grade_all_returns_receipt_and_publishes_students(self):
        self.prepare_grading(score=3)
        StudentSubmission.objects.create(
            assignment=self.assignment, student_name="Bob", raw_response_text="Answer two"
        )
        response = self.client.post(
            reverse("assignment-grade-all", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(response.data["children"]), 2)
        self.ai_provider.assert_not_called()
        self.drain_jobs()
        self.assertEqual(AIJob.objects.get(id=response.data["id"]).state, "succeeded")
        self.assertEqual(
            StudentSubmission.objects.filter(grading_status="graded", total_score=3).count(), 2
        )

    @override_settings(GRAIDER_AI_MAX_BATCH_SUBMISSIONS=1)
    def test_grade_all_rejects_too_many_submissions_before_ai_calls(self):
        self.prepare_grading()
        StudentSubmission.objects.create(
            assignment=self.assignment, student_name="Bob", raw_response_text="Answer"
        )
        response = self.client.post(
            reverse("assignment-grade-all", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AIJob.objects.exists())
        self.ai_provider.assert_not_called()

    @override_settings(GRAIDER_AI_MAX_GRADING_QUESTIONS=1)
    def test_grade_all_rejects_too_many_questions_before_ai_calls(self):
        self.prepare_grading()
        QuestionPart.objects.create(
            assignment=self.assignment, part_key="Q2", text="Second question", max_marks=1
        )
        response = self.client.post(
            reverse("assignment-grade-all", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AIJob.objects.exists())
        self.ai_provider.assert_not_called()

    def test_grade_all_pauses_on_provider_spend_limit(self):
        from .services.openai_client import LLMSpendLimitError

        self.prepare_grading()
        self.ai_outputs["answer_mapping"] = LLMSpendLimitError("Sensitive provider details")
        response = self.client.post(
            reverse("assignment-grade-all", args=[self.assignment.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 202)
        self.drain_jobs()
        job = AIJob.objects.get(id=response.data["id"])
        self.assertEqual(job.state, "paused_quota")
        self.assertNotIn("Sensitive", str(self.client.get(f"/api/ai/jobs/{job.id}/").data))

    def test_repeat_grading_replays_action_key_without_duplicate_ai_work(self):
        submission = self.prepare_grading()
        route = reverse("submission-grade", args=[submission.id])
        first = self.client.post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="repeat")
        self.assertEqual(first.status_code, 202)
        self.drain_jobs()
        repeated = self.client.post(route, {}, format="json", HTTP_IDEMPOTENCY_KEY="repeat")
        self.assertEqual(repeated.status_code, 202)
        self.assertEqual(first.data["id"], repeated.data["id"])
        self.drain_jobs()
        self.assertEqual(self.ai_provider.call_count, 2)
        self.assertEqual(self.client.post(route, {}, format="json").status_code, 409)

    def test_in_progress_grading_rejects_second_request(self):
        submission = self.prepare_grading()
        submission.grading_status = "grading"
        submission.save()
        response = self.client.post(
            reverse("submission-grade", args=[submission.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.ai_provider.assert_not_called()

    def test_submission_grading_endpoint_returns_nested_payload(self):
        submission = self.prepare_grading()
        self.assertEqual(
            self.client.post(
                reverse("submission-grade", args=[submission.id]), {}, format="json"
            ).status_code,
            202,
        )
        self.drain_jobs()
        response = self.client.get(reverse("submission-grading", args=[submission.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["submission"]["student_name"], "Alice")
        self.assertEqual(len(response.data["answer_parts"]), 1)
        self.assertEqual(len(response.data["grading_results"]), 1)

    def test_review_patch_updates_total_and_marks_submission_reviewed(self):
        submission = StudentSubmission.objects.create(
            assignment=self.assignment,
            student_name="Dana",
            raw_response_text="Answer",
        )
        result = GradingResult.objects.create(
            submission=submission,
            question_part=self.question,
            ai_score="3",
            final_score="3",
            max_score="5",
            ai_feedback="AI feedback",
            final_feedback="AI feedback",
        )

        response = self.client.patch(
            reverse("grading-result-detail", args=[result.id]),
            {
                "final_score": "4.50",
                "final_feedback": "Teacher-adjusted feedback.",
                "needs_review": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        result.refresh_from_db()
        self.assertEqual(str(submission.total_score), "4.50")
        self.assertEqual(submission.grading_status, StudentSubmission.GradingStatus.REVIEWED)
        self.assertEqual(str(result.final_score), "4.50")
        self.assertEqual(result.final_feedback, "Teacher-adjusted feedback.")

    def test_finalize_and_export_csv(self):
        submission = StudentSubmission.objects.create(
            assignment=self.assignment,
            student_name="Elliot",
            student_identifier="E-1",
            raw_response_text="Answer",
        )
        GradingResult.objects.create(
            submission=submission,
            question_part=self.question,
            ai_score="4",
            final_score="4.50",
            max_score="5",
            ai_feedback="AI feedback",
            final_feedback="Final feedback",
        )

        finalize_response = self.client.post(
            reverse("submission-finalize", args=[submission.id]),
            {},
            format="json",
        )
        export_response = self.client.get(
            reverse("assignment-export-csv", args=[self.assignment.id])
        )

        self.assertEqual(finalize_response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.grading_status, StudentSubmission.GradingStatus.FINALIZED)
        self.assertEqual(str(submission.total_score), "4.50")
        self.assertIsNotNone(submission.finalized_at)

        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response["Content-Type"], "text/csv")
        content = export_response.content.decode("utf-8")
        self.assertIn(
            "student_name,student_identifier,grading_status,total_score,finalized_at,Q1_score,Q1_feedback",
            content,
        )
        self.assertIn("Elliot,E-1,finalized,4.50", content)
        self.assertIn("Final feedback", content)


class QuestionGenerationServiceTests(TestCase):
    @patch("apps.grading.services.generation.question_set_needs_repair", return_value=False)
    @patch("apps.grading.services.generation.OpenAIChatService.parse")
    def test_generate_question_parts_uses_structured_pdf_parser_for_q1_split(
        self,
        parse_mock,
        _needs_repair_mock,
    ):
        assignment = SimpleNamespace(
            title="Assignment 1 - Q1",
            course_name="CPSC 440",
            description="Covers complex matrix algebra questions",
            raw_assignment_text=(
                "1 Matrix Notation, Quadratics, Convexity, and Gradients [30 points]\n"
                "Some of the notes on the course page might be useful to refresh some mathematical tools.\n"
                "Each part is worth [3 points].\n"
                "[1.1] Consider the function f(x). Answer: TODO\n"
                "[1.2] Write the gradient of f from the previous question, in matrix notation. Answer: TODO\n"
                "[1.3] Show that f is convex if A is a symmetric, positive semi-definite matrix. Answer: TODO\n"
                "[1.4] When A is symmetric and strictly positive definite, give a linear system whose solution minimizes f in terms of x. Answer: TODO\n"
                "[1.5] Suppose that A is not symmetric, but A + A^T is strictly positive definite. Characterize the minimizers of f. Answer: TODO\n"
                "[1.6] Suppose that A is symmetric and only positive semi-definite. Will gradient descent necessarily find one of the solutions? Answer: TODO\n"
                "[1.7] Show that the support vector regression objective is convex. Answer: TODO\n"
                "[1.8] Consider weighted linear regression with an L2 regularizer. Write this function in matrix notation. Answer: TODO\n"
                "[1.9] Assuming that v(i) >= 0 for all i, show that f from the previous part is convex. Answer: TODO\n"
                "[1.10] Assuming that we have v(i) >= 0 for all i, give a linear system whose solution minimizes f in terms of w. Answer: TODO\n"
                "2 K-means Clustering [25 points]\n"
                "[2.1] Complete KMeans.loss. Answer: TODO\n"
            ),
            source_file=SimpleNamespace(name="cpsc440_a1_q1_question_split.pdf"),
        )

        result = generate_question_parts(assignment)

        self.assertEqual(len(result.parts), 11)
        self.assertEqual(result.parts[0].part_type, "context")
        self.assertEqual(result.parts[0].source_label, "1")
        self.assertIn("Some of the notes on the course page", result.parts[0].text)
        self.assertIn("Consider the function", result.parts[0].text)

        question_parts = [part for part in result.parts if part.part_type == "question"]
        self.assertEqual(len(question_parts), 10)
        self.assertEqual(question_parts[0].source_label, "1.1")
        self.assertEqual(question_parts[-1].source_label, "1.10")
        self.assertTrue(all(part.parent_key == "1" for part in question_parts))
        self.assertTrue(all(part.max_marks == 3 for part in question_parts))
        self.assertTrue(question_parts[0].text.startswith("Consider the function"))
        self.assertTrue(question_parts[-1].text.startswith("Assuming that we have v(i) >= 0"))
        parse_mock.assert_not_called()

    def test_build_shared_context_uses_context_parts_and_referenced_siblings(self):
        user = User.objects.create_user(
            email="context@example.com",
            full_name="Context User",
            password="StrongPass123!",
        )
        assignment = Assignment.objects.create(
            teacher=user,
            title="Context Assignment",
            raw_assignment_text="Question 1",
        )
        QuestionPart.objects.create(
            assignment=assignment,
            part_key="Q1",
            source_label="1",
            parent_key="1",
            part_type=QuestionPart.PartType.CONTEXT,
            text="Consider the function f(x) = x^T A x + b^T x + c.",
            max_marks="0",
            display_order=0,
        )
        first_question = QuestionPart.objects.create(
            assignment=assignment,
            part_key="Q2",
            source_label="1.1",
            parent_key="1",
            part_type=QuestionPart.PartType.QUESTION,
            text="Write the function in matrix notation.",
            max_marks="3",
            display_order=1,
        )
        second_question = QuestionPart.objects.create(
            assignment=assignment,
            part_key="Q3",
            source_label="1.2",
            parent_key="1",
            part_type=QuestionPart.PartType.QUESTION,
            text="Write the gradient of f from the previous question in matrix notation.",
            max_marks="3",
            display_order=2,
        )

        shared_context = build_shared_context(second_question)

        self.assertIn("Shared context 1", shared_context)
        self.assertIn("Consider the function f(x)", shared_context)
        self.assertIn("Previous part 1.1", shared_context)
        self.assertIn(first_question.text, shared_context)

    @patch("apps.grading.services.generation.question_set_needs_repair", return_value=False)
    def test_generate_question_parts_ignores_formula_lines_when_finding_sections(
        self, _needs_repair
    ):
        assignment = SimpleNamespace(
            title="Assignment 1 - Q1",
            course_name="CPSC 440",
            description="Math-heavy prompt",
            raw_assignment_text=(
                "1 Matrix Notation [30 points]\n"
                "Each part is worth [3 points].\n"
                "[1.1] Consider the function f(x).\n"
                "Answer: TODO\n"
                "[1.2] Write the gradient.\n"
                "Answer: TODO\n"
                "[1.8] Consider weighted linear regression.\n"
                "2 ∥w∥2\n"
                "Answer: TODO\n"
                "[1.9] Show that the function is convex.\n"
                "Answer: TODO\n"
                "[1.10] Give the minimizing linear system.\n"
                "Answer: TODO\n"
            ),
            source_file=SimpleNamespace(name="cpsc440_a1_q1_question_split.pdf"),
        )

        result = generate_question_parts(assignment)
        question_labels = [
            part.source_label for part in result.parts if part.part_type == "question"
        ]

        self.assertEqual(question_labels, ["1.1", "1.2", "1.8", "1.9", "1.10"])
