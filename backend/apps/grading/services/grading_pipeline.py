import os
from textwrap import dedent

from apps.assignments.models import Assignment, QuestionPart

from .generation import build_shared_context, format_question_label
from .openai_client import OpenAIChatService
from .schemas import GeneratedQuestionGradeSchema, SubmissionAnswerMappingSchema

MAPPING_MODEL = os.getenv("OPENAI_MAPPING_MODEL", "gpt-6-luna")
GRADING_MODEL = os.getenv("OPENAI_GRADING_MODEL", "gpt-6-luna")


def map_submission_answers(
    assignment: Assignment,
    submission_text: str,
    question_parts: list[QuestionPart],
):
    service = OpenAIChatService()
    question_listing = "\n".join(
        dedent(
            f"""
            - internal_key={question.part_key}
              source_label={format_question_label(question)}
              text={question.text}
              shared_context={build_shared_context(question) or "None"}
            """
        ).strip()
        for question in question_parts
    )

    return service.parse(
        user=assignment.teacher,
        operation="answer_mapping",
        model=MAPPING_MODEL,
        response_format=SubmissionAnswerMappingSchema,
        system_prompt=dedent(
            """
            You map a student's freeform submission to structured assignment question parts.
            For each question part, extract the most relevant student answer text.
            If the student did not answer that question, return an empty string.
            Return the exact internal_key values you were given as part_key in the response.
            """
        ).strip(),
        user_prompt=dedent(
            f"""
            Assignment title: {assignment.title}
            Question parts:
            {question_listing}

            Full student submission:
            {submission_text}
            """
        ).strip(),
    )


def grade_question_part(
    question_part: QuestionPart,
    reference_answer_text: str,
    rubric_text: str,
    extracted_answer_text: str,
):
    service = OpenAIChatService()
    shared_context = build_shared_context(question_part)

    return service.parse(
        user=question_part.assignment.teacher,
        operation="submission_grading",
        model=GRADING_MODEL,
        response_format=GeneratedQuestionGradeSchema,
        system_prompt=dedent(
            """
            You grade one student answer against a question, reference answer, and rubric.
            Use both the reference answer and each rubric criterion to assess the student answer.
            Return every supplied criterion_id exactly once with its own score and concise feedback.
            Each score must be between zero and that criterion's maximum, with at most two decimal
            places. Explain deductions using evidence from the student answer. Do not invent criteria.
            Also return overall feedback, a short reasoning summary, and a review flag.
            Question and submission totals are calculated from the criterion scores by the app.
            """
        ).strip(),
        user_prompt=dedent(
            f"""
            Question label: {format_question_label(question_part)}
            Internal key: {question_part.part_key}
            Question part:
            {question_part.text}

            Shared context:
            {shared_context or "None"}

            Max score: {question_part.max_marks if question_part.max_marks is not None else "Not specified"}

            Reference answer:
            {reference_answer_text}

            Rubric:
            {rubric_text}

            Student answer excerpt:
            {extracted_answer_text}
            """
        ).strip(),
    )
