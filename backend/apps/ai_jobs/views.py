from drf_spectacular.utils import OpenApiResponse
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from config.schema import APIErrorSerializer, api_schema

from .models import AIJob
from .runtime import notify_worker
from .serializers import (
    JobDetailSerializer,
    JobFilterSerializer,
    JobRetrySerializer,
    JobSummarySerializer,
)
from .services import WorkerUnavailable, cancel_job, retry_job

CONFLICT = {409: OpenApiResponse(APIErrorSerializer, description="Job state or inputs conflict.")}


class JobPagination(PageNumberPagination):
    page_size = 20


class JobListView(ListAPIView):
    serializer_class = JobSummarySerializer
    pagination_class = JobPagination

    def get_queryset(self):
        filters = JobFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        # Batch children are discoverable through their parent's detail endpoint.
        return AIJob.objects.filter(owner=self.request.user, parent__isnull=True).filter(
            **filters.validated_data
        )

    @api_schema(
        response=JobSummarySerializer(many=True),
        parameters=[JobFilterSerializer],
        tags=["AI jobs"],
        summary="List your AI jobs",
    )
    def get(self, request, *args, **kwargs):
        notify_worker()
        return super().get(request, *args, **kwargs)


class OwnedJobView(GenericAPIView):
    serializer_class = JobDetailSerializer
    parser_classes = [JSONParser]
    lookup_url_kwarg = "job_id"

    def get_queryset(self):
        return AIJob.objects.filter(owner=self.request.user).prefetch_related("children")


class JobDetailView(OwnedJobView):
    @api_schema(response=JobDetailSerializer, tags=["AI jobs"], summary="Get your job's progress")
    def get(self, request, *args, **kwargs):
        job = self.get_object()
        notify_worker()
        return Response(self.get_serializer(job).data)


class JobCancelView(OwnedJobView):
    @api_schema(
        response=JobDetailSerializer,
        errors=CONFLICT,
        tags=["AI jobs"],
        summary="Cancel future work without deleting completed results",
    )
    def post(self, request, job_id):
        job = cancel_job(owner=request.user, job_id=job_id)
        return Response(self.get_serializer(job).data)


class JobRetryView(OwnedJobView):
    @api_schema(
        response=JobDetailSerializer,
        code=202,
        request=JobRetrySerializer,
        errors={
            **CONFLICT,
            429: OpenApiResponse(APIErrorSerializer, description="AI job queue is full."),
            503: OpenApiResponse(APIErrorSerializer, description="Background worker unavailable."),
        },
        tags=["AI jobs"],
        summary="Resume unfinished work with explicit billing acknowledgement",
        description="Requires enabled job mode and a ready local worker. Completed checkpoints and previous usage reservations are retained.",
    )
    def post(self, request, job_id):
        self.get_object()  # Ownership still applies while execution is unavailable.
        serializer = JobRetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not notify_worker():
            raise WorkerUnavailable()
        job = retry_job(owner=request.user, job_id=job_id, **serializer.validated_data)
        return Response(self.get_serializer(job).data, status=202)
