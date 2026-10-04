"""Connect existing AI action URLs to durable admission during staged rollout."""

from django.conf import settings
from rest_framework.response import Response

from .runtime import notify_worker
from .serializers import JobDetailSerializer
from .services import WorkerUnavailable, enqueue_job


def background_response(request, operation, assignment, *, options, submission=None):
    if not settings.GRAIDER_AI_JOBS_ENABLED:
        return None
    if not notify_worker():
        raise WorkerUnavailable()
    job, _ = enqueue_job(
        owner=request.user,
        operation=operation,
        assignment_id=assignment.id,
        submission_id=submission.id if submission else None,
        options=options,
        request_key=request.headers.get("Idempotency-Key"),
    )
    return Response(JobDetailSerializer(job).data, status=202)
