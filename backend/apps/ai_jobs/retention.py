"""Prune old terminal job trees while preserving published data and usage accounting."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.grading.models import LLMUsage

from .models import ACTIVE_STATES, AIJob, JobState
from .services import lock_coordinator

TERMINAL_STATES = (JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.SUPERSEDED)


def eligible_roots(cutoff):
    members = AIJob.objects.filter(Q(pk=OuterRef("pk")) | Q(parent_id=OuterRef("pk")))
    protected = members.filter(
        Q(state__in=ACTIVE_STATES)
        | ~Q(state__in=TERMINAL_STATES)
        | Q(finished_at__isnull=True)
        | Q(finished_at__gte=cutoff)
        | Q(targets__active=True)
        | Q(steps__state=JobState.RUNNING)
        | Q(steps__attempts__usage__status=LLMUsage.Status.PENDING)
        | Q(children__children__isnull=False)
    )
    return (
        AIJob.objects.filter(parent__isnull=True, state__in=TERMINAL_STATES, finished_at__lt=cutoff)
        .alias(protected=Exists(protected))
        .filter(protected=False)
        .order_by("finished_at", "id")
    )


def prune_jobs(*, days=30, batch_size=100, apply=False):
    if days < 1 or batch_size < 1 or batch_size > 100:
        raise ValueError("Days must be positive and batch size must be between 1 and 100.")
    cutoff = timezone.now() - timedelta(days=days)
    roots, jobs = 0, 0
    if not apply:
        selected = eligible_roots(cutoff).values_list("pk", flat=True)
        return {
            "roots": selected.count(),
            "jobs": AIJob.objects.filter(Q(pk__in=selected) | Q(parent_id__in=selected)).count(),
        }
    while True:
        # Share the worker/admission lock: eligibility cannot change between selection and deletion.
        with transaction.atomic():
            lock_coordinator()
            selected = list(eligible_roots(cutoff).values_list("pk", flat=True)[:batch_size])
            if not selected:
                break
            count = AIJob.objects.filter(Q(pk__in=selected) | Q(parent_id__in=selected)).count()
            AIJob.objects.filter(pk__in=selected).delete()
            roots += len(selected)
            jobs += count
    return {"roots": roots, "jobs": jobs}
