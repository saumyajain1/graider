import csv
import io
from contextlib import nullcontext
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.ai_jobs.models import AIJob
from apps.ai_jobs.test_helpers import JobExecutionMixin
from apps.assignments.models import Assignment, QuestionPart

from .models import GradingResult, ReferenceAnswer, RubricCriterion, StudentSubmission
from .services.grading_pipeline import grade_question_part
from .services.schemas import GeneratedCriterionGradeSchema, GeneratedQuestionGradeSchema
from .services.submission_workflow import build_rubric_text


class CriterionGradingTests(JobExecutionMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.setup_fixture()

    def setup_fixture(self):
        self.teacher = User.objects.create_user(
            email="criteria@example.com", password="test-password"
        )
        self.client.force_authenticate(self.teacher)
        self.assignment = Assignment.objects.create(teacher=self.teacher, title="Science")
        self.question = QuestionPart.objects.create(
            assignment=self.assignment, part_key="Q1", text="Explain osmosis.", max_marks=5
        )
        ReferenceAnswer.objects.create(
            question_part=self.question,
            answer_text="Teacher reference: water crosses a partially permeable membrane.",
        )
        self.criteria = [
            RubricCriterion.objects.create(
                question_part=self.question,
                title=title,
                description=description,
                max_points=points,
                display_order=index,
            )
            for index, (title, description, points) in enumerate(
                [
                    ("Definition", "Identifies movement of water.", 2),
                    ("Mechanism", "Explains the concentration gradient and membrane.", 3),
                ]
            )
        ]
        self.submission = StudentSubmission.objects.create(
            assignment=self.assignment,
            student_name="Alex",
            student_identifier="2026-01",
            raw_response_text="Water crosses a membrane.",
        )
        self.url = reverse("submission-grading", args=[self.submission.pk])

    def grade(self, scores=(1.5, 2)):
        return GeneratedQuestionGradeSchema(
            criteria=[
                GeneratedCriterionGradeSchema(
                    criterion_id=criterion.pk,
                    score=score,
                    feedback=f"Feedback for {criterion.title}.",
                )
                for criterion, score in zip(self.criteria, scores)
            ],
            feedback="Overall feedback.",
            reasoning_summary="Evidence from the answer.",
            confidence_score=0.9,
            needs_review=False,
        )

    def review_payload(self, scores=("1.00", "2.00")):
        return {
            "question_part_id": self.question.pk,
            "criterion_results": [
                {
                    "criterion_id": criterion.pk,
                    "final_score": score,
                    "final_feedback": f"Reviewed {criterion.title}.",
                }
                for criterion, score in zip(self.criteria, scores)
            ],
            "final_feedback": "Teacher summary.",
        }

    def mapping(self):
        self.ai_outputs["answer_mapping"] = {
            "answers": [
                {
                    "part_key": "Q1",
                    "extracted_answer_text": self.submission.raw_response_text,
                    "mapping_confidence": 0.95,
                }
            ]
        }
        return nullcontext()

    @patch("apps.grading.services.grading_pipeline.OpenAIChatService")
    def test_prompt_uses_saved_reference_and_every_rubric_criterion(self, service):
        parse = service.return_value.parse
        parse.return_value = self.grade()
        grade_question_part(
            self.question,
            self.question.reference_answer.answer_text,
            build_rubric_text(self.question),
            self.submission.raw_response_text,
        )
        prompt = parse.call_args.kwargs["user_prompt"]
        self.assertIn(self.question.reference_answer.answer_text, prompt)
        self.assertIn(self.submission.raw_response_text, prompt)
        for criterion in self.criteria:
            self.assertIn(f"criterion_id={criterion.pk}", prompt)
            self.assertIn(criterion.description, prompt)
            self.assertIn(f"{Decimal(str(criterion.max_points)):.2f} pts", prompt)
        self.assertIn("every supplied criterion_id", parse.call_args.kwargs["system_prompt"])

    @patch("apps.grading.services.grading_pipeline.grade_question_part")
    def test_ai_breakdown_persists_and_drives_all_totals(self, grade):
        grade.return_value = self.grade()
        with self.mapping():
            self.run_submission_job(self.submission, regrade=True)
        result = GradingResult.objects.get(submission=self.submission)
        self.assertEqual(result.ai_score, Decimal("3.50"))
        self.assertEqual(result.final_score, Decimal("3.50"))
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.total_score, Decimal("3.50"))
        self.assertEqual(grade.call_args.args[1], self.question.reference_answer.answer_text)
        self.assertIn(self.criteria[1].description, grade.call_args.args[2])
        response = self.client.get(self.url)
        rows = response.data["grading_results"][0]["criterion_results"]
        self.assertEqual(rows[0]["ai_score"], "1.50")
        self.assertEqual(rows[1]["final_score"], "2.00")
        self.assertIn("Mechanism", rows[1]["ai_feedback"])
        self.assertEqual(rows[1]["max_points"], "3.00")

    def test_ungraded_review_exposes_questions_without_writing_empty_results(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["questions"][0]["criteria"]), 2)
        self.assertIn("Teacher reference", response.data["reference_answers"][0]["answer_text"])
        self.assertEqual(response.data["grading_results"], [])
        self.assertFalse(GradingResult.objects.exists())

    @patch("apps.grading.services.grading_pipeline.grade_question_part")
    def test_manual_review_needs_no_ai_and_totals_include_zero(self, grade):
        response = self.client.patch(self.url, self.review_payload(("0", "2.5")), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["final_score"], "2.50")
        self.assertIsNone(response.data["ai_score"])
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.total_score, Decimal("2.50"))
        self.assertEqual(self.submission.grading_status, "reviewed")
        self.assertEqual(response.data["criterion_results"][0]["final_score"], "0.00")
        grade.assert_not_called()

    def test_partial_scores_remain_blank_and_total_is_incomplete(self):
        response = self.client.patch(self.url, self.review_payload((None, "2")), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["final_score"])
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.total_score)
        self.assertEqual(self.submission.grading_status, "pending")
        self.assertEqual(
            response.data["criterion_results"][0]["final_feedback"], "Reviewed Definition."
        )

    def test_all_questions_need_scores_before_assignment_total_is_complete(self):
        QuestionPart.objects.create(
            assignment=self.assignment, part_key="Q2", text="Second question", max_marks=1
        )
        response = self.client.patch(self.url, self.review_payload(), format="json")
        self.assertEqual(response.status_code, 200)
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.total_score)

    def test_manual_review_rejects_invalid_criteria_and_totals_without_writes(self):
        payloads = []
        for score in ("-1", "2.01", "1.001"):
            payloads.append(self.review_payload((score, "2")))
        missing = self.review_payload()
        missing["criterion_results"].pop()
        payloads.append(missing)
        duplicate = self.review_payload()
        duplicate["criterion_results"][1]["criterion_id"] = self.criteria[0].pk
        payloads.append(duplicate)
        foreign = self.review_payload()
        foreign["criterion_results"][0]["criterion_id"] = 99999
        payloads.append(foreign)
        total = self.review_payload()
        total["final_score"] = "5"
        payloads.append(total)
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.patch(self.url, payload, format="json").status_code, 400
                )
                self.assertFalse(GradingResult.objects.exists())

    def test_teacher_scoping_and_active_grading_block_manual_writes(self):
        other = User.objects.create_user(
            email="other-criteria@example.com", password="test-password"
        )
        self.client.force_authenticate(other)
        self.assertEqual(
            self.client.patch(self.url, self.review_payload(), format="json").status_code, 404
        )
        self.client.force_authenticate(self.teacher)
        self.submission.grading_status = "grading"
        self.submission.save()
        self.assertEqual(
            self.client.patch(self.url, self.review_payload(), format="json").status_code, 409
        )
        self.assertFalse(GradingResult.objects.exists())

    @patch("apps.grading.services.grading_pipeline.grade_question_part")
    def test_invalid_ai_breakdowns_do_not_replace_existing_results(self, grade):
        existing = GradingResult.objects.create(
            submission=self.submission,
            question_part=self.question,
            ai_score=1,
            final_score=1,
            max_score=5,
            ai_feedback="Keep existing feedback.",
        )
        for mode in ("missing", "duplicate", "foreign", "over-max", "too-precise"):
            output = self.grade()
            if mode == "missing":
                output.criteria.pop()
            elif mode == "duplicate":
                output.criteria[1].criterion_id = output.criteria[0].criterion_id
            elif mode == "foreign":
                output.criteria[0].criterion_id = 99999
            elif mode == "over-max":
                output.criteria[0].score = 3
            else:
                output.criteria[0].score = 1.001
            grade.return_value = output
            with self.mapping():
                response = self.client.post(
                    reverse("submission-grade", args=[self.submission.pk]), {}, format="json"
                )
            self.assertEqual(response.status_code, 202, response.data)
            self.drain_jobs()
            self.assertEqual(AIJob.objects.get(id=response.data["id"]).state, "failed")
            existing.refresh_from_db()
            self.assertEqual(existing.final_score, Decimal("1"))
            self.assertEqual(existing.ai_feedback, "Keep existing feedback.")
            self.assertEqual(existing.criterion_results, [])

    @patch("apps.grading.services.grading_pipeline.grade_question_part")
    def test_missing_answer_has_zero_and_feedback_for_every_criterion(self, grade):
        with self.mapping():
            self.ai_outputs["answer_mapping"]["answers"][0]["extracted_answer_text"] = ""
            self.run_submission_job(self.submission)
        result = GradingResult.objects.get(submission=self.submission)
        self.assertEqual(len(result.criterion_results), 2)
        for row in result.criterion_results:
            self.assertEqual(row["ai_score"], "0")
            self.assertIn("No answer", row["ai_feedback"])
        grade.assert_not_called()

    def test_legacy_aggregate_is_not_fabricated_into_criterion_marks(self):
        GradingResult.objects.create(
            submission=self.submission,
            question_part=self.question,
            ai_score=4,
            final_score=4,
            max_score=5,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.data["grading_results"][0]["final_score"], "4.00")
        self.assertEqual(response.data["grading_results"][0]["criterion_results"], [])
        self.assertEqual(len(response.data["questions"][0]["criteria"]), 2)

    @patch("apps.grading.services.grading_pipeline.grade_question_part")
    def test_teacher_criterion_overrides_survive_regrading(self, grade):
        grade.return_value = self.grade()
        with self.mapping():
            self.run_submission_job(self.submission, regrade=True)
        response = self.client.patch(self.url, self.review_payload(("0", "2.5")), format="json")
        self.assertEqual(response.status_code, 200)
        grade.return_value = self.grade((2, 3))
        with self.mapping():
            self.run_submission_job(self.submission, regrade=True)
        result = GradingResult.objects.get(submission=self.submission)
        self.assertEqual(result.ai_score, Decimal("5"))
        self.assertEqual(result.final_score, Decimal("2.5"))
        self.assertEqual(result.criterion_results[0]["final_score"], "0.00")
        self.assertEqual(result.criterion_results[0]["final_feedback"], "Reviewed Definition.")

    @patch("apps.grading.services.grading_pipeline.grade_question_part")
    def test_clearing_a_criterion_does_not_export_ai_score_as_final_total(self, grade):
        grade.return_value = self.grade()
        with self.mapping():
            self.run_submission_job(self.submission, regrade=True)
        response = self.client.patch(self.url, self.review_payload((None, "2")), format="json")
        self.assertEqual(response.status_code, 200)
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.total_score)
        exported = self.client.get(reverse("assignment-export-csv", args=[self.assignment.pk]))
        row = next(csv.DictReader(io.StringIO(exported.content.decode())))
        self.assertEqual(row["total_score"], "")
        self.assertEqual(row["Q1_score"], "")
