import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class JobState(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    RETRY_WAIT = "retry_wait", "Waiting to retry"
    PAUSED_QUOTA = "paused_quota", "Paused by quota"
    NEEDS_ATTENTION = "needs_attention", "Needs attention"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    SUPERSEDED = "superseded", "Inputs changed"


ACTIVE_STATES = (
    JobState.QUEUED,
    JobState.RUNNING,
    JobState.RETRY_WAIT,
    JobState.PAUSED_QUOTA,
    JobState.NEEDS_ATTENTION,
)
RETRYABLE_STATES = (JobState.FAILED, JobState.PAUSED_QUOTA, JobState.NEEDS_ATTENTION)


class AIJobCoordinator(models.Model):
    """Lock this singleton during admission and state changes, including across containers."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)


class AIJob(models.Model):
    class Operation(models.TextChoices):
        QUESTIONS = "questions", "Extract questions"
        REFERENCES = "reference_answers", "Generate reference answers"
        RUBRIC = "rubric", "Generate rubric"
        GRADE = "grade_submission", "Grade submission"
        BATCH = "grade_batch", "Grade batch"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    assignment = models.ForeignKey("assignments.Assignment", null=True, on_delete=models.SET_NULL)
    submission = models.ForeignKey(
        "grading.StudentSubmission", null=True, blank=True, on_delete=models.SET_NULL
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    operation = models.CharField(max_length=32, choices=Operation.choices)
    state = models.CharField(max_length=20, choices=JobState.choices, default=JobState.QUEUED)
    priority = models.PositiveSmallIntegerField(default=10)
    request_key = models.CharField(max_length=128, null=True, blank=True)
    request_fingerprint = models.CharField(max_length=64)
    input_snapshot = models.JSONField()
    input_fingerprint = models.CharField(max_length=64)
    version = models.PositiveSmallIntegerField(default=1)
    completed_steps = models.PositiveIntegerField(default=0)
    total_steps = models.PositiveIntegerField(default=0)
    cancel_requested = models.BooleanField(default=False)
    error_code = models.CharField(max_length=40, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    result_reference = models.JSONField(default=dict, blank=True)
    retry_after = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [
            models.Index(fields=("owner", "state", "created_at"), name="ai_job_owner_state_idx"),
            models.Index(fields=("state", "priority", "created_at"), name="ai_job_queue_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=("owner", "request_key"), name="ai_job_request_key"),
            models.CheckConstraint(
                condition=Q(completed_steps__lte=models.F("total_steps")),
                name="ai_job_progress_bounds",
            ),
        ]

    def save(self, *args, **kwargs):
        # Inputs are a frozen recipe, not editable job metadata. Bulk updates are reserved
        # for internal state transitions; no API accepts snapshot writes.
        if not self._state.adding:
            immutable = (
                "owner_id",
                "operation",
                "input_snapshot",
                "input_fingerprint",
                "request_key",
                "request_fingerprint",
                "version",
            )
            original = type(self).objects.filter(pk=self.pk).values(*immutable).first()
            if original and any(original[field] != getattr(self, field) for field in immutable):
                raise ValueError("Job inputs and identity cannot be changed after admission.")
        super().save(*args, **kwargs)


class AIJobTarget(models.Model):
    """One active claim per affected question/submission, including bulk/single overlap."""

    job = models.ForeignKey(AIJob, on_delete=models.CASCADE, related_name="targets")
    key = models.CharField(max_length=100)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("job", "key"), name="ai_job_target_once"),
            models.UniqueConstraint(
                fields=("key",), condition=Q(active=True), name="ai_job_active_target"
            ),
        ]


class AIJobStep(models.Model):
    job = models.ForeignKey(AIJob, on_delete=models.CASCADE, related_name="steps")
    key = models.CharField(max_length=100)
    position = models.PositiveIntegerField()
    state = models.CharField(max_length=20, choices=JobState.choices, default=JobState.QUEUED)
    checkpoint = models.JSONField(default=dict, blank=True)
    claim_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("state", "lease_expires_at"), name="ai_step_lease_idx")]
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("job", "key"), name="ai_job_step_once"),
            models.UniqueConstraint(fields=("job", "position"), name="ai_job_step_order"),
        ]


class AIJobAttempt(models.Model):
    class State(models.TextChoices):
        RESERVED = "reserved", "Usage reserved"
        DISPATCHED = "dispatched", "Request dispatched"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed safely"
        UNCERTAIN = "uncertain", "Response or billing unknown"

    step = models.ForeignKey(AIJobStep, on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveIntegerField()
    claim_token = models.UUIDField()
    usage = models.OneToOneField(
        "grading.LLMUsage", null=True, blank=True, on_delete=models.SET_NULL
    )
    state = models.CharField(max_length=20, choices=State.choices, default=State.RESERVED)
    output = models.JSONField(default=dict, blank=True)
    provider_request_id = models.CharField(max_length=100, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("number", "id")
        constraints = [
            models.UniqueConstraint(fields=("step", "number"), name="ai_job_attempt_once")
        ]
