import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.assignments.models import QuestionPart

from ..models import GradingResult, ReferenceAnswer, StudentSubmission, SubmissionAnswerPart
from .grading_pipeline import grade_question_part, map_submission_answers
from .openai_client import LLMConfigurationError, LLMGenerationError, public_llm_error
from .usage import LLMQuotaExceeded

logger = logging.getLogger(__name__)


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
    questions = list(
        question_queryset_for_assignment(submission.assignment)
        .select_related("reference_answer")
        .prefetch_related("rubric_criteria")
    )

    if not questions:
        raise SubmissionNotReadyError("Add question parts before grading submissions.")

    missing_reference_answers = []
    missing_rubric = []
    for question in questions:
        if question.max_marks is None or question.max_marks <= 0:
            raise SubmissionNotReadyError(
                f"Set positive total marks for {question.display_label} before grading."
            )
        criteria = list(question.rubric_criteria.all())
        if criteria and (
            any(criterion.max_points <= 0 for criterion in criteria)
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


def run_grading_pipeline(submission):
    questions = validate_submission_ready_for_grading(submission)
    now = timezone.now()
    with transaction.atomic():
        submission = StudentSubmission.objects.select_for_update().get(pk=submission.pk)
        if submission.grading_status in (
            StudentSubmission.GradingStatus.GRADED,
            StudentSubmission.GradingStatus.REVIEWED,
            StudentSubmission.GradingStatus.FINALIZED,
        ) and submission.updated_at >= now - timedelta(
            seconds=settings.GRAIDER_GRADE_REPEAT_COOLDOWN_SECONDS
        ):
            return submission
        if (
            submission.grading_status == StudentSubmission.GradingStatus.GRADING
            and submission.updated_at >= now - timedelta(hours=1)
        ):
            raise SubmissionGradingInProgressError("This submission is already being graded.")
        original_status = submission.grading_status
        submission.grading_status = StudentSubmission.GradingStatus.GRADING
        submission.last_error = ""
        submission.save(update_fields=("grading_status", "last_error", "updated_at"))

    try:
        if submission.raw_response_text.strip():
            mapping_response = map_submission_answers(
                submission.assignment,
                submission.raw_response_text,
                questions,
            )
            mapping_by_key = {item.part_key: item for item in mapping_response.answers}
        else:
            mapping_by_key = {}

        preserve_manual = original_status in [
            StudentSubmission.GradingStatus.REVIEWED,
            StudentSubmission.GradingStatus.FINALIZED,
        ]

        prepared = []
        for question in questions:
            mapping_item = mapping_by_key.get(question.part_key)
            extracted_answer_text = (
                mapping_item.extracted_answer_text.strip() if mapping_item else ""
            )
            mapping_confidence = (
                Decimal(str(mapping_item.mapping_confidence))
                if mapping_item and mapping_item.mapping_confidence is not None
                else None
            )
            if extracted_answer_text:
                grade = grade_question_part(
                    question,
                    question.reference_answer.answer_text,
                    build_rubric_text(question),
                    extracted_answer_text,
                )
                criterion_results = validate_criterion_grades(question, grade)
                ai_score = sum(Decimal(row["ai_score"]) for row in criterion_results)
                ai_feedback = grade.feedback
                reasoning_summary = grade.reasoning_summary
                confidence_score = (
                    Decimal(str(grade.confidence_score))
                    if grade.confidence_score is not None
                    else None
                )
                needs_review = grade.needs_review
            else:
                ai_score = Decimal("0")
                ai_feedback = "No answer found for this question."
                reasoning_summary = (
                    "The submission did not contain a usable answer for this question part."
                )
                confidence_score = Decimal("1.00")
                needs_review = False
                criterion_results = criterion_snapshots(question)
                for row in criterion_results:
                    row.update(
                        ai_score="0",
                        final_score="0",
                        ai_feedback=ai_feedback,
                        final_feedback=ai_feedback,
                    )
            prepared.append(
                (
                    question,
                    extracted_answer_text,
                    mapping_confidence,
                    ai_score,
                    ai_feedback,
                    reasoning_summary,
                    confidence_score,
                    needs_review,
                    criterion_results,
                )
            )

        with transaction.atomic():
            for (
                question,
                extracted_answer_text,
                mapping_confidence,
                ai_score,
                ai_feedback,
                reasoning_summary,
                confidence_score,
                needs_review,
                criterion_results,
            ) in prepared:
                answer_part, _ = SubmissionAnswerPart.objects.get_or_create(
                    submission=submission,
                    question_part=question,
                )
                answer_part.extracted_answer_text = extracted_answer_text
                answer_part.mapping_confidence = mapping_confidence
                answer_part.save(
                    update_fields=(
                        "extracted_answer_text",
                        "mapping_confidence",
                        "updated_at",
                    )
                )

                result, _ = GradingResult.objects.get_or_create(
                    submission=submission,
                    question_part=question,
                    defaults={"max_score": question.max_marks},
                )
                previous_ai_feedback = result.ai_feedback
                previous_criteria = {row["criterion_id"]: row for row in result.criterion_results}
                if preserve_manual:
                    for row in criterion_results:
                        old = previous_criteria.get(row["criterion_id"])
                        if old and old["max_points"] == row["max_points"]:
                            for name in ("score", "feedback"):
                                if old[f"final_{name}"] != old[f"ai_{name}"]:
                                    row[f"final_{name}"] = old[f"final_{name}"]
                result.criterion_results = criterion_results
                result.ai_score = ai_score
                result.max_score = question.max_marks
                result.ai_feedback = ai_feedback
                result.reasoning_summary = reasoning_summary
                result.confidence_score = confidence_score
                result.needs_review = needs_review
                if (
                    not preserve_manual
                    or not result.final_feedback
                    or result.final_feedback == previous_ai_feedback
                ):
                    result.final_feedback = ai_feedback
                # Once a criterion breakdown exists, the question total is always its sum.
                result.final_score = (
                    sum(Decimal(row["final_score"]) for row in criterion_results)
                    if all(row["final_score"] is not None for row in criterion_results)
                    else None
                )
                result.save()

            submission.total_score = calculate_submission_total(submission)
            submission.grading_status = StudentSubmission.GradingStatus.GRADED
            submission.last_error = ""
            submission.save(
                update_fields=("total_score", "grading_status", "last_error", "updated_at")
            )
    except Exception as exc:
        logger.exception("Grading failed for submission %s", submission.pk)
        submission.grading_status = StudentSubmission.GradingStatus.FAILED
        if isinstance(exc, SubmissionNotReadyError):
            submission.last_error = str(exc)
        elif isinstance(exc, LLMQuotaExceeded):
            submission.last_error = str(exc)
        elif isinstance(exc, (LLMConfigurationError, LLMGenerationError)):
            submission.last_error = public_llm_error(exc)
        else:
            submission.last_error = "Grading failed. Please try again."
        submission.save(update_fields=("grading_status", "last_error", "updated_at"))
        raise

    return submission


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
    submission.save(update_fields=("total_score", "grading_status", "updated_at"))

    return grading_result


def finalize_submission(submission):
    submission.grading_status = StudentSubmission.GradingStatus.FINALIZED
    submission.finalized_at = timezone.now()
    submission.total_score = calculate_submission_total(submission)
    submission.save(update_fields=("grading_status", "finalized_at", "total_score", "updated_at"))
    return submission
