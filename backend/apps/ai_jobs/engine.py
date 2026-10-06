import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from pydantic import ValidationError as SchemaValidationError

from apps.grading.models import LLMUsage
from apps.grading.services.openai_client import (
    LLMConfigurationError,
    LLMGenerationError,
    LLMSpendLimitError,
    LLMTransientError,
    public_llm_error,
)
from apps.grading.services.usage import LLMQuotaExceeded, finish_usage
from config.ai_metrics import metric

from .accounting import ClaimLost, RecipeService, assert_claim
from .models import ACTIVE_STATES, AIJob, AIJobAttempt, AIJobStep, JobState
from .publication import inputs_match, lock_inputs, publish
from .recipes import execute_recipe
from .services import lock_coordinator
from .snapshots import OUTPUT_SCHEMA_VERSION, PROMPT_VERSION, SNAPSHOT_VERSION


def supported(job):
    snapshot = job.input_snapshot
    return (
        job.version == SNAPSHOT_VERSION
        and snapshot.get("snapshot_version") == SNAPSHOT_VERSION
        and snapshot.get("prompt_version") == PROMPT_VERSION
        and snapshot.get("output_schema_version") == OUTPUT_SCHEMA_VERSION
    )


def set_state(job, state, code="", message=""):
    job.state, job.error_code, job.error_message = state, code, message
    job.finished_at = None if state in ACTIVE_STATES else timezone.now()
    job.save(update_fields=("state", "error_code", "error_message", "finished_at", "updated_at"))
    if state not in ACTIVE_STATES:
        job.targets.update(active=False)
    job.steps.exclude(state=JobState.SUCCEEDED).update(
        state=state, claim_token=None, lease_expires_at=None, heartbeat_at=None
    )


def refresh_parent(parent_id):
    if not parent_id:
        return
    parent = AIJob.objects.get(pk=parent_id)
    children = parent.children.all()
    states = set(children.values_list("state", flat=True))
    parent.completed_steps = children.aggregate(total=Sum("completed_steps"))["total"] or 0
    parent.total_steps = children.aggregate(total=Sum("total_steps"))["total"] or 0
    if states == {JobState.SUCCEEDED}:
        state = JobState.SUCCEEDED
    elif JobState.RUNNING in states:
        state = JobState.RUNNING
    elif states & {JobState.QUEUED, JobState.RETRY_WAIT}:
        state = JobState.QUEUED
    elif JobState.NEEDS_ATTENTION in states:
        state = JobState.NEEDS_ATTENTION
    elif JobState.PAUSED_QUOTA in states:
        state = JobState.PAUSED_QUOTA
    elif parent.cancel_requested:
        state = JobState.CANCELLED
    elif states == {JobState.SUPERSEDED}:
        state = JobState.SUPERSEDED
    else:
        state = JobState.FAILED
    parent.state = state
    parent.finished_at = None if state in ACTIVE_STATES else timezone.now()
    parent.save(
        update_fields=("completed_steps", "total_steps", "state", "finished_at", "updated_at")
    )


def recover_expired(now):
    for step in AIJobStep.objects.filter(
        state=JobState.RUNNING, lease_expires_at__lte=now
    ).select_related("job"):
        job = step.job
        for attempt in step.attempts.filter(state=AIJobAttempt.State.RESERVED).select_related(
            "usage"
        ):
            if attempt.usage and attempt.usage.status == LLMUsage.Status.PENDING:
                finish_usage(attempt.usage, status=LLMUsage.Status.FAILED)
            attempt.state = AIJobAttempt.State.FAILED
            attempt.save(update_fields=("state",))
        step.attempts.filter(state=AIJobAttempt.State.SUCCEEDED, output={}).update(
            state=AIJobAttempt.State.UNCERTAIN
        )
        dispatched = list(
            step.attempts.filter(state=AIJobAttempt.State.DISPATCHED).select_related("usage")
        )
        for attempt in dispatched:
            if attempt.usage and attempt.usage.status == LLMUsage.Status.PENDING:
                finish_usage(attempt.usage, status=LLMUsage.Status.UNCERTAIN)
            attempt.state = AIJobAttempt.State.UNCERTAIN
            attempt.save(update_fields=("state",))
        if job.cancel_requested:
            set_state(job, JobState.CANCELLED)
        elif dispatched or step.attempts.filter(state=AIJobAttempt.State.UNCERTAIN).exists():
            set_state(
                job,
                JobState.NEEDS_ATTENTION,
                "uncertain_charge",
                "A request may have been charged. Confirm possible additional charges to retry.",
            )
        else:
            # Successful provider responses are replayed by RecipeService. Claims lost
            # before dispatch can also safely resume; no provider side effect occurred.
            step.state, step.claim_token, step.lease_expires_at = JobState.QUEUED, None, None
            step.save(update_fields=("state", "claim_token", "lease_expires_at"))
            set_state(job, JobState.QUEUED)
        refresh_parent(job.parent_id)


def publish_ready():
    jobs = AIJob.objects.filter(state=JobState.QUEUED, completed_steps__gt=0).exclude(
        operation=AIJob.Operation.BATCH
    )
    for job in jobs:
        if job.completed_steps != job.total_steps:
            continue
        if job.cancel_requested:
            set_state(job, JobState.CANCELLED)
        elif not supported(job):
            set_state(
                job,
                JobState.NEEDS_ATTENTION,
                "unsupported_version",
                "This job version is unsupported by this worker.",
            )
        elif not inputs_match(job):
            set_state(
                job, JobState.SUPERSEDED, "inputs_changed", "Inputs changed. Start a new request."
            )
        else:
            lock_inputs(job)
            if not inputs_match(job):
                set_state(
                    job,
                    JobState.SUPERSEDED,
                    "inputs_changed",
                    "Inputs changed. Start a new request.",
                )
            else:
                try:
                    # Savepoint rolls back every public grade/artifact if publication fails.
                    with transaction.atomic():
                        result = publish(job)
                except (LLMGenerationError, SchemaValidationError):
                    set_state(
                        job,
                        JobState.NEEDS_ATTENTION,
                        "publication_review",
                        "Saved results need review before publication; existing results are preserved.",
                    )
                else:
                    job.result_reference = result
                    job.save(update_fields=("result_reference", "updated_at"))
                    set_state(job, JobState.SUCCEEDED)
                    transaction.on_commit(
                        lambda job_id=str(job.pk), operation=job.operation: metric(
                            "results_committed", job_id=job_id, operation=operation
                        )
                    )
        refresh_parent(job.parent_id)


def claim_next():
    if not settings.GRAIDER_AI_JOBS_ENABLED:
        return None
    with transaction.atomic():
        lock_coordinator()
        now = timezone.now()
        recover_expired(now)
        publish_ready()
        for parent_id in AIJob.objects.filter(
            operation=AIJob.Operation.BATCH, state__in=ACTIVE_STATES
        ).values_list("id", flat=True):
            refresh_parent(parent_id)
        if (
            AIJobStep.objects.filter(state=JobState.RUNNING, lease_expires_at__gt=now).count()
            >= settings.GRAIDER_AI_CONCURRENCY
        ):
            return None
        candidates = list(
            AIJob.objects.filter(
                state__in=(JobState.QUEUED, JobState.RETRY_WAIT), cancel_requested=False
            )
            .filter(Q(retry_after__isnull=True) | Q(retry_after__lte=now))
            .exclude(operation=AIJob.Operation.BATCH)
        )
        # Keep students in a rolling window, yielding between questions to interactive work.
        opened = list(
            AIJob.objects.filter(
                operation=AIJob.Operation.GRADE,
                state__in=(JobState.QUEUED, JobState.RUNNING, JobState.RETRY_WAIT),
            )
            .filter(Q(completed_steps__gt=0) | Q(state=JobState.RUNNING))
            .order_by("created_at")
            .values_list("id", flat=True)
        )
        allowed = set(opened[: settings.GRAIDER_AI_STUDENT_CONCURRENCY])
        room = settings.GRAIDER_AI_STUDENT_CONCURRENCY - len(allowed)
        candidates.sort(
            key=lambda job: (
                0
                if (now - job.updated_at).total_seconds() >= settings.GRAIDER_AI_FAIRNESS_SECONDS
                else job.priority,
                job.updated_at,
                job.created_at,
            )
        )
        for job in candidates:
            if job.operation == AIJob.Operation.GRADE and job.id not in allowed and room <= 0:
                continue
            if not supported(job):
                set_state(
                    job,
                    JobState.NEEDS_ATTENTION,
                    "unsupported_version",
                    "This job version is unsupported by this worker.",
                )
                refresh_parent(job.parent_id)
                continue
            if not inputs_match(job):
                set_state(
                    job,
                    JobState.SUPERSEDED,
                    "inputs_changed",
                    "Inputs changed. Start a new request.",
                )
                refresh_parent(job.parent_id)
                continue
            step = job.steps.exclude(state=JobState.SUCCEEDED).first()
            if not step:
                set_state(
                    job,
                    JobState.NEEDS_ATTENTION,
                    "missing_steps",
                    "This job has no executable steps.",
                )
                refresh_parent(job.parent_id)
                continue
            step.state, step.claim_token = JobState.RUNNING, uuid.uuid4()
            step.heartbeat_at, step.lease_expires_at = (
                now,
                now + timedelta(seconds=settings.GRAIDER_AI_LEASE_SECONDS),
            )
            step.save(update_fields=("state", "claim_token", "heartbeat_at", "lease_expires_at"))
            job.state, job.retry_after = JobState.RUNNING, None
            job.save(update_fields=("state", "retry_after", "updated_at"))
            refresh_parent(job.parent_id)
            return step.id, step.claim_token
    return None


def heartbeat(claims):
    now = timezone.now()
    with transaction.atomic():
        lock_coordinator()
        for step_id, token in claims:
            # An expired claim cannot resurrect itself, even if no successor exists yet.
            AIJobStep.objects.filter(
                pk=step_id, claim_token=token, state=JobState.RUNNING, lease_expires_at__gt=now
            ).update(
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=settings.GRAIDER_AI_LEASE_SECONDS),
            )


def run_claim(step_id, token, *, client=None):
    try:
        step = assert_claim(step_id, token)
        metric("step_start", job_id=str(step.job_id), step_id=step.pk, key=step.key)
        output = execute_recipe(step, RecipeService(step, token, client=client))
        with transaction.atomic():
            lock_coordinator()
            step = assert_claim(step_id, token)
            step.checkpoint, step.state = output, JobState.SUCCEEDED
            step.finished_at, step.claim_token, step.lease_expires_at = timezone.now(), None, None
            step.save(
                update_fields=(
                    "checkpoint",
                    "state",
                    "finished_at",
                    "claim_token",
                    "lease_expires_at",
                )
            )
            job = step.job
            job.completed_steps = job.steps.filter(state=JobState.SUCCEEDED).count()
            job.state = JobState.QUEUED
            job.save(update_fields=("completed_steps", "state", "updated_at"))
            refresh_parent(job.parent_id)
    except ClaimLost:
        # Cancellation is acknowledged promptly, rather than waiting for lease expiry.
        with transaction.atomic():
            lock_coordinator()
            step = (
                AIJobStep.objects.select_related("job")
                .filter(pk=step_id, claim_token=token)
                .first()
            )
            if step and step.job.cancel_requested:
                set_state(step.job, JobState.CANCELLED)
                refresh_parent(step.job.parent_id)
    except (
        LLMGenerationError,
        LLMConfigurationError,
        LLMQuotaExceeded,
        SchemaValidationError,
    ) as exc:
        with transaction.atomic():
            lock_coordinator()
            try:
                step = assert_claim(step_id, token)
            except ClaimLost:
                step = (
                    AIJobStep.objects.select_related("job")
                    .filter(pk=step_id, claim_token=token)
                    .first()
                )
                if step and step.job.cancel_requested:
                    set_state(step.job, JobState.CANCELLED)
                    refresh_parent(step.job.parent_id)
                return
            job = step.job
            uncertain = step.attempts.filter(
                claim_token=token, state=AIJobAttempt.State.UNCERTAIN
            ).exists()
            if uncertain:
                set_state(
                    job,
                    JobState.NEEDS_ATTENTION,
                    "uncertain_charge",
                    "A request may have been charged. Confirm possible additional charges to retry.",
                )
            elif isinstance(exc, (LLMQuotaExceeded, LLMSpendLimitError)):
                set_state(
                    job,
                    JobState.PAUSED_QUOTA,
                    "quota",
                    "AI allowance or spending limit reached. Resume when allowance is available.",
                )
            elif (
                isinstance(exc, LLMTransientError)
                and step.attempts.count() <= settings.GRAIDER_AI_SAFE_RETRIES
            ):
                set_state(
                    job,
                    JobState.RETRY_WAIT,
                    "provider_busy",
                    "Provider is busy; a safe retry is scheduled.",
                )
                job.retry_after = timezone.now() + timedelta(
                    seconds=settings.GRAIDER_AI_RETRY_SECONDS * 2 ** (step.attempts.count() - 1)
                )
                job.save(update_fields=("retry_after",))
            else:
                # Invalid domain output must not be replayed forever on explicit retry.
                step.attempts.filter(claim_token=token, state=AIJobAttempt.State.SUCCEEDED).update(
                    state=AIJobAttempt.State.FAILED
                )
                set_state(job, JobState.FAILED, "ai_failed", public_llm_error(exc))
            refresh_parent(job.parent_id)

    except (ValueError, KeyError, TypeError, AttributeError):
        # Logic/schema mismatches are attention-required; database failures propagate
        # so lease recovery, rather than a blind provider retry, handles them.
        with transaction.atomic():
            lock_coordinator()
            try:
                step = assert_claim(step_id, token)
            except ClaimLost:
                return
            set_state(
                step.job,
                JobState.NEEDS_ATTENTION,
                "execution_review",
                "Saved work needs review before it can continue.",
            )
            refresh_parent(step.job.parent_id)
