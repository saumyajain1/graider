"""Explicitly benchmark real AI grading through a deployed service.

Creates synthetic fixtures through the selected database, admits jobs through
the normal authenticated/CSRF-protected HTTP API, and writes numeric evidence.
Never executes AI locally. Requires --allow-live-ai and an HTTPS base URL.
"""

import argparse
import json
import os
import secrets
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
QUESTION = "Explain why adding two pairs gives four items, and write the calculation."
REFERENCE = "Two items and two more items make four items: 2 + 2 = 4."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--allow-live-ai", action="store_true")
    parser.add_argument("--students", type=int, default=10)
    parser.add_argument("--questions", type=int, default=10)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--retain-fixtures",
        action="store_true",
        help="Keep completed synthetic records for a separate restart check; disable the audit account.",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if not args.allow_live_ai or urlsplit(base).scheme != "https":
        parser.error("Explicit --allow-live-ai and an HTTPS production URL are required.")
    if not 1 <= args.students <= 10 or not 1 <= args.questions <= 10:
        parser.error("Select between one and ten students/questions.")
    load_dotenv(args.env_file, override=True)
    if urlsplit(os.environ.get("DATABASE_URL", "")).hostname in (None, "localhost", "127.0.0.1"):
        parser.error("Select the deployed service's external database explicitly.")
    # This observer must never instantiate a local provider or notify a local worker.
    os.environ.update(
        DJANGO_SETTINGS_MODULE="config.settings",
        DJANGO_ALLOWED_HOSTS=urlsplit(base).hostname,
        OPENAI_API_KEY="",
    )
    sys.path.insert(0, str(ROOT / "backend"))
    import django

    django.setup()
    from django.contrib.sessions.models import Session
    from django.db import transaction
    from django.db.models import Count, Sum

    from apps.accounts.models import User
    from apps.ai_jobs.models import ACTIVE_STATES, AIJob, AIJobAttempt
    from apps.assignments.models import Assignment, QuestionPart
    from apps.grading.models import (
        GradingResult,
        LLMUsage,
        ReferenceAnswer,
        RubricCriterion,
        StudentSubmission,
    )

    if AIJob.objects.filter(state__in=ACTIVE_STATES).exists():
        parser.error("Wait for existing production jobs to finish before measuring.")
    baseline = {
        "users": User.objects.count(),
        "assignments": Assignment.objects.count(),
        "submissions": StudentSubmission.objects.count(),
    }
    report = {
        "run_started_at": datetime.now(UTC).isoformat(),
        "service_url": base,
        "simulated_provider": False,
        "database": "production Neon PostgreSQL",
        "students": args.students,
        "questions_per_student": args.questions,
        "criteria_per_question": 2,
        "workload": "Short arithmetic explanations with two rubric criteria per question.",
        "measurement": "grading only; fixtures, authentication and service wake-up excluded",
        "progress_poll_seconds": 5,
        "baseline_counts": baseline,
    }
    teacher = assignment = parent = None
    response_latencies = []
    http = httpx.Client(base_url=base, timeout=60, follow_redirects=True)

    def api(path, data=None, request_key=None):
        headers = {"Origin": base, "Referer": base + "/", "Accept": "application/json"}
        if data is not None:
            headers["X-CSRFToken"] = http.cookies.get("csrftoken", "")
        if request_key:
            headers["Idempotency-Key"] = request_key
        started = time.monotonic()
        response = http.request("GET" if data is None else "POST", path, json=data, headers=headers)
        duration = time.monotonic() - started
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} for {path}: {response.text[:200]}")
        return response, duration

    def save_report():
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")

    try:
        # The service is awake before fixtures and timed grading begin.
        http.get("/health/").raise_for_status()
        http.get("/api/auth/me")  # Obtain CSRF cookie, including for anonymous sessions.
        email = "grading-benchmark-" + secrets.token_hex(10) + "@example.test"
        password = secrets.token_urlsafe(32)
        response, _ = api(
            "/api/auth/register",
            {"email": email, "full_name": "Synthetic benchmark teacher", "password": password},
        )
        teacher = User.objects.get(pk=response.json()["id"], email=email)
        with transaction.atomic():
            assignment = Assignment.objects.create(
                teacher=teacher,
                title="Synthetic production grading benchmark",
                raw_assignment_text="\n".join(
                    f"Q{i}: {QUESTION}" for i in range(1, args.questions + 1)
                ),
            )
            for index in range(1, args.questions + 1):
                question = QuestionPart.objects.create(
                    assignment=assignment,
                    part_key=f"Q{index}",
                    source_label=str(index),
                    text=QUESTION,
                    max_marks=5,
                    display_order=index,
                )
                ReferenceAnswer.objects.create(
                    question_part=question, answer_text=REFERENCE, source="teacher"
                )
                for order, (title, description, maximum) in enumerate(
                    [
                        ("Method", "Explain the addition of two pairs.", 3),
                        ("Answer", "Give the correct sum, four.", 2),
                    ]
                ):
                    RubricCriterion.objects.create(
                        question_part=question,
                        title=title,
                        description=description,
                        max_points=maximum,
                        display_order=order,
                        created_by_ai=False,
                    )
            StudentSubmission.objects.bulk_create(
                [
                    StudentSubmission(
                        assignment=assignment,
                        student_name=f"Synthetic student {index + 1:02}",
                        student_identifier=f"BENCH-{index + 1:02}",
                        raw_response_text="\n".join(
                            f"Q{i}: Two items plus two more gives four items. 2+2=4."
                            for i in range(1, args.questions + 1)
                        ),
                    )
                    for index in range(args.students)
                ]
            )
        response, admission = api(
            f"/api/assignments/{assignment.pk}/grade-all", {}, secrets.token_hex(16)
        )
        assert response.status_code == 202, "The deployed API must admit a background job."
        parent = AIJob.objects.get(pk=response.json()["id"])
        report.update(
            http_status=response.status_code,
            admission_seconds=round(admission, 6),
            job_id=str(parent.pk),
            assignment_id=assignment.pk,
            job_created_at=parent.created_at.isoformat(),
            ai_configuration=parent.children.first().input_snapshot["configuration"],
        )
        save_report()
        observed_first = None
        started = last_progress = time.monotonic()
        while time.monotonic() - started < args.timeout_seconds:
            response, duration = api(f"/api/ai/jobs/{parent.pk}/")
            response_latencies.append(duration)
            job = response.json()
            completed = sum(child["state"] == "succeeded" for child in job["children"])
            if completed and observed_first is None:
                observed_first = datetime.now(UTC).isoformat()
                report["first_student_observed_at"] = observed_first
                report["student_visible_before_batch_complete"] = completed < args.students
            assert (
                not StudentSubmission.objects.filter(assignment=assignment)
                .exclude(grading_status="graded")
                .filter(grading_results__isnull=False)
                .exists()
            ), "Partial student results became visible."
            if time.monotonic() - last_progress >= 30:
                print(
                    f"Production benchmark: {completed}/{args.students} students complete; {job['completed_steps']}/{job['total_steps']} steps.",
                    flush=True,
                )
                last_progress = time.monotonic()
            if job["state"] == "succeeded":
                report["all_students_observed_at"] = datetime.now(UTC).isoformat()
                break
            if job["state"] in {
                "failed",
                "paused_quota",
                "needs_attention",
                "cancelled",
                "superseded",
            }:
                raise RuntimeError(
                    f"Benchmark stopped safely: {job['state']} ({job['error_code']})."
                )
            time.sleep(5)
        else:
            raise TimeoutError("Production grading exceeded the selected observation window.")
        attempts = list(
            AIJobAttempt.objects.filter(step__job__parent=parent)
            .order_by("created_at")
            .values("usage_id", "state", "created_at", "finished_at")
        )
        children = list(parent.children.order_by("finished_at").values("id", "finished_at"))
        beginning = min(row["created_at"] for row in attempts)
        report.update(
            request_to_finished_record_seconds=(
                children[-1]["finished_at"] - parent.created_at
            ).total_seconds(),
            dispatch_to_finished_record_seconds=(
                children[-1]["finished_at"] - beginning
            ).total_seconds(),
            timing_boundary_note="Database timestamps precede commit; use AI_METRIC events for exact execution/publication boundaries.",
            student_finished_records=[
                {"job_id": str(row["id"]), "finished_at": row["finished_at"].isoformat()}
                for row in children
            ],
            attempts=[
                {
                    **row,
                    "created_at": row["created_at"].isoformat(),
                    "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
                }
                for row in attempts
            ],
            usage=list(
                LLMUsage.objects.filter(user=teacher)
                .values("status", "operation", "model")
                .annotate(
                    calls=Count("id"),
                    input_tokens=Sum("input_tokens"),
                    output_tokens=Sum("output_tokens"),
                    total_tokens=Sum("total_tokens"),
                )
            ),
            question_results=GradingResult.objects.filter(
                submission__assignment=assignment
            ).count(),
            criterion_results=sum(
                len(criteria)
                for criteria in GradingResult.objects.filter(
                    submission__assignment=assignment
                ).values_list("criterion_results", flat=True)
            ),
            progress_request_median_seconds=round(statistics.median(response_latencies), 6),
            progress_request_max_seconds=round(max(response_latencies), 6),
            progress_requests=len(response_latencies),
            no_partial_student_results=True,
            passed=True,
        )
        assert report["question_results"] == args.students * args.questions
        assert report["criterion_results"] == args.students * args.questions * 2
        assert all(row["state"] == "succeeded" for row in attempts)
        assert len(attempts) == args.students * (args.questions + 1)
        print(
            json.dumps(
                {k: v for k, v in report.items() if k not in {"attempts", "ai_configuration"}},
                indent=2,
            ),
            flush=True,
        )
    except Exception as exc:
        report.update(passed=False, failure=str(exc))
        raise
    finally:
        if teacher is not None:
            # Retain protected usage rows so real charges still count against global quotas.
            teacher.is_active = False
            teacher.set_unusable_password()
            teacher.save(update_fields=("is_active", "password"))
            if not args.retain_fixtures and (
                parent is None or not parent.children.filter(state__in=ACTIVE_STATES).exists()
            ):
                AIJob.objects.filter(owner=teacher).delete()
                if assignment is not None:
                    assignment.delete()
                report["synthetic_assignments_removed"] = True
            report["audit_account_disabled_usage_preserved"] = True
        session_key = http.cookies.get("sessionid")
        if session_key:
            Session.objects.filter(session_key=session_key).delete()
        http.close()
        report["after_counts"] = {
            "users": User.objects.count(),
            "assignments": Assignment.objects.count(),
            "submissions": StudentSubmission.objects.count(),
        }
        save_report()


if __name__ == "__main__":
    main()
