from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from apps.uploads import (
    check_file_size,
    check_text_length,
    delete_name_after_commit,
    file_api_url,
    original_name,
    stored_upload,
)

from .models import Assignment, QuestionPart
from .services import extract_text_from_uploaded_file, is_supported_text_upload


def build_part_key(assignment):
    existing_keys = set(assignment.question_parts.values_list("part_key", flat=True))
    index = 1
    while True:
        candidate = f"Q{index}"
        if candidate not in existing_keys:
            return candidate
        index += 1


class AssignmentSerializer(serializers.ModelSerializer):
    source_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    source_file_url = serializers.SerializerMethodField()
    source_filename = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    question_count = serializers.SerializerMethodField()
    submission_count = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = (
            "id",
            "title",
            "course_name",
            "description",
            "raw_assignment_text",
            "source_file",
            "source_file_url",
            "source_filename",
            "ingestion_notes",
            "status",
            "question_count",
            "submission_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "source_file_url",
            "source_filename",
            "ingestion_notes",
            "status",
            "question_count",
            "submission_count",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        uploaded_file = attrs.get("source_file")
        if uploaded_file is not None and not is_supported_text_upload(uploaded_file):
            raise serializers.ValidationError(
                {"source_file": "Only .txt and .pdf files are supported."}
            )
        if uploaded_file is not None:
            check_file_size(uploaded_file, settings.GRAIDER_MAX_UPLOAD_BYTES)
        if "raw_assignment_text" in attrs:
            check_text_length(
                attrs["raw_assignment_text"],
                settings.GRAIDER_MAX_ASSIGNMENT_CHARS,
                "Assignment text",
            )

        if self.instance is None:
            raw_text = attrs.get("raw_assignment_text", "").strip()
            if not raw_text and uploaded_file is None:
                raise serializers.ValidationError(
                    {"raw_assignment_text": ("Provide assignment text or upload a .txt/.pdf file.")}
                )
        return attrs

    def create(self, validated_data):
        uploaded_file = validated_data.pop("source_file", None)
        extracted_text = ""
        note = ""

        if uploaded_file is not None:
            extracted_text, note = extract_text_from_uploaded_file(uploaded_file)

        raw_text = validated_data.get("raw_assignment_text", "").strip()
        if not raw_text:
            if not extracted_text:
                raise serializers.ValidationError(
                    {"source_file": (note or "No extractable text was found in the uploaded file.")}
                )
            validated_data["raw_assignment_text"] = extracted_text
        validated_data["ingestion_notes"] = note

        assignment = Assignment(
            teacher=self.context["request"].user,
            **validated_data,
        )
        if uploaded_file is not None:
            assignment.source_original_filename = original_name(uploaded_file)
            with stored_upload(assignment.source_file, uploaded_file):
                with transaction.atomic():
                    assignment.save()
        else:
            assignment.save()

        return assignment

    def update(self, instance, validated_data):
        uploaded_file = validated_data.pop("source_file", None)
        note = instance.ingestion_notes
        raw_text_provided = "raw_assignment_text" in validated_data

        if uploaded_file is not None:
            extracted_text, note = extract_text_from_uploaded_file(uploaded_file)
            if not raw_text_provided and extracted_text:
                instance.raw_assignment_text = extracted_text
            if not raw_text_provided and not extracted_text:
                raise serializers.ValidationError(
                    {"source_file": (note or "No extractable text was found in the uploaded file.")}
                )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.ingestion_notes = note
        if uploaded_file is not None:
            old_storage = instance.source_file.storage
            old_name = instance.source_file.name
            instance.source_original_filename = original_name(uploaded_file)
            with stored_upload(instance.source_file, uploaded_file):
                with transaction.atomic():
                    instance.save()
                    delete_name_after_commit(old_storage, old_name)
        else:
            instance.save()
        return instance

    def get_source_file_url(self, obj) -> str | None:
        return (
            file_api_url("assignment-source-file", assignment_id=obj.id)
            if obj.source_file
            else None
        )

    def get_source_filename(self, obj) -> str | None:
        return (
            (obj.source_original_filename or obj.source_file.name.split("/")[-1])
            if obj.source_file
            else None
        )

    def get_status(self, obj) -> str:
        return obj.workflow_status

    def get_question_count(self, obj) -> int:
        return obj.question_parts.filter(part_type=QuestionPart.PartType.QUESTION).count()

    def get_submission_count(self, obj) -> int:
        submissions = getattr(obj, "submissions", None)
        return submissions.count() if submissions is not None else 0


class QuestionPartSerializer(serializers.ModelSerializer):
    display_label = serializers.SerializerMethodField()

    class Meta:
        model = QuestionPart
        fields = (
            "id",
            "assignment",
            "part_key",
            "source_label",
            "display_label",
            "parent_key",
            "part_type",
            "text",
            "max_marks",
            "display_order",
            "created_by_ai",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "assignment",
            "part_key",
            "display_label",
            "display_order",
            "created_by_ai",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        assignment = self.context["assignment"]
        display_order = assignment.question_parts.count()
        part_key = build_part_key(assignment)
        source_label = (validated_data.pop("source_label", "") or part_key).strip()
        return QuestionPart.objects.create(
            assignment=assignment,
            part_key=part_key,
            source_label=source_label,
            display_order=display_order,
            **validated_data,
        )

    def get_display_label(self, obj) -> str:
        return obj.display_label


class QuestionGenerateSerializer(serializers.Serializer):
    replace_existing = serializers.BooleanField(default=True)


class QuestionReorderSerializer(serializers.Serializer):
    question_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
