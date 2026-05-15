from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GeneratedQuestionPartSchema(BaseModel):
    part_type: Literal["context", "question"] = "question"
    source_label: str | None = None
    text: str = Field(min_length=1)
    max_marks: float | None = None
    parent_key: str | None = None

    @field_validator("max_marks")
    @classmethod
    def validate_max_marks(cls, value):
        if value is not None and value < 0:
            raise ValueError("max_marks must be non-negative.")
        return value


class GeneratedQuestionSetSchema(BaseModel):
    parts: list[GeneratedQuestionPartSchema]


class GeneratedReferenceAnswerSchema(BaseModel):
    answer_text: str = Field(min_length=1)


class GeneratedRubricCriterionSchema(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    max_points: float = Field(ge=0)


class GeneratedRubricSchema(BaseModel):
    criteria: list[GeneratedRubricCriterionSchema]


class SubmissionAnswerMappingItemSchema(BaseModel):
    part_key: str = Field(min_length=1)
    extracted_answer_text: str = ""
    mapping_confidence: float | None = Field(default=None, ge=0, le=1)


class SubmissionAnswerMappingSchema(BaseModel):
    answers: list[SubmissionAnswerMappingItemSchema]


class GeneratedQuestionGradeSchema(BaseModel):
    score: float = Field(ge=0)
    feedback: str = Field(min_length=1)
    reasoning_summary: str = Field(min_length=1)
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    needs_review: bool = False
