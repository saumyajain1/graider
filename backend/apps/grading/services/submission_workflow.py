from decimal import Decimal
from datetime import timedelta
import logging

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
        f"- {criterion.title} ({criterion.max_points} pts): {criterion.description}"
        for criterion in question_part.rubric_criteria.all()
    )


def calculate_submission_total(submission):
    total = Decimal("0")
    for result in submission.grading_results.all():
        total += result.final_score if result.final_score is not None else result.ai_score or Decimal("0")
    return total


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
        try:
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
        if (
            submission.grading_status in (
                StudentSubmission.GradingStatus.GRADED,
                StudentSubmission.GradingStatus.REVIEWED,
                StudentSubmission.GradingStatus.FINALIZED,
            )
            and submission.updated_at >= now - timedelta(seconds=settings.GRAIDER_GRADE_REPEAT_COOLDOWN_SECONDS)
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
            extracted_answer_text = mapping_item.extracted_answer_text.strip() if mapping_item else ""
            mapping_confidence = (
                Decimal(str(mapping_item.mapping_confidence))
                if mapping_item and mapping_item.mapping_confidence is not None else None
            )
            if extracted_answer_text:
                grade = grade_question_part(
                    question,
                    question.reference_answer.answer_text,
                    build_rubric_text(question),
                    extracted_answer_text,
                )
                ai_score = Decimal(str(grade.score))
                if question.max_marks is not None and ai_score > question.max_marks:
                    ai_score = question.max_marks
                ai_feedback = grade.feedback
                reasoning_summary = grade.reasoning_summary
                confidence_score = (
                    Decimal(str(grade.confidence_score))
                    if grade.confidence_score is not None else None
                )
                needs_review = grade.needs_review
            else:
                ai_score = Decimal("0")
                ai_feedback = "No answer found for this question."
                reasoning_summary = "The submission did not contain a usable answer for this question part."
                confidence_score = Decimal("1.00")
                needs_review = False
            prepared.append((
                question, extracted_answer_text, mapping_confidence, ai_score,
                ai_feedback, reasoning_summary, confidence_score, needs_review,
            ))

        with transaction.atomic():
            for (
                question, extracted_answer_text, mapping_confidence, ai_score,
                ai_feedback, reasoning_summary, confidence_score, needs_review,
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
                    defaults={"max_score": question.max_marks or Decimal("0")},
                )
                previous_ai_score = result.ai_score
                previous_ai_feedback = result.ai_feedback
                result.ai_score = ai_score
                result.max_score = question.max_marks or Decimal("0")
                result.ai_feedback = ai_feedback
                result.reasoning_summary = reasoning_summary
                result.confidence_score = confidence_score
                result.needs_review = needs_review
                if (
                    not preserve_manual
                    or result.final_score is None
                    or result.final_score == previous_ai_score
                ):
                    result.final_score = ai_score
                if (
                    not preserve_manual
                    or not result.final_feedback
                    or result.final_feedback == previous_ai_feedback
                ):
                    result.final_feedback = ai_feedback
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


def save_grading_review(grading_result, *, final_score, final_feedback, needs_review):
    grading_result.final_score = final_score
    grading_result.final_feedback = final_feedback
    grading_result.needs_review = needs_review
    grading_result.save()

    submission = grading_result.submission
    submission.total_score = calculate_submission_total(submission)
    submission.grading_status = StudentSubmission.GradingStatus.REVIEWED
    submission.save(update_fields=("total_score", "grading_status", "updated_at"))

    return grading_result


def finalize_submission(submission):
    submission.grading_status = StudentSubmission.GradingStatus.FINALIZED
    submission.finalized_at = timezone.now()
    submission.total_score = calculate_submission_total(submission)
    submission.save(update_fields=("grading_status", "finalized_at", "total_score", "updated_at"))
    return submission
