"""Durable admission/control only. Execution and provider calls belong to the worker."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.assignments.models import Assignment
from apps.grading.models import StudentSubmission

from .models import (
    ACTIVE_STATES,
    RETRYABLE_STATES,
    AIJob,
    AIJobAttempt,
    AIJobCoordinator,
    AIJobStep,
    AIJobTarget,
    JobState,
)
from .snapshots import (
    SNAPSHOT_VERSION,
    capture_inputs,
    execution_plan,
    fingerprint,
    inputs_unchanged,
)


class JobConflict(APIException):
    status_code = 409
    default_detail = "Another AI job already covers this target."


class QueueFull(APIException):
    status_code = 429
    default_detail = "The AI job queue is full. Wait for existing jobs to finish."


class WorkerUnavailable(APIException):
    status_code = 503
    default_detail = "The background AI worker is unavailable. Please try again shortly."


def lock_coordinator():
    # Created by the migration, not lazily inserted during competing admissions.
    AIJobCoordinator.objects.select_for_update().get(pk=1)


def check_capacity(owner, additional):
    executable = AIJob.objects.filter(state__in=ACTIVE_STATES).exclude(
        operation=AIJob.Operation.BATCH
    )
    if (
        executable.count() + additional > settings.GRAIDER_AI_GLOBAL_QUEUE_LIMIT
        or executable.filter(owner=owner).count() + additional
        > settings.GRAIDER_AI_USER_QUEUE_LIMIT
    ):
        raise QueueFull()


def validate_targets(keys, *, exclude_jobs=()):
    if (
        AIJobTarget.objects.filter(key__in=keys, active=True)
        .exclude(job_id__in=exclude_jobs)
        .exists()
    ):
        raise JobConflict()


def create_job(
    owner, assignment, operation, snapshot, *, submission=None, parent=None, key=None, intent=""
):
    steps, targets = execution_plan(snapshot)
    job = AIJob.objects.create(
        owner=owner,
        assignment=assignment,
        submission=submission,
        parent=parent,
        operation=operation,
        priority=20 if operation in (AIJob.Operation.GRADE, AIJob.Operation.BATCH) else 10,
        request_key=key,
        request_fingerprint=intent,
        input_snapshot=snapshot,
        input_fingerprint=fingerprint(snapshot),
        total_steps=len(steps),
    )
    AIJobStep.objects.bulk_create(
        [AIJobStep(job=job, key=step, position=index) for index, step in enumerate(steps)]
    )
    AIJobTarget.objects.bulk_create([AIJobTarget(job=job, key=target) for target in targets])
    return job


def enqueue_job(
    *, owner, operation, assignment_id, submission_id=None, options=None, request_key=None
):
    """Return (job, created). An entire batch is admitted or nothing is written.

    Called by AI endpoints only after worker readiness is established. Admission neither contacts AI nor consumes a token reservation.
    """
    if operation not in AIJob.Operation.values:
        raise ValidationError("Unknown AI operation.")
    options = dict(options or {})
    allowed = (
        {"question_part_id", "replace_existing"}
        if operation in (AIJob.Operation.REFERENCES, AIJob.Operation.RUBRIC)
        else {"replace_existing"}
        if operation == AIJob.Operation.QUESTIONS
        else {"regrade"}
        if operation in (AIJob.Operation.GRADE, AIJob.Operation.BATCH)
        else set()
    )
    if set(options) - allowed:
        raise ValidationError("Unsupported options for this AI operation.")
    if any(
        type(value) is not bool for name, value in options.items() if name != "question_part_id"
    ):
        raise ValidationError("Replacement and regrading options must be booleans.")
    if options.get("question_part_id") is not None and (
        type(options["question_part_id"]) is not int or options["question_part_id"] <= 0
    ):
        raise ValidationError("Question ID must be a positive integer.")
    if request_key is not None and (
        not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 128
    ):
        raise ValidationError("Idempotency key must contain between 1 and 128 characters.")
    if (operation == AIJob.Operation.GRADE) != (submission_id is not None):
        raise ValidationError("A submission ID is required only for single-submission grading.")
    # Normalize explicit defaults so semantically identical requests replay the same job.
    if operation in (AIJob.Operation.REFERENCES, AIJob.Operation.RUBRIC):
        options = {
            "replace_existing": options.get("replace_existing", False),
            "question_part_id": options.get("question_part_id"),
        }
    elif operation == AIJob.Operation.QUESTIONS:
        options = {"replace_existing": options.get("replace_existing", False)}
    elif operation in (AIJob.Operation.GRADE, AIJob.Operation.BATCH):
        options = {"regrade": options.get("regrade", False)}
    intent = fingerprint(
        {
            "operation": operation,
            "assignment_id": assignment_id,
            "submission_id": submission_id,
            "options": options,
        }
    )
    with transaction.atomic():
        lock_coordinator()
        from .runtime import notify_worker

        transaction.on_commit(notify_worker)
        if request_key:
            previous = AIJob.objects.filter(owner=owner, request_key=request_key).first()
            if previous:
                if previous.request_fingerprint != intent:
                    raise JobConflict("This idempotency key was used for a different request.")
                return previous, False
        assignment = Assignment.objects.filter(pk=assignment_id, teacher=owner).first()
        if assignment is None:
            raise NotFound()
        submissions = []
        if operation in (AIJob.Operation.GRADE, AIJob.Operation.BATCH):
            queryset = StudentSubmission.objects.filter(assignment=assignment).order_by("id")
            if operation == AIJob.Operation.GRADE:
                submission = queryset.filter(pk=submission_id).first()
                if submission is None:
                    raise NotFound()
                submissions = [submission]
            else:
                if not options["regrade"]:
                    queryset = queryset.filter(grading_status__in=("pending", "failed"))
                # Inspect only limit+1 rows before rejecting an oversized batch.
                submissions = list(queryset[: settings.GRAIDER_AI_MAX_BATCH_SUBMISSIONS + 1])
                if len(submissions) > settings.GRAIDER_AI_MAX_BATCH_SUBMISSIONS:
                    raise ValidationError("Too many eligible submissions for one grading batch.")
                if not submissions:
                    raise ValidationError("There are no eligible submissions to grade.")
            if (
                assignment.question_parts.filter(part_type="question").count()
                > settings.GRAIDER_AI_MAX_GRADING_QUESTIONS
            ):
                raise ValidationError("Too many questions for background grading.")
            for submission in submissions:
                if submission.grading_status == "grading":
                    raise JobConflict("This submission is already being graded.")
                if (
                    submission.grading_status not in ("pending", "failed")
                    and not options["regrade"]
                ):
                    raise JobConflict("Choose explicit regrading to replace existing grades.")
                if submission.finalized_at is not None or submission.grading_status == "finalized":
                    raise JobConflict("Reopen this finalized submission before regrading.")
        configuration = None
        recipes = []
        for submission in submissions or [None]:
            child_operation = AIJob.Operation.GRADE if submissions else operation
            recipe = capture_inputs(assignment, child_operation, options, submission, configuration)
            configuration = recipe["configuration"]
            _, targets = execution_plan(recipe)
            recipes.append((submission, recipe, targets))
        check_capacity(owner, len(recipes))
        validate_targets([key for _, _, keys in recipes for key in keys])
        if operation == AIJob.Operation.BATCH:
            batch_snapshot = capture_inputs(
                assignment, operation, options, configuration=configuration
            )
            batch_snapshot["submission_ids"] = [submission.id for submission in submissions]
            parent = create_job(
                owner, assignment, operation, batch_snapshot, key=request_key, intent=intent
            )
            children = [
                create_job(
                    owner,
                    assignment,
                    AIJob.Operation.GRADE,
                    recipe,
                    submission=submission,
                    parent=parent,
                )
                for submission, recipe, _ in recipes
            ]
            parent.total_steps = sum(child.total_steps for child in children)
            parent.save(update_fields=("total_steps", "updated_at"))
            return parent, True
        submission, recipe, _ = recipes[0]
        return create_job(
            owner,
            assignment,
            operation,
            recipe,
            submission=submission,
            key=request_key,
            intent=intent,
        ), True


def owned_job(owner, job_id):
    job = AIJob.objects.filter(owner=owner, pk=job_id).first()
    if job is None:
        raise NotFound()
    return job


def cancel_job(*, owner, job_id):
    with transaction.atomic():
        lock_coordinator()
        from .runtime import notify_worker

        transaction.on_commit(notify_worker)
        job = owned_job(owner, job_id)
        if job.state == JobState.CANCELLED:
            return job
        if job.state not in ACTIVE_STATES:
            raise JobConflict("This job has finished; its published results are preserved.")
        work = list(job.children.all()) if job.operation == AIJob.Operation.BATCH else [job]
        now = timezone.now()
        for child in work:
            if child.state not in ACTIVE_STATES:
                continue
            child.cancel_requested = True
            # Hold target claims until the worker acknowledges an in-flight request.
            if child.state != JobState.RUNNING:
                child.state = JobState.CANCELLED
                child.finished_at = now
                child.targets.update(active=False)
                child.steps.exclude(state=JobState.SUCCEEDED).update(state=JobState.CANCELLED)
            child.save(update_fields=("cancel_requested", "state", "finished_at", "updated_at"))
        if job.operation == AIJob.Operation.BATCH:
            job.cancel_requested = True
            if not job.children.filter(state__in=ACTIVE_STATES).exists():
                job.state = JobState.CANCELLED
                job.finished_at = now
            job.save(update_fields=("cancel_requested", "state", "finished_at", "updated_at"))
        return job


def retry_job(*, owner, job_id, confirm_possible_charge=False):
    """Explicit resume retains checkpoints, attempts, and all previous usage records."""
    stale = []
    with transaction.atomic():
        lock_coordinator()
        from .runtime import notify_worker

        transaction.on_commit(notify_worker)
        job = owned_job(owner, job_id)
        if job.state not in RETRYABLE_STATES or job.cancel_requested:
            raise JobConflict("Only failed, quota-paused or attention-required jobs can resume.")
        work = (
            list(job.children.filter(state__in=RETRYABLE_STATES))
            if job.operation == AIJob.Operation.BATCH
            else [job]
        )
        if not work:
            raise JobConflict("There are no unfinished child jobs to resume.")
        if any(child.version != SNAPSHOT_VERSION for child in [job, *work]):
            raise JobConflict("This job version is unsupported. Start a new request.")
        if (
            AIJobAttempt.objects.filter(
                step__job__in=work,
                state__in=(AIJobAttempt.State.DISPATCHED, AIJobAttempt.State.UNCERTAIN),
            )
            .exclude(step__state=JobState.SUCCEEDED)
            .exists()
            and not confirm_possible_charge
        ):
            raise JobConflict(
                "A previous request may have been charged. Confirm possible additional charges to retry."
            )
        for child in work:
            snapshot = child.input_snapshot
            if child.assignment_id is None or (
                child.operation == AIJob.Operation.GRADE and child.submission_id is None
            ):
                stale.append(child)
                continue
            try:
                current = capture_inputs(
                    child.assignment,
                    child.operation,
                    snapshot["options"],
                    child.submission,
                    snapshot["configuration"],
                )
                if fingerprint(snapshot) != child.input_fingerprint or not inputs_unchanged(
                    snapshot, current
                ):
                    stale.append(child)
            except ValidationError:
                stale.append(child)
        if stale:
            for child in stale:
                child.state = JobState.SUPERSEDED
                child.finished_at = timezone.now()
                child.targets.update(active=False)
                child.save(update_fields=("state", "finished_at", "updated_at"))
            if job.operation == AIJob.Operation.BATCH:
                # One stale student must not strand other paused/failed students.
                remaining = (
                    job.children.exclude(pk__in=[child.id for child in stale])
                    .filter(state__in=(*ACTIVE_STATES, *RETRYABLE_STATES))
                    .exists()
                )
                job.state = JobState.NEEDS_ATTENTION if remaining else JobState.SUPERSEDED
                job.finished_at = None if remaining else timezone.now()
                job.save(update_fields=("state", "finished_at", "updated_at"))
        else:
            check_capacity(owner, sum(child.state not in ACTIVE_STATES for child in work))
            keys = list(AIJobTarget.objects.filter(job__in=work).values_list("key", flat=True))
            validate_targets(keys, exclude_jobs=[child.id for child in work])
            for child in work:
                child.targets.update(active=True)
                child.steps.exclude(state=JobState.SUCCEEDED).update(
                    state=JobState.QUEUED,
                    claim_token=None,
                    lease_expires_at=None,
                    heartbeat_at=None,
                    finished_at=None,
                )
                child.state = JobState.QUEUED
                child.finished_at = None
                child.retry_after = None
                child.error_code = ""
                child.error_message = ""
                child.save(
                    update_fields=(
                        "state",
                        "finished_at",
                        "retry_after",
                        "error_code",
                        "error_message",
                        "updated_at",
                    )
                )
            if job.operation == AIJob.Operation.BATCH:
                job.state = JobState.QUEUED
                job.finished_at = None
                job.error_code = ""
                job.error_message = ""
                job.save(
                    update_fields=(
                        "state",
                        "finished_at",
                        "error_code",
                        "error_message",
                        "updated_at",
                    )
                )
            elif job.parent_id:
                AIJob.objects.filter(pk=job.parent_id).update(
                    state=JobState.QUEUED, finished_at=None, updated_at=timezone.now()
                )
    if stale:
        raise JobConflict(
            "Job inputs changed or were deleted. Start a new request using current inputs."
        )
    return job
