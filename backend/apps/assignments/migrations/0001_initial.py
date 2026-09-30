# Consolidated initial schema for the pre-launch Graider database.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.assignments.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Assignment",
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
                ("course_name", models.CharField(blank=True, max_length=255)),
                ("description", models.TextField(blank=True)),
                ("raw_assignment_text", models.TextField(blank=True)),
                (
                    "source_file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=apps.assignments.models.assignment_source_upload_to,
                    ),
                ),
                ("source_original_filename", models.CharField(blank=True, max_length=255)),
                ("ingestion_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at", "-created_at"),
            },
        ),
        migrations.CreateModel(
            name="QuestionPart",
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
                ("part_key", models.CharField(max_length=50)),
                ("source_label", models.CharField(blank=True, max_length=100)),
                ("parent_key", models.CharField(blank=True, max_length=50)),
                (
                    "part_type",
                    models.CharField(
                        choices=[("context", "Context"), ("question", "Question")],
                        default="question",
                        max_length=20,
                    ),
                ),
                ("text", models.TextField()),
                (
                    "max_marks",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True),
                ),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("created_by_ai", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="question_parts",
                        to="assignments.assignment",
                    ),
                ),
            ],
            options={
                "ordering": ("display_order", "id"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("assignment", "part_key"),
                        name="unique_question_part_key_per_assignment",
                    )
                ],
            },
        ),
    ]
