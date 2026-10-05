"""Capture JSON-only execution recipes. Never create a provider client here."""

import hashlib
import json
import os
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from rest_framework.exceptions import ValidationError

from apps.assignments.models import QuestionPart
from apps.grading.models import GradingResult
from apps.grading.services.openai_client import LLMConfigurationError, get_reasoning_effort
from apps.grading.services.submission_workflow import (
    SubmissionNotReadyError,
    validate_submission_ready_for_grading,
)

from .models import AIJob

SNAPSHOT_VERSION = 1
PROMPT_VERSION = 1
OUTPUT_SCHEMA_VERSION = 1


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def inputs_unchanged(original, current):
    """Independent artifact jobs guard their own targets and all question context."""
    if original["operation"] not in (AIJob.Operation.REFERENCES, AIJob.Operation.RUBRIC):
        return fingerprint(original) == fingerprint(current)
    # Freeze admission's targets: a missing-only job must not gain new work later.
    targets = {int(key.rsplit(":", 1)[-1]) for key in execution_plan(original)[0]}
    projected = []
    for snapshot in (original, current):
        value = deepcopy(snapshot)
        for part in value["parts"]:
            if part["id"] not in targets:
                part["reference"] = None
                part["rubric"] = []
        projected.append(value)
    return fingerprint(projected[0]) == fingerprint(projected[1])


def ai_configuration():
    tasks = {
        "question_generation": "OPENAI_QUESTION_MODEL",
        "question_repair": "OPENAI_QUESTION_MODEL",
        "reference_answer": "OPENAI_ARTIFACT_MODEL",
        "rubric_generation": "OPENAI_ARTIFACT_MODEL",
        "answer_mapping": "OPENAI_MAPPING_MODEL",
        "submission_grading": "OPENAI_GRADING_MODEL",
    }
    try:
        return {
            task: {
                "model": os.getenv(variable, "gpt-6-luna"),
                "reasoning_effort": get_reasoning_effort(task),
            }
            for task, variable in tasks.items()
        }
    except LLMConfigurationError as exc:
        raise ValidationError("Invalid AI model/reasoning configuration.") from exc


def capture_inputs(assignment, operation, options, submission=None, configuration=None):
    parts = list(
        assignment.question_parts.select_related("reference_answer")
        .prefetch_related("rubric_criteria")
        .order_by("display_order", "id")
    )
    questions = [part for part in parts if part.part_type == QuestionPart.PartType.QUESTION]
    if operation == AIJob.Operation.QUESTIONS and not assignment.raw_assignment_text.strip():
        raise ValidationError("Add assignment text before extracting questions.")
    if (
        operation == AIJob.Operation.QUESTIONS
        and parts
        and not options.get("replace_existing", False)
    ):
        raise ValidationError(
            "Explicitly choose replacement before extracting over existing questions."
        )
    if operation in (AIJob.Operation.REFERENCES, AIJob.Operation.RUBRIC) and not questions:
        raise ValidationError("Add scored questions before generating answers or rubrics.")
    question_id = options.get("question_part_id")
    if question_id and not any(part.id == question_id for part in questions):
        raise ValidationError("Choose a scored question from this assignment.")
    if operation == AIJob.Operation.GRADE:
        try:
            validate_submission_ready_for_grading(submission)
        except SubmissionNotReadyError as exc:
            raise ValidationError(str(exc)) from exc
        if not submission.raw_response_text.strip():
            raise ValidationError("Add submission text before grading.")
    snapshot = {
        "snapshot_version": SNAPSHOT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "configuration": configuration if configuration is not None else ai_configuration(),
        "operation": operation,
        "options": options,
        "assignment": {
            "id": assignment.id,
            "title": assignment.title,
            "course_name": assignment.course_name,
            "updated_at": assignment.updated_at.isoformat(),
            "source_name": Path(assignment.source_file.name).name if assignment.source_file else "",
            "description": assignment.description,
            "text": assignment.raw_assignment_text,
            "source_filename": assignment.source_original_filename,
        },
        "parts": [
            {
                "id": part.id,
                "part_key": part.part_key,
                "source_label": part.source_label,
                "parent_key": part.parent_key,
                "part_type": part.part_type,
                "text": part.text,
                "max_marks": str(part.max_marks) if part.max_marks is not None else None,
                "display_order": part.display_order,
                "updated_at": part.updated_at.isoformat(),
                "reference": (
                    {
                        "id": part.reference_answer.id,
                        "text": part.reference_answer.answer_text,
                        "version": part.reference_answer.version,
                        "source": part.reference_answer.source,
                        "updated_at": part.reference_answer.updated_at.isoformat(),
                    }
                    if hasattr(part, "reference_answer")
                    else None
                ),
                "rubric": [
                    {
                        "id": criterion.id,
                        "title": criterion.title,
                        "description": criterion.description,
                        "max_points": str(criterion.max_points),
                        "display_order": criterion.display_order,
                        "updated_at": criterion.updated_at.isoformat(),
                    }
                    for criterion in part.rubric_criteria.all()
                ],
            }
            for part in parts
        ],
    }
    if submission is not None:
        snapshot["submission"] = {
            "id": submission.id,
            "text": submission.raw_response_text,
            "finalized_at": submission.finalized_at.isoformat()
            if submission.finalized_at
            else None,
            # A publication guard for edits to prior grades while regrading is in progress.
            "published_results": [
                {"id": row.id, "updated_at": row.updated_at.isoformat()}
                for row in GradingResult.objects.filter(submission=submission).order_by("id")
            ],
        }
    return snapshot


def execution_plan(snapshot):
    operation = snapshot["operation"]
    questions = [p for p in snapshot["parts"] if p["part_type"] == "question"]
    options = snapshot["options"]
    if options.get("question_part_id"):
        questions = [p for p in questions if p["id"] == options["question_part_id"]]
    if operation == AIJob.Operation.QUESTIONS:
        return ["extract"], [f"questions:{snapshot['assignment']['id']}"]
    if operation == AIJob.Operation.GRADE:
        return ["map"] + [f"grade:{p['id']}" for p in questions], [
            f"grade:{snapshot['submission']['id']}"
        ]
    if operation == AIJob.Operation.BATCH:
        return [], []
    if not options.get("replace_existing", False):
        if operation == AIJob.Operation.REFERENCES:
            questions = [
                p for p in questions if not p["reference"] or not p["reference"]["text"].strip()
            ]
        else:
            questions = [p for p in questions if not p["rubric"]]
    if not questions:
        raise ValidationError("Nothing to generate. Explicitly choose replacement to regenerate.")
    if any(
        not p["text"].strip() or not p["max_marks"] or Decimal(p["max_marks"]) <= 0
        for p in questions
    ):
        raise ValidationError("Set question text and positive total marks before generating.")
    if operation == AIJob.Operation.RUBRIC and any(
        not p["reference"] or not p["reference"]["text"].strip() for p in questions
    ):
        raise ValidationError(
            "Generate or create a reference answer before generating rubric criteria."
        )
    return [f"{operation}:{p['id']}" for p in questions], [
        f"{operation}:{p['id']}" for p in questions
    ]
