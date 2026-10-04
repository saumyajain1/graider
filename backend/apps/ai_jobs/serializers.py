from rest_framework import serializers

from .models import AIJob, AIJobAttempt, JobState


class JobFilterSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField(min_value=1, required=False)
    state = serializers.ChoiceField(choices=JobState.choices, required=False)
    active_only = serializers.BooleanField(required=False, default=False)


class JobRetrySerializer(serializers.Serializer):
    confirm_possible_charge = serializers.BooleanField(default=False)


class GradingJobRequestSerializer(serializers.Serializer):
    regrade = serializers.BooleanField(default=False)


class JobSummarySerializer(serializers.ModelSerializer):
    assignment_id = serializers.IntegerField(read_only=True, allow_null=True)
    submission_id = serializers.IntegerField(read_only=True, allow_null=True)
    parent_id = serializers.UUIDField(read_only=True, allow_null=True)
    assignment_title = serializers.CharField(
        source="assignment.title", read_only=True, default="Deleted assignment"
    )
    student_name = serializers.CharField(
        source="submission.student_name", read_only=True, default=""
    )
    question_part_id = serializers.SerializerMethodField()
    question_part_ids = serializers.SerializerMethodField()
    replace_existing = serializers.SerializerMethodField()

    def get_question_part_id(self, obj) -> int | None:
        return obj.input_snapshot.get("options", {}).get("question_part_id")

    def get_question_part_ids(self, obj) -> list[int]:
        return [
            int(step.key.split(":")[-1])
            for step in obj.steps.all()
            if step.key.rpartition(":")[-1].isdecimal()
        ]

    def get_replace_existing(self, obj) -> bool:
        return obj.input_snapshot.get("options", {}).get("replace_existing", False)

    class Meta:
        model = AIJob
        fields = (
            "id",
            "operation",
            "state",
            "assignment_id",
            "submission_id",
            "parent_id",
            "assignment_title",
            "student_name",
            "question_part_id",
            "question_part_ids",
            "replace_existing",
            "completed_steps",
            "total_steps",
            "cancel_requested",
            "error_code",
            "error_message",
            "result_reference",
            "retry_after",
            "created_at",
            "updated_at",
            "finished_at",
        )
        read_only_fields = fields


class JobDetailSerializer(JobSummarySerializer):
    children = JobSummarySerializer(many=True, read_only=True)
    possible_duplicate_charge = serializers.SerializerMethodField()

    class Meta(JobSummarySerializer.Meta):
        fields = (*JobSummarySerializer.Meta.fields, "children", "possible_duplicate_charge")

    def get_possible_duplicate_charge(self, obj) -> bool:
        return (
            AIJobAttempt.objects.filter(
                step__job_id__in=[obj.id, *obj.children.values_list("id", flat=True)],
                state__in=(AIJobAttempt.State.DISPATCHED, AIJobAttempt.State.UNCERTAIN),
            )
            .exclude(step__state=JobState.SUCCEEDED)
            .exists()
        )
