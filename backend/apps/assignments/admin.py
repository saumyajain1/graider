from django.contrib import admin

from .models import Assignment, QuestionPart


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "teacher", "course_name", "updated_at")
    search_fields = ("title", "course_name", "teacher__email")
    list_filter = ("created_at", "updated_at")


@admin.register(QuestionPart)
class QuestionPartAdmin(admin.ModelAdmin):
    list_display = ("part_key", "assignment", "part_type", "max_marks", "display_order")
    list_filter = ("part_type", "created_by_ai")
    search_fields = ("part_key", "text", "assignment__title")
