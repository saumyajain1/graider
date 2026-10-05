from decimal import Decimal

from rest_framework import serializers

from apps.assignments.models import QuestionPart
from apps.uploads import file_api_url

from .models import (
    GradingResult,
    ReferenceAnswer,
    RubricCriterion,
    StudentSubmission,
    SubmissionAnswerPart,
    SubmissionImport,
)
from .services.submission_workflow import criterion_snapshots


class ReferenceAnswerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferenceAnswer
        fields = ("id", "answer_text", "source")
        read_only_fields = ("id",)


class RubricCriterionWriteSerializer(serializers.ModelSerializer):
    max_points = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0.01"))

    def validate(self, attrs):
        question = self.instance.question_part
        points = attrs.get("max_points", self.instance.max_points)
        if question.max_marks is None or question.max_marks <= 0:
            raise serializers.ValidationError(
                {"max_points": "Set positive question total marks first."}
            )
        if points > question.max_marks:
            raise serializers.ValidationError(
                {"max_points": "Criterion points cannot exceed the question total marks."}
            )
        return attrs

    class Meta:
        model = RubricCriterion
        fields = (
            "id",
            "question_part",
            "title",
            "description",
            "max_points",
            "display_order",
            "created_by_ai",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "question_part",
            "display_order",
            "created_by_ai",
            "created_at",
            "updated_at",
        )


class RubricCriterionResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = RubricCriterion
        fields = (
            "id",
            "title",
            "description",
            "max_points",
            "display_order",
            "created_by_ai",
            "created_at",
            "updated_at",
        )


class ReferenceAnswerItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    question_part_id = serializers.IntegerField()
    part_key = serializers.CharField()
    source_label = serializers.CharField(allow_blank=True)
    display_label = serializers.CharField()
    question_text = serializers.CharField()
    max_marks = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    answer_text = serializers.CharField()
    version = serializers.IntegerField(allow_null=True)
    source = serializers.CharField(allow_null=True)


class RubricQuestionSerializer(serializers.Serializer):
    question_part_id = serializers.IntegerField()
    part_key = serializers.CharField()
    source_label = serializers.CharField(allow_blank=True)
    display_label = serializers.CharField()
    question_text = serializers.CharField()
    max_marks = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    criteria = RubricCriterionResponseSerializer(many=True)


class ReferenceAnswerCreateSerializer(serializers.Serializer):
    question_part_id = serializers.IntegerField()
    answer_text = serializers.CharField()

    def validate_question_part_id(self, value):
        assignment = self.context["assignment"]
        if not assignment.question_parts.filter(
            id=value, part_type=QuestionPart.PartType.QUESTION
        ).exists():
            raise serializers.ValidationError("Choose a scored question from this assignment.")
        return value


class RubricCriterionCreateSerializer(serializers.Serializer):
    question_part_id = serializers.IntegerField()
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    max_points = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0.01"))

    def validate(self, attrs):
        question = self.context["assignment"].question_parts.get(id=attrs["question_part_id"])
        if question.max_marks is None or question.max_marks <= 0:
            raise serializers.ValidationError(
                {"max_points": "Set positive question total marks first."}
            )
        if attrs["max_points"] > question.max_marks:
            raise serializers.ValidationError(
                {"max_points": "Criterion points cannot exceed the question total marks."}
            )
        return attrs

    def validate_question_part_id(self, value):
        assignment = self.context["assignment"]
        if not assignment.question_parts.filter(
            id=value, part_type=QuestionPart.PartType.QUESTION
        ).exists():
            raise serializers.ValidationError("Choose a scored question from this assignment.")
        return value


class StudentSubmissionSerializer(serializers.ModelSerializer):
    response_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    response_file_url = serializers.SerializerMethodField()
    response_filename = serializers.SerializerMethodField()

    class Meta:
        model = StudentSubmission
        fields = (
            "id",
            "assignment",
            "student_name",
            "student_identifier",
            "raw_response_text",
            "response_file",
            "response_file_url",
            "response_filename",
            "ingestion_notes",
            "upload_source",
            "grading_status",
            "total_score",
            "last_error",
            "finalized_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "assignment",
            "response_file_url",
            "response_filename",
            "ingestion_notes",
            "upload_source",
            "grading_status",
            "total_score",
            "last_error",
            "finalized_at",
            "created_at",
            "updated_at",
        )

    def get_response_file_url(self, obj) -> str | None:
        return (
            file_api_url("submission-response-file", submission_id=obj.id)
            if obj.response_file
            else None
        )

    def get_response_filename(self, obj) -> str | None:
        return (
            (obj.response_original_filename or obj.response_file.name.split("/")[-1])
            if obj.response_file
            else None
        )


class SubmissionImportSerializer(serializers.ModelSerializer):
    source_file_url = serializers.SerializerMethodField()

    class Meta:
        model = SubmissionImport
        fields = ("id", "original_filename", "source_file_url", "row_count", "created_at")

    def get_source_file_url(self, obj) -> str:
        return file_api_url(
            "submission-import-file", assignment_id=obj.assignment_id, import_id=obj.id
        )


class SubmissionCreateSerializer(serializers.Serializer):
    student_name = serializers.CharField(max_length=255)
    student_identifier = serializers.CharField(max_length=255, allow_blank=True, required=False)
    raw_response_text = serializers.CharField(allow_blank=True, required=False)
    response_file = serializers.FileField(required=False, allow_null=True)


class SubmissionAnswerPartSerializer(serializers.ModelSerializer):
    question_part_id = serializers.IntegerField(source="question_part.id", read_only=True)
    part_key = serializers.CharField(source="question_part.part_key", read_only=True)
    source_label = serializers.CharField(source="question_part.source_label", read_only=True)
    display_label = serializers.CharField(source="question_part.display_label", read_only=True)
    question_text = serializers.CharField(source="question_part.text", read_only=True)

    class Meta:
        model = SubmissionAnswerPart
        fields = (
            "id",
            "question_part_id",
            "part_key",
            "source_label",
            "display_label",
            "question_text",
            "extracted_answer_text",
            "mapping_confidence",
            "created_at",
            "updated_at",
        )


class CriterionResultSerializer(serializers.Serializer):
    criterion_id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    max_points = serializers.DecimalField(max_digits=6, decimal_places=2)
    ai_score = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    final_score = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    ai_feedback = serializers.CharField(allow_blank=True)
    final_feedback = serializers.CharField(allow_blank=True)


class GradingResultSerializer(serializers.ModelSerializer):
    criterion_results = CriterionResultSerializer(many=True, read_only=True)
    question_part_id = serializers.IntegerField(source="question_part.id", read_only=True)
    part_key = serializers.CharField(source="question_part.part_key", read_only=True)
    source_label = serializers.CharField(source="question_part.source_label", read_only=True)
    display_label = serializers.CharField(source="question_part.display_label", read_only=True)
    question_text = serializers.CharField(source="question_part.text", read_only=True)

    class Meta:
        model = GradingResult
        fields = (
            "id",
            "question_part_id",
            "part_key",
            "source_label",
            "display_label",
            "question_text",
            "ai_score",
            "final_score",
            "max_score",
            "ai_feedback",
            "final_feedback",
            "criterion_results",
            "reasoning_summary",
            "confidence_score",
            "needs_review",
            "created_at",
            "updated_at",
        )


class CriterionReviewSerializer(serializers.Serializer):
    criterion_id = serializers.IntegerField()
    final_score = serializers.DecimalField(
        max_digits=6, decimal_places=2, allow_null=True, min_value=0
    )
    final_feedback = serializers.CharField(allow_blank=True)


class GradingResultReviewSerializer(serializers.Serializer):
    criterion_results = CriterionReviewSerializer(many=True, required=False, allow_empty=False)
    final_score = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        allow_null=True,
        required=False,
        min_value=0,
    )
    final_feedback = serializers.CharField(allow_blank=True, required=False)
    needs_review = serializers.BooleanField(required=False)

    def validate(self, attrs):
        result = self.context["grading_result"]
        if "criterion_results" not in attrs:
            if result.criterion_results and "final_score" in attrs:
                raise serializers.ValidationError(
                    {
                        "final_score": "Edit rubric criterion scores; the question total is calculated."
                    }
                )
            return attrs
        rows = [
            dict(row)
            for row in (result.criterion_results or criterion_snapshots(result.question_part))
        ]
        incoming = {row["criterion_id"]: row for row in attrs["criterion_results"]}
        if (
            len(incoming) != len(attrs["criterion_results"])
            or set(incoming) != {row["criterion_id"] for row in rows}
            or not rows
        ):
            raise serializers.ValidationError(
                {"criterion_results": "Include every rubric criterion exactly once."}
            )
        if (
            result.max_score <= 0
            or sum(Decimal(row["max_points"]) for row in rows) != result.max_score
        ):
            raise serializers.ValidationError(
                {"criterion_results": "Set matching question and rubric totals before reviewing."}
            )
        for row in rows:
            edit = incoming[row["criterion_id"]]
            score = edit["final_score"]
            if score is not None and score > Decimal(row["max_points"]):
                raise serializers.ValidationError(
                    {
                        "criterion_results": f"{row['title']}: score cannot exceed {row['max_points']}."
                    }
                )
            row["final_score"] = str(score) if score is not None else None
            row["final_feedback"] = edit["final_feedback"]
        total = (
            sum(Decimal(row["final_score"]) for row in rows)
            if all(row["final_score"] is not None for row in rows)
            else None
        )
        if "final_score" in attrs and attrs["final_score"] != total:
            raise serializers.ValidationError(
                {"final_score": "Total must equal the criterion scores."}
            )
        attrs["criterion_results"] = rows
        attrs["final_score"] = total
        return attrs

    def validate_final_score(self, value):
        grading_result = self.context["grading_result"]
        if value is not None and value > grading_result.max_score:
            raise serializers.ValidationError("Final score cannot exceed the max score.")
        return value

    def normalized_data(self):
        grading_result = self.context["grading_result"]
        return {
            "final_score": self.validated_data.get(
                "final_score",
                grading_result.final_score,
            ),
            "final_feedback": self.validated_data.get(
                "final_feedback",
                grading_result.final_feedback,
            )
            or "",
            "needs_review": self.validated_data.get(
                "needs_review",
                grading_result.needs_review,
            ),
            "criterion_results": self.validated_data.get("criterion_results"),
        }


class SubmissionQuestionReviewSerializer(GradingResultReviewSerializer):
    question_part_id = serializers.IntegerField()
    criterion_results = CriterionReviewSerializer(many=True, allow_empty=False)


class SubmissionGradingSerializer(serializers.Serializer):
    submission = StudentSubmissionSerializer()
    answer_parts = SubmissionAnswerPartSerializer(many=True)
    grading_results = GradingResultSerializer(many=True)
    questions = RubricQuestionSerializer(many=True)
    reference_answers = ReferenceAnswerItemSerializer(many=True)


def build_reference_answer_item(question_part: QuestionPart):
    answer = getattr(question_part, "reference_answer", None)
    return {
        "id": answer.id if answer else None,
        "question_part_id": question_part.id,
        "part_key": question_part.part_key,
        "source_label": question_part.source_label,
        "display_label": question_part.display_label,
        "question_text": question_part.text,
        "max_marks": question_part.max_marks,
        "answer_text": answer.answer_text if answer else "",
        "version": answer.version if answer else None,
        "source": answer.source if answer else None,
    }


def build_rubric_question_item(question_part: QuestionPart):
    return {
        "question_part_id": question_part.id,
        "part_key": question_part.part_key,
        "source_label": question_part.source_label,
        "display_label": question_part.display_label,
        "question_text": question_part.text,
        "max_marks": question_part.max_marks,
        "criteria": RubricCriterionResponseSerializer(
            question_part.rubric_criteria.all(),
            many=True,
        ).data,
    }


class TargetQuestionSerializer(serializers.Serializer):
    question_part_id = serializers.IntegerField(required=False, allow_null=True)


class ArtifactGenerationSerializer(TargetQuestionSerializer):
    replace_existing = serializers.BooleanField(default=False)


class SubmissionCsvUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
