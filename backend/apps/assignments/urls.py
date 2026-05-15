from django.urls import path

from .views import (
    AssignmentDetailView,
    AssignmentListCreateView,
    QuestionDetailView,
    QuestionListCreateView,
    QuestionReorderView,
)

urlpatterns = [
    path("", AssignmentListCreateView.as_view(), name="assignment-list"),
    path("<int:assignment_id>", AssignmentDetailView.as_view(), name="assignment-detail"),
    path("<int:assignment_id>/questions", QuestionListCreateView.as_view(), name="question-list"),
    path(
        "<int:assignment_id>/questions/reorder",
        QuestionReorderView.as_view(),
        name="question-reorder",
    ),
    path("questions/<int:question_id>", QuestionDetailView.as_view(), name="question-detail"),
]
