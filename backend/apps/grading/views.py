from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assignments.models import Assignment, QuestionPart

from .models import ReferenceAnswer, RubricCriterion
from .serializers import (
    ReferenceAnswerCreateSerializer,
    ReferenceAnswerItemSerializer,
    ReferenceAnswerWriteSerializer,
    RubricCriterionCreateSerializer,
    RubricCriterionResponseSerializer,
    RubricCriterionWriteSerializer,
    RubricQuestionSerializer,
    build_reference_answer_item,
    build_rubric_question_item,
)
from .services import (
    LLMConfigurationError,
    LLMGenerationError,
    generate_reference_answer,
    generate_rubric_criteria,
)


def normalize_rubric_order(question_part):
    for index, item in enumerate(question_part.rubric_criteria.all()):
        if item.display_order != index:
            item.display_order = index
            item.save(update_fields=("display_order", "updated_at"))


def question_queryset_for_assignment(assignment):
    return assignment.question_parts.filter(part_type=QuestionPart.PartType.QUESTION).order_by(
        "display_order", "id"
    )


class TeacherScopedArtifactView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def get_assignment(self, assignment_id):
        return get_object_or_404(
            Assignment.objects.select_related("teacher"),
            id=assignment_id,
            teacher=self.request.user,
        )

    def get_reference_answer(self, reference_answer_id):
        return get_object_or_404(
            ReferenceAnswer.objects.select_related(
                "question_part",
                "question_part__assignment",
                "question_part__assignment__teacher",
            ),
            id=reference_answer_id,
            question_part__assignment__teacher=self.request.user,
        )

    def get_rubric_criterion(self, criterion_id):
        return get_object_or_404(
            RubricCriterion.objects.select_related(
                "question_part",
                "question_part__assignment",
                "question_part__assignment__teacher",
            ),
            id=criterion_id,
            question_part__assignment__teacher=self.request.user,
        )

    def handle_llm_error(self, exc):
        if isinstance(exc, LLMConfigurationError):
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class ReferenceAnswerListCreateView(TeacherScopedArtifactView):
    def get(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        items = [
            build_reference_answer_item(question_part)
            for question_part in question_queryset_for_assignment(assignment)
        ]
        return Response(ReferenceAnswerItemSerializer(items, many=True).data)

    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = ReferenceAnswerCreateSerializer(
            data=request.data,
            context={"assignment": assignment},
        )
        serializer.is_valid(raise_exception=True)
        question_part = assignment.question_parts.get(id=serializer.validated_data["question_part_id"])
        answer_text = serializer.validated_data["answer_text"]
        reference_answer, created = ReferenceAnswer.objects.get_or_create(
            question_part=question_part,
            defaults={
                "answer_text": answer_text,
                "source": ReferenceAnswer.Source.TEACHER,
            },
        )
        if not created:
            reference_answer.answer_text = answer_text
            reference_answer.source = ReferenceAnswer.Source.TEACHER
            reference_answer.version += 1
            reference_answer.save()

        item = build_reference_answer_item(question_part)
        return Response(ReferenceAnswerItemSerializer(item).data, status=status.HTTP_201_CREATED)


class ReferenceAnswerGenerateView(TeacherScopedArtifactView):
    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        target_question_id = request.data.get("question_part_id")
        questions = question_queryset_for_assignment(assignment)
        if target_question_id is not None:
            questions = questions.filter(id=target_question_id)

        if not questions.exists():
            return Response(
                {"detail": "No target question parts were found for reference answer generation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items = []
        try:
            for question_part in questions:
                parsed = generate_reference_answer(assignment, question_part)
                reference_answer, created = ReferenceAnswer.objects.get_or_create(
                    question_part=question_part,
                    defaults={
                        "answer_text": parsed.answer_text,
                        "source": ReferenceAnswer.Source.AI,
                    },
                )
                if not created:
                    reference_answer.answer_text = parsed.answer_text
                    reference_answer.source = ReferenceAnswer.Source.AI
                    reference_answer.version += 1
                    reference_answer.save()

                items.append(build_reference_answer_item(question_part))
        except (LLMConfigurationError, LLMGenerationError) as exc:
            return self.handle_llm_error(exc)

        return Response(ReferenceAnswerItemSerializer(items, many=True).data)


class ReferenceAnswerDetailView(TeacherScopedArtifactView):
    def patch(self, request, reference_answer_id):
        reference_answer = self.get_reference_answer(reference_answer_id)
        serializer = ReferenceAnswerWriteSerializer(reference_answer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            source=request.data.get("source", ReferenceAnswer.Source.TEACHER),
            version=reference_answer.version + 1,
        )
        item = build_reference_answer_item(reference_answer.question_part)
        return Response(ReferenceAnswerItemSerializer(item).data)


class RubricListCreateView(TeacherScopedArtifactView):
    def get(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        items = [
            build_rubric_question_item(question_part)
            for question_part in question_queryset_for_assignment(assignment)
        ]
        return Response(RubricQuestionSerializer(items, many=True).data)

    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = RubricCriterionCreateSerializer(
            data=request.data,
            context={"assignment": assignment},
        )
        serializer.is_valid(raise_exception=True)
        question_part = assignment.question_parts.get(id=serializer.validated_data["question_part_id"])
        criterion = RubricCriterion.objects.create(
            question_part=question_part,
            title=serializer.validated_data["title"],
            description=serializer.validated_data["description"],
            max_points=serializer.validated_data["max_points"],
            display_order=question_part.rubric_criteria.count(),
            created_by_ai=False,
        )
        return Response(
            RubricCriterionResponseSerializer(criterion).data,
            status=status.HTTP_201_CREATED,
        )


class RubricGenerateView(TeacherScopedArtifactView):
    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        target_question_id = request.data.get("question_part_id")
        questions = question_queryset_for_assignment(assignment).select_related("reference_answer")
        if target_question_id is not None:
            questions = questions.filter(id=target_question_id)

        if not questions.exists():
            return Response(
                {"detail": "No target question parts were found for rubric generation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        generated_questions = []
        try:
            with transaction.atomic():
                for question_part in questions:
                    try:
                        reference_answer = question_part.reference_answer
                    except ReferenceAnswer.DoesNotExist:
                        return Response(
                            {
                                "detail": (
                                    "Generate or create a reference answer before generating rubric criteria."
                                )
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    parsed = generate_rubric_criteria(question_part, reference_answer.answer_text)
                    question_part.rubric_criteria.all().delete()
                    for index, criterion in enumerate(parsed.criteria):
                        RubricCriterion.objects.create(
                            question_part=question_part,
                            title=criterion.title,
                            description=criterion.description,
                            max_points=Decimal(str(criterion.max_points)),
                            display_order=index,
                            created_by_ai=True,
                        )
                    generated_questions.append(build_rubric_question_item(question_part))
        except (LLMConfigurationError, LLMGenerationError) as exc:
            return self.handle_llm_error(exc)

        return Response(RubricQuestionSerializer(generated_questions, many=True).data)


class RubricCriterionDetailView(TeacherScopedArtifactView):
    def patch(self, request, criterion_id):
        criterion = self.get_rubric_criterion(criterion_id)
        serializer = RubricCriterionWriteSerializer(criterion, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by_ai=False)
        return Response(RubricCriterionResponseSerializer(criterion).data)

    def delete(self, request, criterion_id):
        criterion = self.get_rubric_criterion(criterion_id)
        question_part = criterion.question_part
        criterion.delete()
        normalize_rubric_order(question_part)
        return Response(status=status.HTTP_204_NO_CONTENT)
