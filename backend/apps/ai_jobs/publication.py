from decimal import Decimal

from apps.assignments.models import Assignment, QuestionPart
from apps.assignments.serializers import build_part_key
from apps.grading.models import (
    GradingResult,
    ReferenceAnswer,
    RubricCriterion,
    StudentSubmission,
    SubmissionAnswerPart,
)
from apps.grading.services.schemas import (
    GeneratedQuestionSetSchema,
    GeneratedReferenceAnswerSchema,
    GeneratedRubricSchema,
)
from apps.grading.services.submission_workflow import calculate_submission_total

from .models import AIJob
from .snapshots import capture_inputs, fingerprint


def inputs_match(job):
    from rest_framework.exceptions import ValidationError

    if not job.assignment_id or (job.operation == AIJob.Operation.GRADE and not job.submission_id):
        return False
    assignment = Assignment.objects.filter(pk=job.assignment_id, teacher_id=job.owner_id).first()
    if not assignment:
        return False
    submission = (
        StudentSubmission.objects.filter(pk=job.submission_id).first()
        if job.submission_id
        else None
    )
    if submission and submission.grading_status in ("grading", "finalized"):
        return False
    try:
        snapshot = capture_inputs(
            assignment,
            job.operation,
            job.input_snapshot["options"],
            submission,
            job.input_snapshot["configuration"],
        )
        return fingerprint(snapshot) == job.input_fingerprint
    except ValidationError:
        return False


def lock_inputs(job):
    # The caller owns the coordinator lock and transaction. Lock rows before the
    # final comparison, including parent rows that protect insertion via FK locks.
    Assignment.objects.select_for_update().get(pk=job.assignment_id)
    parts = list(QuestionPart.objects.select_for_update().filter(assignment_id=job.assignment_id))
    list(ReferenceAnswer.objects.select_for_update().filter(question_part__in=parts))
    list(RubricCriterion.objects.select_for_update().filter(question_part__in=parts))
    if job.submission_id:
        StudentSubmission.objects.select_for_update().get(pk=job.submission_id)
        list(GradingResult.objects.select_for_update().filter(submission_id=job.submission_id))
        list(
            SubmissionAnswerPart.objects.select_for_update().filter(submission_id=job.submission_id)
        )


def publish(job):
    """Called only inside a guarded short transaction; no provider calls here."""
    checkpoints = {step.key: step.checkpoint for step in job.steps.all()}
    if job.operation == AIJob.Operation.QUESTIONS:
        parsed = GeneratedQuestionSetSchema.model_validate(checkpoints["extract"])
        assignment = job.assignment
        if job.input_snapshot["options"]["replace_existing"]:
            assignment.question_parts.all().delete()
            # Replacing questions invalidates published grades and totals as one change.
            assignment.submissions.update(
                grading_status="pending", total_score=None, finalized_at=None, last_error=""
            )
        ids = []
        for index, part in enumerate(parsed.parts):
            key = build_part_key(assignment)
            question = QuestionPart.objects.create(
                assignment=assignment,
                part_key=key,
                source_label=(part.source_label or key).strip(),
                parent_key=part.parent_key or "",
                part_type=part.part_type,
                text=part.text,
                max_marks=Decimal(str(part.max_marks)) if part.max_marks is not None else None,
                display_order=index,
                created_by_ai=True,
            )
            ids.append(question.id)
        return {"assignment_id": assignment.id, "question_ids": ids}
    if job.operation in (AIJob.Operation.REFERENCES, AIJob.Operation.RUBRIC):
        for key, data in checkpoints.items():
            question_id = int(key.split(":")[-1])
            if job.operation == AIJob.Operation.REFERENCES:
                parsed = GeneratedReferenceAnswerSchema.model_validate(data)
                answer, created = ReferenceAnswer.objects.get_or_create(
                    question_part_id=question_id,
                    defaults={"answer_text": parsed.answer_text, "source": "ai"},
                )
                if not created:
                    answer.answer_text = parsed.answer_text
                    answer.source = "ai"
                    answer.version += 1
                    answer.save()
            else:
                parsed = GeneratedRubricSchema.model_validate(data)
                RubricCriterion.objects.filter(question_part_id=question_id).delete()
                RubricCriterion.objects.bulk_create(
                    [
                        RubricCriterion(
                            question_part_id=question_id,
                            title=row.title,
                            description=row.description,
                            max_points=Decimal(str(row.max_points)),
                            display_order=index,
                            created_by_ai=True,
                        )
                        for index, row in enumerate(parsed.criteria)
                    ]
                )
        return {"assignment_id": job.assignment_id}
    submission = job.submission
    for key, data in checkpoints.items():
        if key == "map":
            continue
        question_id = data["question_id"]
        SubmissionAnswerPart.objects.update_or_create(
            submission=submission,
            question_part_id=question_id,
            defaults={
                "extracted_answer_text": data["answer_text"],
                "mapping_confidence": data["mapping_confidence"],
            },
        )
        result, created = GradingResult.objects.get_or_create(
            submission=submission,
            question_part_id=question_id,
            defaults={"max_score": QuestionPart.objects.get(pk=question_id).max_marks},
        )
        criteria = [dict(row) for row in data["criteria"]]
        old = {row["criterion_id"]: row for row in result.criterion_results}
        for row in criteria:
            previous = old.get(row["criterion_id"])
            if previous and previous["max_points"] == row["max_points"]:
                for field in ("score", "feedback"):
                    if previous[f"final_{field}"] != previous[f"ai_{field}"]:
                        row[f"final_{field}"] = previous[f"final_{field}"]
        current = {row["criterion_id"]: row for row in criteria}
        for old_id, previous in old.items():
            overridden = any(
                previous[f"final_{field}"] != previous[f"ai_{field}"]
                for field in ("score", "feedback")
            )
            if overridden and (
                old_id not in current or current[old_id]["max_points"] != previous["max_points"]
            ):
                from apps.grading.services.openai_client import LLMGenerationError

                raise LLMGenerationError(
                    "Changed rubric cannot preserve a teacher override automatically."
                )
        if (
            not created
            and not old
            and result.final_score is not None
            and result.final_score != result.ai_score
        ):
            from apps.grading.services.openai_client import LLMGenerationError

            raise LLMGenerationError(
                "Legacy teacher total needs manual review before criterion regrading."
            )
        final_feedback = (
            data["feedback"]
            if created or result.final_feedback == result.ai_feedback
            else result.final_feedback
        )
        result.ai_score = sum(Decimal(row["ai_score"]) for row in criteria)
        result.max_score = QuestionPart.objects.get(pk=question_id).max_marks
        result.final_score = (
            sum(Decimal(row["final_score"]) for row in criteria)
            if all(row["final_score"] is not None for row in criteria)
            else None
        )
        result.criterion_results = criteria
        result.ai_feedback = data["feedback"]
        result.final_feedback = final_feedback
        result.reasoning_summary = data["reasoning"]
        result.confidence_score = data["confidence"]
        result.needs_review = data["needs_review"]
        result.save()
    submission.total_score = calculate_submission_total(submission)
    submission.grading_status = "graded"
    submission.last_error = ""
    submission.save(update_fields=("total_score", "grading_status", "last_error", "updated_at"))
    return {"submission_id": submission.id, "assignment_id": job.assignment_id}
