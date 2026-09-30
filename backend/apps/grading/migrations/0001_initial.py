# Consolidated initial schema for the pre-launch Graider database.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.grading.models


def create_quota_lock(apps, schema_editor):
    apps.get_model("grading", "LLMQuotaLock").objects.using(
        schema_editor.connection.alias
    ).get_or_create(id=1)


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("assignments", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReferenceAnswer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("answer_text", models.TextField()),
                ("version", models.PositiveIntegerField(default=1)),
                (
                    "source",
                    models.CharField(
                        choices=[("ai", "AI"), ("teacher", "Teacher")],
                        default="ai",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "question_part",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reference_answer",
                        to="assignments.questionpart",
                    ),
                ),
            ],
            options={
                "ordering": ("question_part__display_order", "id"),
            },
        ),
        migrations.CreateModel(
            name="RubricCriterion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField()),
                ("max_points", models.DecimalField(decimal_places=2, max_digits=6)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("created_by_ai", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "question_part",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rubric_criteria",
                        to="assignments.questionpart",
                    ),
                ),
            ],
            options={
                "ordering": ("display_order", "id"),
            },
        ),
        migrations.CreateModel(
            name="StudentSubmission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("student_name", models.CharField(max_length=255)),
                ("student_identifier", models.CharField(blank=True, max_length=255)),
                ("raw_response_text", models.TextField(blank=True)),
                (
                    "response_file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=apps.grading.models.submission_source_upload_to,
                    ),
                ),
                ("response_original_filename", models.CharField(blank=True, max_length=255)),
                ("ingestion_notes", models.TextField(blank=True)),
                (
                    "upload_source",
                    models.CharField(
                        choices=[
                            ("manual", "Manual"),
                            ("file", "File"),
                            ("csv", "CSV"),
                        ],
                        default="manual",
                        max_length=20,
                    ),
                ),
                (
                    "grading_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("grading", "Grading"),
                            ("graded", "Graded"),
                            ("reviewed", "Reviewed"),
                            ("finalized", "Finalized"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "total_score",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                    ),
                ),
                ("last_error", models.TextField(blank=True)),
                ("finalized_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submissions",
                        to="assignments.assignment",
                    ),
                ),
            ],
            options={
                "ordering": ("student_name", "id"),
            },
        ),
        migrations.CreateModel(
            name="GradingResult",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "ai_score",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=6,
                        null=True,
                    ),
                ),
                (
                    "final_score",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=6,
                        null=True,
                    ),
                ),
                ("max_score", models.DecimalField(decimal_places=2, max_digits=6)),
                ("ai_feedback", models.TextField(blank=True)),
                ("final_feedback", models.TextField(blank=True)),
                ("reasoning_summary", models.TextField(blank=True)),
                (
                    "confidence_score",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=4,
                        null=True,
                    ),
                ),
                ("needs_review", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "question_part",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grading_results",
                        to="assignments.questionpart",
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grading_results",
                        to="grading.studentsubmission",
                    ),
                ),
            ],
            options={
                "ordering": ("question_part__display_order", "id"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("submission", "question_part"),
                        name="unique_grading_result_per_submission_question",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="SubmissionAnswerPart",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("extracted_answer_text", models.TextField(blank=True)),
                (
                    "mapping_confidence",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=4,
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "question_part",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submission_answer_parts",
                        to="assignments.questionpart",
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="answer_parts",
                        to="grading.studentsubmission",
                    ),
                ),
            ],
            options={
                "ordering": ("question_part__display_order", "id"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("submission", "question_part"),
                        name="unique_answer_part_per_submission_question",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="SubmissionImport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source_file",
                    models.FileField(upload_to=apps.grading.models.csv_source_upload_to),
                ),
                ("original_filename", models.CharField(max_length=255)),
                ("row_count", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="csv_imports",
                        to="assignments.assignment",
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="LLMQuotaLock",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="LLMUsage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("operation", models.CharField(max_length=32)),
                ("model", models.CharField(max_length=100)),
                ("input_tokens", models.PositiveIntegerField(default=0)),
                ("output_tokens", models.PositiveIntegerField(default=0)),
                ("total_tokens", models.PositiveIntegerField(default=0)),
                ("reserved_tokens", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("uncertain", "Uncertain"),
                            ("unmetered", "Succeeded without usage data"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("provider_request_id", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="llm_usages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "created_at"], name="llm_usage_user_created_idx")
                ]
            },
        ),
        migrations.RunPython(
            create_quota_lock,
            migrations.RunPython.noop,
        ),
    ]
