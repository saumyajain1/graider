from rest_framework import serializers

from apps.assignments.models import QuestionPart

from .models import ReferenceAnswer, RubricCriterion


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
