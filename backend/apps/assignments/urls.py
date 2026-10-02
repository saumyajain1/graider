from django.urls import path

from .views import (
    AssignmentDetailView,
    AssignmentListCreateView,
    AssignmentSourceFileView,
    QuestionDetailView,
    QuestionGenerateView,
    QuestionListCreateView,
    QuestionReorderView,
)

urlpatterns = [
    path("", AssignmentListCreateView.as_view(), name="assignment-list"),
    path("<int:assignment_id>", AssignmentDetailView.as_view(), name="assignment-detail"),
    path(
        "<int:assignment_id>/source-file",
        AssignmentSourceFileView.as_view(),
        name="assignment-source-file",
    ),
    path("<int:assignment_id>/questions", QuestionListCreateView.as_view(), name="question-list"),
    path(
        "<int:assignment_id>/questions/generate",
        QuestionGenerateView.as_view(),
        name="question-generate",
    ),
    path(
        "<int:assignment_id>/questions/reorder",
        QuestionReorderView.as_view(),
        name="question-reorder",
    ),
    path("questions/<int:question_id>", QuestionDetailView.as_view(), name="question-detail"),
]
