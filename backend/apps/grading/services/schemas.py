from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GeneratedQuestionPartSchema(BaseModel):
    part_type: Literal["context", "question"] = "question"
    source_label: str | None = None
    text: str = Field(min_length=1)
    max_marks: float | None = None
    parent_key: str | None = None

    @field_validator("max_marks")
    @classmethod
    def validate_max_marks(cls, value):
        if value is not None and (
            not Decimal(str(value)).is_finite()
            or value <= 0
            or value > 9999.99
            or Decimal(str(value)) != Decimal(str(value)).quantize(Decimal("0.01"))
        ):
            raise ValueError(
                "max_marks must be positive, at most 9999.99, and have at most two decimal places."
            )
        return value


class GeneratedQuestionSetSchema(BaseModel):
    parts: list[GeneratedQuestionPartSchema] = Field(min_length=1)

    @model_validator(mode="after")
    def require_scored_marks(self):
        questions = [part for part in self.parts if part.part_type == "question"]
        if not questions or any(part.max_marks is None for part in questions):
            raise ValueError("Every scored question must have a positive total mark allocation.")
        return self


class GeneratedReferenceAnswerSchema(BaseModel):
    answer_text: str = Field(min_length=1)


class GeneratedRubricCriterionSchema(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    max_points: float = Field(gt=0, le=9999.99, allow_inf_nan=False)


class GeneratedRubricSchema(BaseModel):
    criteria: list[GeneratedRubricCriterionSchema] = Field(min_length=1)


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
