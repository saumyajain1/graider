import csv
from io import StringIO

from django.db import transaction
from django.http import HttpResponse

from ..models import StudentSubmission
from .submission_workflow import question_queryset_for_assignment


class CsvImportError(ValueError):
    pass


def import_submissions_from_csv(assignment, uploaded_file):
    try:
        content = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError("CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(StringIO(content))
    fieldnames = reader.fieldnames or []
    if "student_name" not in fieldnames:
        raise CsvImportError("CSV must include a student_name column.")

    response_field = next(
        (candidate for candidate in ("response_text", "raw_response_text") if candidate in fieldnames),
        None,
    )
    if response_field is None:
        raise CsvImportError("CSV must include response_text or raw_response_text.")

    identifier_field = "student_identifier" if "student_identifier" in fieldnames else "student_id"
    submissions = []
    for row_number, row in enumerate(reader, start=2):
        student_name = (row.get("student_name") or "").strip()
        if not student_name:
            continue

        raw_response_text = (row.get(response_field) or "").strip()
        if not raw_response_text:
            raise CsvImportError(f"Row {row_number} is missing response text.")

        submissions.append(
            StudentSubmission(
                assignment=assignment,
                student_name=student_name,
                student_identifier=(
                    (row.get(identifier_field) or "").strip()
                    if identifier_field in fieldnames
                    else ""
                ),
                raw_response_text=raw_response_text,
                upload_source=StudentSubmission.UploadSource.CSV,
            )
        )

    if not submissions:
        raise CsvImportError("CSV did not contain any importable submission rows.")

    with transaction.atomic():
        return StudentSubmission.objects.bulk_create(submissions)


def build_assignment_results_csv_response(assignment):
    questions = list(question_queryset_for_assignment(assignment))
    submissions = assignment.submissions.prefetch_related("grading_results").all()

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="assignment-{assignment.id}-results.csv"'

    writer = csv.writer(response)
    header = [
        "student_name",
        "student_identifier",
        "grading_status",
        "total_score",
        "finalized_at",
    ]
    for question in questions:
        export_label = question.display_label
        header.extend([f"{export_label}_score", f"{export_label}_feedback"])
    writer.writerow(header)

    for submission in submissions:
        results_by_question = {
            result.question_part_id: result for result in submission.grading_results.all()
        }
        row = [
            submission.student_name,
            submission.student_identifier,
            submission.grading_status,
            submission.total_score or "",
            submission.finalized_at.isoformat() if submission.finalized_at else "",
        ]
        for question in questions:
            result = results_by_question.get(question.id)
            score = ""
            feedback = ""
            if result is not None:
                score = result.final_score if result.final_score is not None else result.ai_score or ""
                feedback = result.final_feedback or result.ai_feedback
            row.extend([score, feedback])
        writer.writerow(row)

    return response
