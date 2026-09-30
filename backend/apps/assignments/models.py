from django.conf import settings
from django.db import models

from apps.uploads import object_key


def assignment_source_upload_to(instance, filename):
    return object_key(f"assignments/{instance.teacher_id}", filename)


class Assignment(models.Model):
    class WorkflowStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUESTIONS_READY = "questions_ready", "Questions Ready"
        REFERENCE_ANSWERS_READY = "reference_answers_ready", "Reference Answers Ready"
        RUBRIC_READY = "rubric_ready", "Rubric Ready"
        SUBMISSIONS_UPLOADED = "submissions_uploaded", "Submissions Uploaded"
        REVIEW_READY = "review_ready", "Review Ready"
        FINALIZED = "finalized", "Finalized"

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
    source_original_filename = models.CharField(max_length=255, blank=True)
    ingestion_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    @property
    def workflow_status(self):
        submissions = getattr(self, "submissions", None)
        if submissions is not None and submissions.exists():
            if submissions.exclude(grading_status="finalized").count() == 0:
                return self.WorkflowStatus.FINALIZED
            if submissions.filter(grading_status__in=["graded", "reviewed", "finalized"]).exists():
                return self.WorkflowStatus.REVIEW_READY
            return self.WorkflowStatus.SUBMISSIONS_UPLOADED

        question_parts = self.question_parts.filter(part_type=QuestionPart.PartType.QUESTION)
        if not question_parts.exists():
            return self.WorkflowStatus.DRAFT

        if all(question.rubric_criteria.exists() for question in question_parts):
            return self.WorkflowStatus.RUBRIC_READY

        if all(hasattr(question, "reference_answer") for question in question_parts):
            return self.WorkflowStatus.REFERENCE_ANSWERS_READY

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
