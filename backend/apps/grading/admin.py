from django.contrib import admin

from .models import (
    GradingResult,
    LLMUsage,
    ReferenceAnswer,
    RubricCriterion,
    StudentSubmission,
    SubmissionAnswerPart,
)


@admin.register(LLMUsage)
class LLMUsageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "operation", "model", "status", "total_tokens", "reserved_tokens")
    list_filter = ("operation", "status", "model")
    search_fields = ("user__email", "provider_request_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReferenceAnswer)
class ReferenceAnswerAdmin(admin.ModelAdmin):
    list_display = ("question_part", "source", "version", "updated_at")
    search_fields = ("question_part__part_key", "answer_text")


@admin.register(RubricCriterion)
class RubricCriterionAdmin(admin.ModelAdmin):
    list_display = ("title", "question_part", "max_points", "display_order", "created_by_ai")
    search_fields = ("title", "description", "question_part__part_key")
    list_filter = ("created_by_ai",)


@admin.register(StudentSubmission)
class StudentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("student_name", "assignment", "grading_status", "total_score", "updated_at")
    search_fields = ("student_name", "student_identifier", "assignment__title")
    list_filter = ("grading_status", "upload_source")


@admin.register(SubmissionAnswerPart)
class SubmissionAnswerPartAdmin(admin.ModelAdmin):
    list_display = ("submission", "question_part", "mapping_confidence", "updated_at")
    search_fields = ("submission__student_name", "question_part__part_key", "extracted_answer_text")


@admin.register(GradingResult)
class GradingResultAdmin(admin.ModelAdmin):
    list_display = ("submission", "question_part", "ai_score", "final_score", "needs_review")
    search_fields = ("submission__student_name", "question_part__part_key", "ai_feedback")
    list_filter = ("needs_review",)
