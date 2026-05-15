from pathlib import Path

from django.db import models
from django.utils import timezone

from apps.assignments.models import QuestionPart


def submission_source_upload_to(instance, filename):
    safe_name = Path(filename).name
    timestamp = timezone.now().strftime("%Y/%m/%d")
    return f"submissions/{instance.assignment.teacher_id}/{instance.assignment_id}/{timestamp}/{safe_name}"


class ReferenceAnswer(models.Model):
    class Source(models.TextChoices):
        AI = "ai", "AI"
        TEACHER = "teacher", "Teacher"

    question_part = models.OneToOneField(
        QuestionPart,
        on_delete=models.CASCADE,
        related_name="reference_answer",
    )
    answer_text = models.TextField()
    version = models.PositiveIntegerField(default=1)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.AI,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("question_part__display_order", "id")

    def __str__(self):
        return f"Reference answer for {self.question_part.part_key}"


class RubricCriterion(models.Model):
    question_part = models.ForeignKey(
        QuestionPart,
        on_delete=models.CASCADE,
        related_name="rubric_criteria",
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    max_points = models.DecimalField(max_digits=6, decimal_places=2)
    display_order = models.PositiveIntegerField(default=0)
    created_by_ai = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_order", "id")

    def __str__(self):
        return f"{self.question_part.part_key}: {self.title}"


class StudentSubmission(models.Model):
    class UploadSource(models.TextChoices):
        MANUAL = "manual", "Manual"
        FILE = "file", "File"
        CSV = "csv", "CSV"

    class GradingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        GRADING = "grading", "Grading"
        GRADED = "graded", "Graded"
        REVIEWED = "reviewed", "Reviewed"
        FINALIZED = "finalized", "Finalized"
        FAILED = "failed", "Failed"

    assignment = models.ForeignKey(
        "assignments.Assignment",
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    student_name = models.CharField(max_length=255)
    student_identifier = models.CharField(max_length=255, blank=True)
    raw_response_text = models.TextField(blank=True)
    response_file = models.FileField(
        upload_to=submission_source_upload_to,
        blank=True,
        null=True,
    )
    ingestion_notes = models.TextField(blank=True)
    upload_source = models.CharField(
        max_length=20,
        choices=UploadSource.choices,
        default=UploadSource.MANUAL,
    )
    grading_status = models.CharField(
        max_length=20,
        choices=GradingStatus.choices,
        default=GradingStatus.PENDING,
    )
    total_score = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )
    last_error = models.TextField(blank=True)
    finalized_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("student_name", "id")

    def __str__(self):
        return f"{self.assignment_id}: {self.student_name}"


class SubmissionAnswerPart(models.Model):
    submission = models.ForeignKey(
        StudentSubmission,
        on_delete=models.CASCADE,
        related_name="answer_parts",
    )
    question_part = models.ForeignKey(
        QuestionPart,
        on_delete=models.CASCADE,
        related_name="submission_answer_parts",
    )
    extracted_answer_text = models.TextField(blank=True)
    mapping_confidence = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("question_part__display_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("submission", "question_part"),
                name="unique_answer_part_per_submission_question",
            )
        ]


class GradingResult(models.Model):
    submission = models.ForeignKey(
        StudentSubmission,
        on_delete=models.CASCADE,
        related_name="grading_results",
    )
    question_part = models.ForeignKey(
        QuestionPart,
        on_delete=models.CASCADE,
        related_name="grading_results",
    )
    ai_score = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    final_score = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    max_score = models.DecimalField(max_digits=6, decimal_places=2)
    ai_feedback = models.TextField(blank=True)
    final_feedback = models.TextField(blank=True)
    reasoning_summary = models.TextField(blank=True)
    confidence_score = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        blank=True,
        null=True,
    )
    needs_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("question_part__display_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("submission", "question_part"),
                name="unique_grading_result_per_submission_question",
            )
        ]
