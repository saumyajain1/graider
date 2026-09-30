from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assignments.models import Assignment
from apps.assignments.services import extract_text_from_uploaded_file, is_supported_text_upload
from apps.uploads import (
    check_file_size,
    check_submission_capacity,
    check_text_length,
    original_name,
    private_file_response,
    stored_upload,
)

from .models import (
    GradingResult,
    ReferenceAnswer,
    RubricCriterion,
    StudentSubmission,
    SubmissionImport,
)
from .serializers import (
    GradingResultReviewSerializer,
    GradingResultSerializer,
    ReferenceAnswerCreateSerializer,
    ReferenceAnswerItemSerializer,
    ReferenceAnswerWriteSerializer,
    RubricCriterionCreateSerializer,
    RubricCriterionResponseSerializer,
    RubricCriterionWriteSerializer,
    RubricQuestionSerializer,
    StudentSubmissionSerializer,
    SubmissionCreateSerializer,
    SubmissionGradingSerializer,
    SubmissionImportSerializer,
    build_reference_answer_item,
    build_rubric_question_item,
)
from .services import (
    LLMConfigurationError,
    LLMGenerationError,
    generate_reference_answer,
    generate_rubric_criteria,
)
from .services.openai_client import LLMSpendLimitError, public_llm_error
from .services.submission_io import (
    CsvImportError,
    build_assignment_results_csv_response,
    parse_submissions_csv,
)
from .services.submission_workflow import (
    SubmissionGradingInProgressError,
    SubmissionNotReadyError,
    finalize_submission,
    question_queryset_for_assignment,
    run_grading_pipeline,
    save_grading_review,
)
from .services.usage import LLMQuotaExceeded


def normalize_rubric_order(question_part):
    for index, item in enumerate(question_part.rubric_criteria.all()):
        if item.display_order != index:
            item.display_order = index
            item.save(update_fields=("display_order", "updated_at"))


def serialize_submission_grading(submission):
    return {
        "submission": submission,
        "answer_parts": submission.answer_parts.all(),
        "grading_results": submission.grading_results.all(),
    }


class TeacherScopedArtifactView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def get_assignment(self, assignment_id):
        return get_object_or_404(
            Assignment.objects.select_related("teacher"),
            id=assignment_id,
            teacher=self.request.user,
        )

    def get_submission(self, submission_id):
        return get_object_or_404(
            StudentSubmission.objects.select_related("assignment", "assignment__teacher"),
            id=submission_id,
            assignment__teacher=self.request.user,
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

    def get_grading_result(self, grading_result_id):
        return get_object_or_404(
            GradingResult.objects.select_related(
                "submission",
                "submission__assignment",
                "submission__assignment__teacher",
                "question_part",
            ),
            id=grading_result_id,
            submission__assignment__teacher=self.request.user,
        )

    def handle_llm_error(self, exc):
        if isinstance(exc, (LLMConfigurationError, LLMSpendLimitError)):
            return Response(
                {"detail": public_llm_error(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return Response({"detail": public_llm_error(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    def handle_quota_error(self, exc):
        return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)


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
        question_part = assignment.question_parts.get(
            id=serializer.validated_data["question_part_id"]
        )
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
        except LLMQuotaExceeded as exc:
            return self.handle_quota_error(exc)
        except (LLMConfigurationError, LLMGenerationError) as exc:
            return self.handle_llm_error(exc)

        return Response(ReferenceAnswerItemSerializer(items, many=True).data)


class ReferenceAnswerDetailView(TeacherScopedArtifactView):
    def patch(self, request, reference_answer_id):
        reference_answer = self.get_reference_answer(reference_answer_id)
        serializer = ReferenceAnswerWriteSerializer(
            reference_answer, data=request.data, partial=True
        )
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
        question_part = assignment.question_parts.get(
            id=serializer.validated_data["question_part_id"]
        )
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

        questions = list(questions)
        if not questions:
            return Response(
                {"detail": "No target question parts were found for rubric generation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        references = []
        for question_part in questions:
            try:
                references.append((question_part, question_part.reference_answer))
            except ReferenceAnswer.DoesNotExist:
                return Response(
                    {
                        "detail": "Generate or create a reference answer before generating rubric criteria."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        prepared = []
        try:
            for question_part, reference_answer in references:
                parsed = generate_rubric_criteria(question_part, reference_answer.answer_text)
                prepared.append((question_part, parsed))
        except LLMQuotaExceeded as exc:
            return self.handle_quota_error(exc)
        except (LLMConfigurationError, LLMGenerationError) as exc:
            return self.handle_llm_error(exc)

        generated_questions = []
        with transaction.atomic():
            for question_part, parsed in prepared:
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


class SubmissionListCreateView(TeacherScopedArtifactView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = StudentSubmissionSerializer(assignment.submissions.all(), many=True)
        return Response(serializer.data)

    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        serializer = SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_file = serializer.validated_data.get("response_file")
        raw_response_text = serializer.validated_data.get("raw_response_text", "")
        ingestion_notes = ""

        if uploaded_file is not None:
            if not is_supported_text_upload(uploaded_file):
                return Response({"detail": "Only .txt and .pdf files are supported."}, status=400)
            check_file_size(uploaded_file, settings.GRAIDER_MAX_UPLOAD_BYTES)
            extracted_text, ingestion_notes = extract_text_from_uploaded_file(
                uploaded_file, max_chars=settings.GRAIDER_MAX_RESPONSE_CHARS
            )
            if not raw_response_text.strip():
                raw_response_text = extracted_text
            if not raw_response_text.strip():
                detail = ingestion_notes or "No extractable text was found in the uploaded file."
                return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        check_text_length(raw_response_text, settings.GRAIDER_MAX_RESPONSE_CHARS, "Response text")
        submission = StudentSubmission(
            assignment=assignment,
            student_name=serializer.validated_data["student_name"],
            student_identifier=serializer.validated_data.get("student_identifier", ""),
            raw_response_text=raw_response_text,
            response_original_filename=original_name(uploaded_file) if uploaded_file else "",
            ingestion_notes=ingestion_notes,
            upload_source=(
                StudentSubmission.UploadSource.FILE
                if uploaded_file is not None
                else StudentSubmission.UploadSource.MANUAL
            ),
        )
        if uploaded_file is not None:
            with stored_upload(submission.response_file, uploaded_file):
                with transaction.atomic():
                    Assignment.objects.select_for_update().get(pk=assignment.pk)
                    check_submission_capacity(assignment)
                    submission.save()
        else:
            with transaction.atomic():
                Assignment.objects.select_for_update().get(pk=assignment.pk)
                check_submission_capacity(assignment)
                submission.save()
        return Response(
            StudentSubmissionSerializer(submission).data,
            status=status.HTTP_201_CREATED,
        )


class SubmissionImportCsvView(TeacherScopedArtifactView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"detail": "Upload a CSV file in the file field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            submissions = parse_submissions_csv(assignment, uploaded_file)
        except CsvImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        csv_import = SubmissionImport(
            assignment=assignment,
            original_filename=original_name(uploaded_file),
            row_count=len(submissions),
        )
        with stored_upload(csv_import.source_file, uploaded_file):
            with transaction.atomic():
                Assignment.objects.select_for_update().get(pk=assignment.pk)
                check_submission_capacity(assignment, len(submissions))
                csv_import.save()
                created = StudentSubmission.objects.bulk_create(submissions)

        return Response(
            StudentSubmissionSerializer(created, many=True).data, status=status.HTTP_201_CREATED
        )


class SubmissionImportListView(TeacherScopedArtifactView):
    def get(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        return Response(SubmissionImportSerializer(assignment.csv_imports.all(), many=True).data)


class SubmissionImportFileView(TeacherScopedArtifactView):
    def get(self, request, assignment_id, import_id):
        assignment = self.get_assignment(assignment_id)
        csv_import = get_object_or_404(assignment.csv_imports, pk=import_id)
        return private_file_response(csv_import.source_file, csv_import.original_filename)


class SubmissionDetailView(TeacherScopedArtifactView):
    def get(self, request, submission_id):
        submission = self.get_submission(submission_id)
        return Response(StudentSubmissionSerializer(submission).data)


class SubmissionResponseFileView(TeacherScopedArtifactView):
    def get(self, request, submission_id):
        submission = self.get_submission(submission_id)
        filename = (
            submission.response_original_filename
            or submission.response_file.name.rsplit("/", 1)[-1]
        )
        return private_file_response(submission.response_file, filename)


class SubmissionGradeView(TeacherScopedArtifactView):
    def post(self, request, submission_id):
        submission = self.get_submission(submission_id)
        try:
            submission = run_grading_pipeline(submission)
        except SubmissionNotReadyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except SubmissionGradingInProgressError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except LLMQuotaExceeded as exc:
            return self.handle_quota_error(exc)
        except (LLMConfigurationError, LLMGenerationError) as exc:
            return self.handle_llm_error(exc)

        return Response(StudentSubmissionSerializer(submission).data)


class AssignmentGradeAllView(TeacherScopedArtifactView):
    def post(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        submissions = list(assignment.submissions.all())
        if not submissions:
            return Response(
                {"detail": "No submissions are available to grade."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(submissions) > settings.GRAIDER_MAX_GRADE_ALL_SUBMISSIONS:
            return Response(
                {
                    "detail": f"Grade at most {settings.GRAIDER_MAX_GRADE_ALL_SUBMISSIONS} submissions at once."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (
            question_queryset_for_assignment(assignment).count()
            > settings.GRAIDER_MAX_GRADE_ALL_QUESTIONS
        ):
            return Response(
                {
                    "detail": f"Grade-all supports at most {settings.GRAIDER_MAX_GRADE_ALL_QUESTIONS} questions."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        graded = 0
        failed = 0
        for submission in submissions:
            try:
                run_grading_pipeline(submission)
                graded += 1
            except SubmissionNotReadyError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except SubmissionGradingInProgressError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
            except LLMQuotaExceeded as exc:
                return self.handle_quota_error(exc)
            except (LLMConfigurationError, LLMSpendLimitError) as exc:
                return self.handle_llm_error(exc)
            except LLMGenerationError:
                failed += 1

        return Response(
            {
                "graded_count": graded,
                "failed_count": failed,
                "submissions": StudentSubmissionSerializer(
                    assignment.submissions.all(), many=True
                ).data,
            }
        )


class SubmissionGradingView(TeacherScopedArtifactView):
    def get(self, request, submission_id):
        submission = self.get_submission(submission_id)
        payload = serialize_submission_grading(submission)
        return Response(SubmissionGradingSerializer(payload).data)


class GradingResultDetailView(TeacherScopedArtifactView):
    def patch(self, request, grading_result_id):
        grading_result = self.get_grading_result(grading_result_id)
        serializer = GradingResultReviewSerializer(
            data=request.data,
            context={"grading_result": grading_result},
        )
        serializer.is_valid(raise_exception=True)
        grading_result = save_grading_review(grading_result, **serializer.normalized_data())

        return Response(GradingResultSerializer(grading_result).data)


class SubmissionFinalizeView(TeacherScopedArtifactView):
    def post(self, request, submission_id):
        submission = self.get_submission(submission_id)
        submission = finalize_submission(submission)
        return Response(StudentSubmissionSerializer(submission).data)


class AssignmentExportCsvView(TeacherScopedArtifactView):
    def get(self, request, assignment_id):
        assignment = self.get_assignment(assignment_id)
        return build_assignment_results_csv_response(assignment)
