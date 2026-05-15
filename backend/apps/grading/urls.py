from django.urls import path

from .views import (
    ReferenceAnswerDetailView,
    ReferenceAnswerGenerateView,
    ReferenceAnswerListCreateView,
    RubricCriterionDetailView,
    RubricGenerateView,
    RubricListCreateView,
)

urlpatterns = [
    path(
        "assignments/<int:assignment_id>/reference-answers",
        ReferenceAnswerListCreateView.as_view(),
        name="reference-answer-list",
    ),
    path(
        "assignments/<int:assignment_id>/reference-answers/generate",
        ReferenceAnswerGenerateView.as_view(),
        name="reference-answer-generate",
    ),
    path(
        "reference-answers/<int:reference_answer_id>",
        ReferenceAnswerDetailView.as_view(),
        name="reference-answer-detail",
    ),
    path(
        "assignments/<int:assignment_id>/rubric",
        RubricListCreateView.as_view(),
        name="rubric-list",
    ),
    path(
        "assignments/<int:assignment_id>/rubric/generate",
        RubricGenerateView.as_view(),
        name="rubric-generate",
    ),
    path(
        "rubric-criteria/<int:criterion_id>",
        RubricCriterionDetailView.as_view(),
        name="rubric-criterion-detail",
    ),
]
