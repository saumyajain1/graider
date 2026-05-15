from rest_framework import serializers

from apps.assignments.models import QuestionPart

from .models import (
    GradingResult,
    ReferenceAnswer,
    RubricCriterion,
    StudentSubmission,
    SubmissionAnswerPart,
)


class ReferenceAnswerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferenceAnswer
        fields = ("id", "answer_text", "source")
        read_only_fields = ("id",)


class RubricCriterionWriteSerializer(serializers.ModelSerializer):
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
        if not assignment.question_parts.filter(id=value).exists():
            raise serializers.ValidationError("Question part does not belong to this assignment.")
        return value


class RubricCriterionCreateSerializer(serializers.Serializer):
    question_part_id = serializers.IntegerField()
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    max_points = serializers.DecimalField(max_digits=6, decimal_places=2)

    def validate_question_part_id(self, value):
        assignment = self.context["assignment"]
        if not assignment.question_parts.filter(id=value).exists():
            raise serializers.ValidationError("Question part does not belong to this assignment.")
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

    def get_response_file_url(self, obj):
        return obj.response_file.url if obj.response_file else None

    def get_response_filename(self, obj):
        return obj.response_file.name.split("/")[-1] if obj.response_file else None


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


class GradingResultSerializer(serializers.ModelSerializer):
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
            "reasoning_summary",
            "confidence_score",
            "needs_review",
            "created_at",
            "updated_at",
        )


class GradingResultReviewSerializer(serializers.Serializer):
    final_score = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        allow_null=True,
        required=False,
        min_value=0,
    )
    final_feedback = serializers.CharField(allow_blank=True, required=False)
    needs_review = serializers.BooleanField(required=False)

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
        }


class SubmissionGradingSerializer(serializers.Serializer):
    submission = StudentSubmissionSerializer()
    answer_parts = SubmissionAnswerPartSerializer(many=True)
    grading_results = GradingResultSerializer(many=True)


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
