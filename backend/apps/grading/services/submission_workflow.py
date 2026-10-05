from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.assignments.models import QuestionPart
from apps.assignments.readiness import assignment_readiness

from ..models import ReferenceAnswer, StudentSubmission
from .openai_client import LLMGenerationError


class SubmissionNotReadyError(ValueError):
    pass


class SubmissionGradingInProgressError(Exception):
    pass


def question_queryset_for_assignment(assignment):
    return assignment.question_parts.filter(part_type=QuestionPart.PartType.QUESTION).order_by(
        "display_order", "id"
    )


def build_rubric_text(question_part):
    return "\n".join(
        f"- criterion_id={criterion.id}: {criterion.title} ({criterion.max_points} pts): {criterion.description}"
        for criterion in question_part.rubric_criteria.all()
    )


def calculate_submission_total(submission):
    total = Decimal("0")
    results = list(submission.grading_results.all())
    if len(results) != question_queryset_for_assignment(submission.assignment).count():
        return None
    for result in results:
        if result.criterion_results and any(
            row["final_score"] is None for row in result.criterion_results
        ):
            return None
        if result.final_score is None and result.ai_score is None:
            return None
        total += (
            result.final_score
            if result.final_score is not None
            else result.ai_score or Decimal("0")
        )
    return total


def criterion_snapshots(question):
    return [
        {
            "criterion_id": criterion.id,
            "title": criterion.title,
            "description": criterion.description,
            "max_points": str(criterion.max_points),
            "ai_score": None,
            "final_score": None,
            "ai_feedback": "",
            "final_feedback": "",
        }
        for criterion in question.rubric_criteria.all()
    ]


def validate_criterion_grades(question, grade):
    rows = criterion_snapshots(question)
    grades = {item.criterion_id: item for item in grade.criteria}
    if len(grades) != len(grade.criteria) or set(grades) != {row["criterion_id"] for row in rows}:
        raise LLMGenerationError("AI did not grade every rubric criterion exactly once.")
    for row in rows:
        item = grades[row["criterion_id"]]
        score = Decimal(str(item.score))
        if (
            not score.is_finite()
            or score < 0
            or score > Decimal(row["max_points"])
            or score != score.quantize(Decimal("0.01"))
            or not item.feedback.strip()
        ):
            raise LLMGenerationError("AI returned invalid rubric criterion marks or feedback.")
        row.update(
            ai_score=str(score),
            final_score=str(score),
            ai_feedback=item.feedback,
            final_feedback=item.feedback,
        )
    return rows


def validate_submission_ready_for_grading(submission):
    questions, _, _, _ = assignment_readiness(submission.assignment)

    if not questions:
        raise SubmissionNotReadyError("Add question parts before grading submissions.")

    missing_reference_answers = []
    missing_rubric = []
    for question in questions:
        if not question.text.strip() or question.max_marks is None or question.max_marks <= 0:
            raise SubmissionNotReadyError(
                f"Set positive total marks for {question.display_label} before grading."
            )
        criteria = list(question.rubric_criteria.all())
        if criteria and (
            any(
                criterion.max_points <= 0
                or not criterion.title.strip()
                or not criterion.description.strip()
                for criterion in criteria
            )
            or sum(criterion.max_points for criterion in criteria) != question.max_marks
        ):
            raise SubmissionNotReadyError(
                f"Rubric points for {question.display_label} must total {question.max_marks} marks before grading."
            )
        try:
            if not question.reference_answer.answer_text.strip():
                raise ReferenceAnswer.DoesNotExist
            question.reference_answer
        except ReferenceAnswer.DoesNotExist:
            missing_reference_answers.append(question.part_key)
        if not question.rubric_criteria.exists():
            missing_rubric.append(question.part_key)

    if missing_reference_answers:
        raise SubmissionNotReadyError(
            "Missing reference answers for: " + ", ".join(missing_reference_answers)
        )

    if missing_rubric:
        raise SubmissionNotReadyError("Missing rubric criteria for: " + ", ".join(missing_rubric))

    return questions


@transaction.atomic
def save_grading_review(
    grading_result, *, final_score, final_feedback, needs_review, criterion_results=None
):
    submission = StudentSubmission.objects.select_for_update().get(pk=grading_result.submission_id)
    if submission.grading_status == StudentSubmission.GradingStatus.GRADING:
        raise SubmissionGradingInProgressError("Wait for grading to finish before editing results.")
    if grading_result.pk is None:
        existing = submission.grading_results.filter(
            question_part_id=grading_result.question_part_id
        ).first()
        if existing is not None:
            raise SubmissionGradingInProgressError(
                "Results changed while saving. Reload and try again."
            )
    if criterion_results is not None:
        grading_result.criterion_results = criterion_results
    grading_result.final_score = final_score
    grading_result.final_feedback = final_feedback
    grading_result.needs_review = needs_review
    grading_result.save()

    submission.total_score = calculate_submission_total(submission)
    submission.grading_status = (
        StudentSubmission.GradingStatus.REVIEWED
        if submission.total_score is not None
        else StudentSubmission.GradingStatus.PENDING
    )
    submission.finalized_at = None
    submission.save(update_fields=("total_score", "grading_status", "finalized_at", "updated_at"))

    return grading_result


@transaction.atomic
def finalize_submission(submission):
    submission = StudentSubmission.objects.select_for_update().get(pk=submission.pk)
    if submission.grading_status == StudentSubmission.GradingStatus.GRADING:
        raise SubmissionGradingInProgressError("Wait for grading to finish before finalizing.")
    questions, marks_ready, _, _ = assignment_readiness(submission.assignment)
    results = {r.question_part_id: r for r in submission.grading_results.select_for_update()}
    if not marks_ready or set(results) != {q.pk for q in questions}:
        raise SubmissionNotReadyError("Enter valid grades for every question before finalizing.")
    for question in questions:
        result = results[question.pk]
        if result.needs_review:
            raise SubmissionNotReadyError("Clear all review flags before finalizing.")
        score = result.final_score if result.final_score is not None else result.ai_score
        if (
            score is None
            or result.max_score != question.max_marks
            or not 0 <= score <= question.max_marks
        ):
            raise SubmissionNotReadyError(
                "Every question needs a valid score within its total marks."
            )
        if result.criterion_results:
            rows = result.criterion_results
            try:
                totals = [Decimal(str(row["final_score"])) for row in rows]
                maxima = [Decimal(str(row["max_points"])) for row in rows]
                valid = all(
                    v.is_finite() and m.is_finite() and m > 0 and 0 <= v <= m
                    for v, m in zip(totals, maxima)
                )
                valid = valid and len({row["criterion_id"] for row in rows}) == len(rows)
                valid = valid and sum(maxima) == question.max_marks and sum(totals) == score
            except (KeyError, ValueError, ArithmeticError, TypeError):
                valid = False
            if not valid:
                raise SubmissionNotReadyError("Complete every rubric score before finalizing.")
    submission.total_score = calculate_submission_total(submission)
    if submission.total_score is None:
        raise SubmissionNotReadyError("Complete every question before finalizing.")
    if submission.grading_status != StudentSubmission.GradingStatus.FINALIZED:
        submission.grading_status = StudentSubmission.GradingStatus.FINALIZED
        submission.finalized_at = timezone.now()
        submission.save(
            update_fields=("grading_status", "finalized_at", "total_score", "updated_at")
        )
    return submission
