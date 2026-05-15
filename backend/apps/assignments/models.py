from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone


def assignment_source_upload_to(instance, filename):
    safe_name = Path(filename).name
    timestamp = timezone.now().strftime("%Y/%m/%d")
    return f"assignments/{instance.teacher_id}/{timestamp}/{safe_name}"


class Assignment(models.Model):
    class WorkflowStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUESTIONS_READY = "questions_ready", "Questions Ready"

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    title = models.CharField(max_length=255)
    course_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    raw_assignment_text = models.TextField(blank=True)
    source_file = models.FileField(
        upload_to=assignment_source_upload_to,
        blank=True,
        null=True,
    )
    ingestion_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    @property
    def workflow_status(self):
        question_parts = self.question_parts.filter(part_type=QuestionPart.PartType.QUESTION)
        if not question_parts.exists():
            return self.WorkflowStatus.DRAFT

        return self.WorkflowStatus.QUESTIONS_READY

    def __str__(self):
        return self.title


class QuestionPart(models.Model):
    class PartType(models.TextChoices):
        CONTEXT = "context", "Context"
        QUESTION = "question", "Question"

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="question_parts",
    )
    part_key = models.CharField(max_length=50)
    source_label = models.CharField(max_length=100, blank=True)
    parent_key = models.CharField(max_length=50, blank=True)
    part_type = models.CharField(
        max_length=20,
        choices=PartType.choices,
        default=PartType.QUESTION,
    )
    text = models.TextField()
    max_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
    )
    display_order = models.PositiveIntegerField(default=0)
    created_by_ai = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("assignment", "part_key"),
                name="unique_question_part_key_per_assignment",
            )
        ]

    def __str__(self):
        return f"{self.assignment_id}:{self.part_key}"

    @property
    def display_label(self):
        return self.source_label or self.part_key
