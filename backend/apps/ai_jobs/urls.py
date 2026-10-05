from django.urls import path

from .views import JobCancelView, JobDetailView, JobListView, JobRetryView

urlpatterns = [
    path("", JobListView.as_view(), name="ai-job-list"),
    path("<uuid:job_id>/", JobDetailView.as_view(), name="ai-job-detail"),
    path("<uuid:job_id>/cancel/", JobCancelView.as_view(), name="ai-job-cancel"),
    path("<uuid:job_id>/retry/", JobRetryView.as_view(), name="ai-job-retry"),
]
