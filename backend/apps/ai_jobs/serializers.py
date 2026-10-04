from rest_framework import serializers

from .models import AIJob, AIJobAttempt, JobState


class JobFilterSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField(min_value=1, required=False)
    state = serializers.ChoiceField(choices=JobState.choices, required=False)


class JobRetrySerializer(serializers.Serializer):
    confirm_possible_charge = serializers.BooleanField(default=False)


class JobSummarySerializer(serializers.ModelSerializer):
    assignment_id = serializers.IntegerField(read_only=True, allow_null=True)
    submission_id = serializers.IntegerField(read_only=True, allow_null=True)
    parent_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = AIJob
        fields = (
            "id",
            "operation",
            "state",
            "assignment_id",
            "submission_id",
            "parent_id",
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
