from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_view
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_jobs.admission import background_response
from apps.ai_jobs.models import AIJob
from apps.ai_jobs.serializers import JobDetailSerializer
from apps.uploads import delete_upload_after_commit, private_file_response
from config.schema import api_schema

from .models import Assignment, QuestionPart
from .serializers import (
    AssignmentSerializer,
    QuestionGenerateSerializer,
    QuestionPartSerializer,
    QuestionReorderSerializer,
    SourcePreviewResponseSerializer,
    SourcePreviewSerializer,
)


def normalize_question_order(assignment):
    for index, question in enumerate(assignment.question_parts.order_by("display_order", "id")):
        if question.display_order != index:
            question.display_order = index
            question.save(update_fields=("display_order", "updated_at"))


class TeacherScopedView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_assignment(self, assignment_id):
        return get_object_or_404(
            Assignment.objects.select_related("teacher"),
            id=assignment_id,
            teacher=self.request.user,
        )

    def get_question(self, question_id):
        return get_object_or_404(
            QuestionPart.objects.select_related("assignment", "assignment__teacher"),
            id=question_id,
            assignment__teacher=self.request.user,
        )


@extend_schema_view(
    get=api_schema(response=AssignmentSerializer(many=True)),
    post=api_schema(request=AssignmentSerializer, response=AssignmentSerializer, code=201),
)
class AssignmentListCreateView(TeacherScopedView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        assignments = Assignment.objects.filter(teacher=request.user)
        serializer = AssignmentSerializer(assignments, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        serializer = AssignmentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save()
        return Response(
            AssignmentSerializer(assignment, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    get=api_schema(response=AssignmentSerializer),
    patch=api_schema(request=AssignmentSerializer, response=AssignmentSerializer),
    delete=api_schema(code=204),
)
class AssignmentDetailView(TeacherScopedView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = AssignmentSerializer(assignment, context={"request": request})
        return Response(serializer.data)

    def patch(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = AssignmentSerializer(
            assignment,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save()
        return Response(AssignmentSerializer(assignment, context={"request": request}).data)

    def delete(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        with transaction.atomic():
            delete_upload_after_commit(assignment.source_file)
            for submission in assignment.submissions.all():
                delete_upload_after_commit(submission.response_file)
            for csv_import in assignment.csv_imports.all():
                delete_upload_after_commit(csv_import.source_file)
            assignment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=api_schema(
        response={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            (200, "text/plain"): OpenApiTypes.BINARY,
        }
    ),
)
class AssignmentSourceFileView(TeacherScopedView):
    def get(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        filename = (
            assignment.source_original_filename or assignment.source_file.name.rsplit("/", 1)[-1]
        )
        return private_file_response(assignment.source_file, filename)


@extend_schema_view(
    get=api_schema(response=QuestionPartSerializer(many=True)),
    post=api_schema(request=QuestionPartSerializer, response=QuestionPartSerializer, code=201),
)
class QuestionListCreateView(TeacherScopedView):
    parser_classes = [JSONParser]

    def get(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = QuestionPartSerializer(assignment.question_parts.all(), many=True)
        return Response(serializer.data)

    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = QuestionPartSerializer(
            data=request.data,
            context={"assignment": assignment},
        )
        serializer.is_valid(raise_exception=True)
        question = serializer.save()
        return Response(QuestionPartSerializer(question).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    post=api_schema(
        request=QuestionGenerateSerializer,
        response=JobDetailSerializer,
        code=202,
        ai=True,
        errors={409: OpenApiTypes.OBJECT},
    ),
)
class QuestionGenerateView(TeacherScopedView):
    parser_classes = [JSONParser]

    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = QuestionGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return background_response(
            request, AIJob.Operation.QUESTIONS, assignment, options=serializer.validated_data
        )


@extend_schema_view(
    patch=api_schema(request=QuestionPartSerializer, response=QuestionPartSerializer),
    delete=api_schema(code=204),
)
class QuestionDetailView(TeacherScopedView):
    parser_classes = [JSONParser]

    def patch(self, request, question_id):
        question = self.get_question(question_id)
        serializer = QuestionPartSerializer(question, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        question = serializer.save()
        return Response(QuestionPartSerializer(question).data)

    def delete(self, request, question_id):
        question = self.get_question(question_id)
        assignment = question.assignment
        question.delete()
        normalize_question_order(assignment)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    post=api_schema(request=QuestionReorderSerializer, response=QuestionPartSerializer(many=True)),
)
class QuestionReorderView(TeacherScopedView):
    parser_classes = [JSONParser]

    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = QuestionReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question_ids = serializer.validated_data["question_ids"]

        existing_ids = list(assignment.question_parts.values_list("id", flat=True))
        if sorted(question_ids) != sorted(existing_ids):
            return Response(
                {
                    "detail": "question_ids must contain each question for the assignment exactly once."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        questions_by_id = {question.id: question for question in assignment.question_parts.all()}

        with transaction.atomic():
            for index, question_id in enumerate(question_ids):
                question = questions_by_id[question_id]
                question.display_order = index
                question.save(update_fields=("display_order", "updated_at"))

        serializer = QuestionPartSerializer(assignment.question_parts.all(), many=True)
        return Response(serializer.data)


@extend_schema_view(
    post=api_schema(request=SourcePreviewSerializer, response=SourcePreviewResponseSerializer)
)
class AssignmentSourcePreviewView(TeacherScopedView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, assignment_id):
        from .services import extract_text_from_uploaded_file

        self.get_assignment(assignment_id)
        serializer = SourcePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text, notes = extract_text_from_uploaded_file(serializer.validated_data["source_file"])
        if not text.strip():
            return Response(
                {"detail": notes or "No extractable text was found in this file."}, status=400
            )
        return Response({"extracted_text": text, "ingestion_notes": notes})
