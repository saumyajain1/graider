from decimal import Decimal

from .models import QuestionPart


def assignment_readiness(assignment):
    """One set of setup rules for workflow badges and grading admission."""
    questions = list(
        assignment.question_parts.filter(part_type=QuestionPart.PartType.QUESTION)
        .select_related("reference_answer")
        .prefetch_related("rubric_criteria")
    )
    marks_ready = bool(questions) and all(
        q.text.strip() and q.max_marks is not None and q.max_marks > 0 for q in questions
    )
    answers_ready = marks_ready and all(
        getattr(q, "reference_answer", None) and q.reference_answer.answer_text.strip()
        for q in questions
    )
    rubric_ready = answers_ready and all(
        bool(criteria := list(q.rubric_criteria.all()))
        and all(c.max_points > 0 and c.title.strip() and c.description.strip() for c in criteria)
        and sum((c.max_points for c in criteria), Decimal("0")) == q.max_marks
        for q in questions
    )
    return questions, marks_ready, bool(answers_ready), bool(rubric_ready)
