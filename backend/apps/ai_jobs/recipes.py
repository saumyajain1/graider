"""Replay existing prompt builders against frozen inputs, without live ORM reads."""

from decimal import Decimal
from types import SimpleNamespace

from apps.grading.services import generation, grading_pipeline
from apps.grading.services.submission_workflow import criterion_snapshots, validate_criterion_grades

from .models import AIJob


class FrozenRows(list):
    def all(self):
        return self

    def filter(self, **conditions):
        def matches(row):
            for key, value in conditions.items():
                field, _, operator = key.partition("__")
                actual = getattr(row, field)
                if operator == "lt":
                    if not actual < value:
                        return False
                elif actual != value:
                    return False
            return True

        return FrozenRows(row for row in self if matches(row))

    def exclude(self, **conditions):
        excluded = self.filter(**conditions)
        return FrozenRows(row for row in self if row not in excluded)

    def order_by(self, *fields):
        rows = list(self)
        for field in reversed(fields):
            rows.sort(
                key=lambda row: getattr(row, field.lstrip("-")), reverse=field.startswith("-")
            )
        return FrozenRows(rows)

    def first(self):
        return self[0] if self else None


def frozen_assignment(snapshot, owner):
    source = snapshot["assignment"]
    assignment = SimpleNamespace(
        id=source["id"],
        teacher=owner,
        title=source["title"],
        description=source["description"],
        course_name=source["course_name"],
        raw_assignment_text=source["text"],
        source_file=source["source_name"],
    )
    parts = FrozenRows()
    for row in snapshot["parts"]:
        part = SimpleNamespace(
            **{
                key: row[key]
                for key in (
                    "id",
                    "part_key",
                    "source_label",
                    "parent_key",
                    "part_type",
                    "text",
                    "display_order",
                )
            }
        )
        part.assignment = assignment
        part.max_marks = Decimal(row["max_marks"]) if row["max_marks"] is not None else None
        part.display_label = part.source_label or part.part_key
        part.rubric_criteria = FrozenRows(
            SimpleNamespace(**{**criterion, "max_points": Decimal(criterion["max_points"])})
            for criterion in row["rubric"]
        )
        part.reference_answer = (
            SimpleNamespace(answer_text=row["reference"]["text"]) if row["reference"] else None
        )
        parts.append(part)
    assignment.question_parts = parts
    return assignment


def execute_recipe(step, service):
    job = step.job
    assignment = frozen_assignment(job.input_snapshot, job.owner)
    questions = assignment.question_parts.filter(part_type="question")
    if job.operation == AIJob.Operation.QUESTIONS:
        return generation.generate_question_parts(assignment, service=service).model_dump(
            mode="json"
        )
    if step.key == "map":
        mapping = grading_pipeline.map_submission_answers(
            assignment, job.input_snapshot["submission"]["text"], questions, service=service
        )
        keys = [item.part_key for item in mapping.answers]
        if len(keys) != len(set(keys)) or set(keys) != {q.part_key for q in questions}:
            from apps.grading.services.openai_client import LLMGenerationError

            raise LLMGenerationError("Mapping must contain each question exactly once.")
        return mapping.model_dump(mode="json")
    question_id = int(step.key.split(":")[-1])
    question = questions.filter(id=question_id).first()
    if job.operation == AIJob.Operation.REFERENCES:
        return generation.generate_reference_answer(
            assignment, question, service=service
        ).model_dump(mode="json")
    if job.operation == AIJob.Operation.RUBRIC:
        return generation.generate_rubric_criteria(
            question,
            question.reference_answer.answer_text if question.reference_answer else "",
            service=service,
        ).model_dump(mode="json")
    mapped = job.steps.get(key="map").checkpoint["answers"]
    answer = next(row for row in mapped if row["part_key"] == question.part_key)
    text = answer["extracted_answer_text"].strip()
    if text:
        rubric = "\n".join(
            f"- criterion_id={c.id}: {c.title} ({c.max_points} pts): {c.description}"
            for c in question.rubric_criteria
        )
        grade = grading_pipeline.grade_question_part(
            question, question.reference_answer.answer_text, rubric, text, service=service
        )
        criteria = validate_criterion_grades(question, grade)
        feedback, reasoning, confidence, needs_review = (
            grade.feedback,
            grade.reasoning_summary,
            grade.confidence_score,
            grade.needs_review,
        )
    else:
        criteria = criterion_snapshots(question)
        feedback = "No answer found for this question."
        reasoning, confidence, needs_review = (
            "No usable answer was present in the submission.",
            1,
            False,
        )
        for criterion in criteria:
            criterion.update(
                ai_score="0", final_score="0", ai_feedback=feedback, final_feedback=feedback
            )
    return {
        "question_id": question.id,
        "answer_text": text,
        "mapping_confidence": answer["mapping_confidence"],
        "criteria": criteria,
        "feedback": feedback,
        "reasoning": reasoning,
        "confidence": confidence,
        "needs_review": needs_review,
    }
