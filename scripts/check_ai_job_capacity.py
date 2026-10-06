"""Check 10x10 jobs in the production image at 0.1 CPU / 512 MiB.

Requires an explicitly selected disposable local PostgreSQL container. AI uses
an opt-in mounted MockTransport; no real credentials or external calls are used.
"""

import argparse
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def memory_mib(value):
    amount, unit = re.fullmatch(r"([\d.]+)([A-Za-z]+)", value.split(" / ")[0]).groups()
    return float(amount) * {"B": 1 / 1048576, "KiB": 1 / 1024, "MiB": 1, "GiB": 1024}[unit]


def peak_calls(events):
    active, peak = set(), 0
    for line in events.read_text().splitlines():
        event = json.loads(line)
        if event["event"] == "start":
            active.add(event["request_id"])
            peak = max(peak, len(active))
        elif event["event"] == "end":
            active.remove(event["request_id"])
    assert not active, "Every simulated provider dispatch must complete."
    return peak


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--image", default="graider:step4-review")
    parser.add_argument("--delay", type=float, default=8)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--student-concurrency", type=int)
    parser.add_argument("--requests-per-minute", type=int, default=40)
    parser.add_argument("--web-workers", type=int, default=1)
    parser.add_argument("--web-threads", type=int, default=4)
    parser.add_argument("--scan-seconds", type=int, default=2)
    parser.add_argument(
        "--scoring-only",
        action="store_true",
        help="Prepare mapping checkpoints before timing 100 question scores and result publication.",
    )
    parser.add_argument(
        "--grading-only",
        action="store_true",
        help="Time answer mapping, scoring and publication, excluding admission and startup.",
    )
    parser.add_argument("--skip-restart", action="store_true")
    parser.add_argument(
        "--quiet-observation",
        action="store_true",
        help="Observe grading through the external DB instead of sending periodic web requests.",
    )
    parser.add_argument(
        "--warm-start",
        action="store_true",
        help="Boot at 2 CPUs, then enforce 0.1 CPU before releasing timed grading.",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    admin_url = os.environ.get("DATABASE_URL", "")
    parsed = urlsplit(admin_url)
    if parsed.scheme not in ("postgresql", "postgres") or parsed.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        parser.error("DATABASE_URL must explicitly select a disposable local PostgreSQL server.")
    if args.delay < 0:
        parser.error("Delay cannot be negative.")
    if args.scoring_only and args.grading_only:
        parser.error("Select either scoring-only or grading-only timing.")
    timed_only = args.scoring_only or args.grading_only
    if args.quiet_observation and not timed_only:
        parser.error("Quiet observation requires scoring-only or grading-only timing.")
    if args.warm_start and not timed_only:
        parser.error("Warm startup requires a timed-grading release barrier.")
    if args.student_concurrency is None:
        args.student_concurrency = args.concurrency
    if (
        min(
            args.concurrency,
            args.student_concurrency,
            args.requests_per_minute,
            args.web_workers,
            args.web_threads,
            args.scan_seconds,
        )
        <= 0
    ):
        parser.error(
            "Concurrency, request limits, web process/thread counts and scan time must be positive."
        )
    identity = uuid4().hex[:12]
    database = "graider_capacity_" + identity
    network, container = "graider-capacity-" + identity, "graider-capacity-" + identity
    test_url = urlunsplit(parsed._replace(path="/" + database))
    container_url = urlunsplit(
        parsed._replace(
            netloc=f"{parsed.username}:{parsed.password}@{args.postgres_container}:5432",
            path="/" + database,
            query="",
        )
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    shared = {
        "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": "capacity-test-only-" + "a1B2c3D4e5" * 6,
        "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
        "FRONTEND_URL": "",
        "DJANGO_CORS_ALLOWED_ORIGINS": "",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "",
        "AWS_ENDPOINT_URL_S3": "https://storage.example.invalid",
        "AWS_ACCESS_KEY_ID": "capacity-test-only",
        "AWS_SECRET_ACCESS_KEY": "capacity-test-only",
        "OPENAI_API_KEY": "fake-capacity-test-key",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "BREVO_API_KEY": "",
        "GRAIDER_AI_JOBS_ENABLED": "true",
        "GRAIDER_AI_CONCURRENCY": str(args.concurrency),
        "GRAIDER_AI_STUDENT_CONCURRENCY": str(args.student_concurrency),
        "GRAIDER_AI_LEASE_SECONDS": "90",
        "GRAIDER_AI_HEARTBEAT_SECONDS": "10",
        "GRAIDER_AI_SCAN_SECONDS": str(args.scan_seconds),
        "GRAIDER_AI_FAIRNESS_SECONDS": "30",
        "GRAIDER_AI_SAFE_RETRIES": "2",
        "GRAIDER_AI_RETRY_SECONDS": "10",
        "GRAIDER_AI_DRAIN_SECONDS": "20",
        "GRAIDER_AI_WAKE_SOCKET": "/tmp/graider-ai-worker.sock",
        "GRAIDER_AI_USER_QUEUE_LIMIT": "20",
        "GRAIDER_AI_GLOBAL_QUEUE_LIMIT": "50",
        "GRAIDER_AI_MAX_BATCH_SUBMISSIONS": "10",
        "GRAIDER_AI_MAX_GRADING_QUESTIONS": "10",
        "GRAIDER_USER_DAILY_TOKENS": "250000",
        "GRAIDER_USER_MONTHLY_TOKENS": "500000",
        "GRAIDER_GLOBAL_MONTHLY_TOKENS": "2000000",
        "GRAIDER_USER_AI_REQUESTS_PER_MINUTE": str(args.requests_per_minute),
        "GRAIDER_MAX_OUTPUT_TOKENS": "8192",
        "GUNICORN_WORKERS": str(args.web_workers),
        "GUNICORN_THREADS": str(args.web_threads),
        "GUNICORN_TIMEOUT_SECONDS": "120",
        "GUNICORN_GRACEFUL_TIMEOUT_SECONDS": "120",
        **{
            name: "gpt-6-luna"
            for name in (
                "OPENAI_QUESTION_MODEL",
                "OPENAI_ARTIFACT_MODEL",
                "OPENAI_MAPPING_MODEL",
                "OPENAI_GRADING_MODEL",
            )
        },
    }
    os.environ.update(shared, DATABASE_URL=test_url, DJANGO_SETTINGS_MODULE="config.settings")
    sys.path.insert(0, str(ROOT / "backend"))
    created = network_created = attached = container_started = False
    connections = None
    with tempfile.TemporaryDirectory(prefix="graider-capacity-") as directory:
        folder = Path(directory)
        folder.chmod(0o777)  # Synthetic event log written by the non-root image user.
        events = folder / "events.jsonl"
        report = {
            "cpu": 0.1,
            "startup_cpu": 2 if args.warm_start else 0.1,
            "run_started_at": datetime.now(UTC).isoformat(),
            "memory_limit_mib": 512,
            "students": 10,
            "questions_per_student": 10,
            "provider_delay_seconds": args.delay,
            "slow_student_delay_seconds": args.delay + 2,
            "simulated_provider": True,
            "external_database": "disposable local PostgreSQL",
            "runtime_image_id": docker("image", "inspect", args.image, "--format", "{{.Id}}"),
            "source_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "grading_concurrency": args.concurrency,
            "student_concurrency": args.student_concurrency,
            "requests_per_minute": args.requests_per_minute,
            "web_workers": args.web_workers,
            "web_threads": args.web_threads,
            "scan_seconds": args.scan_seconds,
            "progress_observation": "external database"
            if args.quiet_observation
            else "HTTP health, job and roster polling",
            "measurement": "question scoring and publication"
            if args.scoring_only
            else "answer mapping, question scoring and publication"
            if args.grading_only
            else "full grading workflow including admission",
        }

        def write_report():
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")

        try:
            with psycopg.connect(admin_url, autocommit=True) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            created = True
            import django

            django.setup()
            from django.core.management import call_command
            from django.db import connections

            from apps.accounts.models import User
            from apps.ai_jobs.models import AIJob
            from apps.assignments.models import Assignment, QuestionPart
            from apps.grading.models import (
                GradingResult,
                LLMUsage,
                ReferenceAnswer,
                RubricCriterion,
                StudentSubmission,
            )

            call_command("migrate", interactive=False, verbosity=0)
            teacher = User.objects.create_user(
                email="capacity@example.test",
                full_name="Synthetic Teacher",
                password="CapacityTest2026!",
            )
            assignment = Assignment.objects.create(
                teacher=teacher,
                title="Synthetic 10 by 10 workload",
                raw_assignment_text="\n".join(
                    f"Q{i}: Explain why 2+2=4 and show the calculation." for i in range(1, 11)
                ),
            )
            for index in range(1, 11):
                question = QuestionPart.objects.create(
                    assignment=assignment,
                    part_key=f"Q{index}",
                    source_label=str(index),
                    text="Explain why 2+2=4 and show the calculation.",
                    max_marks=5,
                    display_order=index,
                )
                ReferenceAnswer.objects.create(
                    question_part=question, answer_text="Adding two pairs gives four items; 2+2=4."
                )
                RubricCriterion.objects.create(
                    question_part=question,
                    title="Method",
                    description="Explain the addition of two pairs.",
                    max_points=3,
                )
                RubricCriterion.objects.create(
                    question_part=question,
                    title="Answer",
                    description="Give the correct sum, four.",
                    max_points=2,
                    display_order=1,
                )
            for index in range(10):
                StudentSubmission.objects.create(
                    assignment=assignment,
                    student_name=f"Synthetic student {index + 1}",
                    raw_response_text=("SLOW_STUDENT\n" if index == 0 else "")
                    + "\n".join(
                        f"Q{i}: Two items plus two more gives four items. 2+2=4."
                        for i in range(1, 11)
                    ),
                )
            if timed_only:
                from apps.ai_jobs.services import enqueue_job

                parent, _ = enqueue_job(
                    owner=teacher, operation=AIJob.Operation.BATCH, assignment_id=assignment.id
                )
                if args.scoring_only:
                    from django.test import override_settings

                    from apps.ai_jobs.engine import claim_next, run_claim
                    from apps.ai_jobs.models import AIJobStep

                    sys.path.insert(0, str(ROOT / "scripts/ai_jobs_verification"))
                    from fake_provider import install

                    # Real mapping recipes/accounting with a simulated transport,
                    # no delay and outside the question-scoring timer.
                    os.environ["GRAIDER_VERIFY_DELAY"] = "0"
                    os.environ["GRAIDER_VERIFY_SLOW_DELAY"] = "0"
                    install()
                    with override_settings(GRAIDER_AI_STUDENT_CONCURRENCY=10):
                        for _ in range(10):
                            claim = claim_next()
                            assert claim and AIJobStep.objects.get(pk=claim[0]).key == "map"
                            run_claim(*claim)
                    assert parent.children.filter(completed_steps=1, state="queued").count() == 10
                    assert LLMUsage.objects.count() == 10
                else:
                    assert parent.children.filter(completed_steps=0, state="queued").count() == 10
                    assert not LLMUsage.objects.exists()
                assert not GradingResult.objects.exists()
                parent_id = str(parent.id)
            docker("network", "create", network)
            network_created = True
            docker("network", "connect", network, args.postgres_container)
            attached = True
            command = [
                "run",
                "--detach",
                "--name",
                container,
                "--network",
                network,
                "--cpus",
                "2" if args.warm_start else "0.1",
                "--memory",
                "512m",
                "--memory-swap",
                "512m",
                "--publish",
                f"127.0.0.1:{port}:10000",
                "--volume",
                f"{ROOT / 'scripts/ai_jobs_verification'}:/verification:ro",
                "--volume",
                f"{folder}:/verification-data",
            ]
            environment = {
                **shared,
                "DATABASE_URL": container_url,
                "PYTHONPATH": "/verification:/app/backend",
                "GRAIDER_VERIFY_FAKE_AI": "true",
                "GRAIDER_VERIFY_EVENTS": "/verification-data/events.jsonl",
                "GRAIDER_VERIFY_DELAY": str(args.delay),
                "GRAIDER_VERIFY_SLOW_DELAY": str(args.delay + 2),
            }
            if timed_only:
                environment["GRAIDER_VERIFY_SCORING_RELEASE"] = "/verification-data/release"
            for key, value in environment.items():
                command += ["--env", f"{key}={value}"]
            command.append(args.image)
            started = time.monotonic()
            docker(*command)
            container_started = True
            configuration = json.loads(docker("inspect", container))[0]["HostConfig"]
            assert (
                configuration["NanoCpus"] == (2000000000 if args.warm_start else 100000000)
                and configuration["Memory"] == 536870912
            )
            peak_memory = 0
            health_latencies = []
            client = httpx.Client(
                base_url=f"http://127.0.0.1:{port}",
                headers={"X-Forwarded-Proto": "https"},
                timeout=30,
                limits=httpx.Limits(max_keepalive_connections=0),
            )

            def sample():
                nonlocal peak_memory
                stats = json.loads(
                    docker("stats", "--no-stream", "--format", "{{json .}}", container)
                )
                peak_memory = max(peak_memory, memory_mib(stats["MemUsage"]))
                state = json.loads(docker("inspect", container))[0]["State"]
                assert state["Running"] and not state["OOMKilled"], (
                    "Verification container stopped or ran out of memory."
                )

            def request(method, path, body=None):
                headers = {
                    "Cookie": "; ".join(f"{key}={value}" for key, value in client.cookies.items()),
                    "Origin": f"https://127.0.0.1:{port}",
                }
                if method == "POST":
                    headers["X-CSRFToken"] = client.cookies.get("csrftoken", "")
                return client.request(
                    method, path, headers=headers, json=body if method == "POST" else None
                )

            def ready():
                until = time.monotonic() + 600
                last_progress = time.monotonic()
                while time.monotonic() < until:
                    try:
                        response = client.get("/health/", timeout=2)
                        if response.status_code == 200:
                            sample()
                            return
                    except httpx.TransportError:
                        pass
                    if time.monotonic() - last_progress > 30:
                        sample()
                        print("Waiting for constrained container startup...", flush=True)
                        last_progress = time.monotonic()
                    time.sleep(2)
                raise AssertionError("Constrained container did not become ready in 600 seconds.")

            ready()
            report["web_ready_seconds"] = round(time.monotonic() - started, 2)
            assert client.get("/login").status_code == 200
            assert (
                client.get("/api/auth/me").status_code == 401
            )  # Establish the normal CSRF cookie.
            login = request(
                "POST", "/api/auth/login", {"email": teacher.email, "password": "CapacityTest2026!"}
            )
            assert login.status_code == 200, login.text
            report["startup_sampled_peak_memory_mib"] = round(peak_memory, 2)
            peak_memory = 0
            if timed_only:
                until = time.monotonic() + 180
                while time.monotonic() < until:
                    if events.exists() and "worker_waiting" in events.read_text():
                        break
                    time.sleep(1)
                else:
                    raise AssertionError("Scoring worker did not reach the release barrier.")
                if args.warm_start:
                    docker("update", "--cpus", "0.1", container)
                constrained = json.loads(docker("inspect", container))[0]["HostConfig"]
                assert constrained["NanoCpus"] == 100000000
                assert constrained["Memory"] == constrained["MemorySwap"] == 536870912
                assert "scoring_start" not in events.read_text()
                accepted = time.monotonic()
                (folder / "release").touch()
                report["admission_seconds"] = None
            else:
                # Worker readiness can follow web readiness; 503 writes no job.
                until = time.monotonic() + 180
                while time.monotonic() < until:
                    accepted = time.monotonic()
                    response = request("POST", f"/api/assignments/{assignment.id}/grade-all", {})
                    if response.status_code == 202:
                        break
                    assert response.status_code == 503, response.text
                    assert not AIJob.objects.exists()
                    time.sleep(3)
                else:
                    raise AssertionError("Background worker did not become ready.")
                report["admission_seconds"] = round(time.monotonic() - accepted, 2)
                assert report["admission_seconds"] < 10, "Job admission must return promptly."
                parent_id = response.json()["id"]
            first_completion = None
            observations = 0
            while time.monotonic() - accepted < 900:
                if args.quiet_observation:
                    parent_state = AIJob.objects.get(pk=parent_id).state
                    children = list(AIJob.objects.filter(parent_id=parent_id).values("state"))
                    roster = list(
                        StudentSubmission.objects.values("id", "grading_status", "total_score")
                    )
                    for student in roster:
                        if student["total_score"] is not None:
                            student["total_score"] = str(student["total_score"])
                else:
                    heartbeat_started = time.monotonic()
                    assert client.get("/health/").status_code == 200
                    health_latencies.append(time.monotonic() - heartbeat_started)
                    progress = request("GET", f"/api/ai/jobs/{parent_id}/")
                    assert progress.status_code == 200, progress.text
                    children = progress.json()["children"]
                    parent_state = progress.json()["state"]
                    roster = request("GET", f"/api/assignments/{assignment.id}/submissions").json()
                assert not {child["state"] for child in children} & {
                    "failed",
                    "paused_quota",
                    "needs_attention",
                    "superseded",
                }, str(children)
                completed = [row for row in roster if row["grading_status"] == "graded"]
                for student in completed:
                    assert GradingResult.objects.filter(submission_id=student["id"]).count() == 10
                    assert student["total_score"] == "50.00"
                incomplete_ids = [row["id"] for row in roster if row["grading_status"] != "graded"]
                # One DB snapshot avoids a false failure if a pending roster row
                # commits complete grades between the HTTP response and this check.
                assert (
                    not StudentSubmission.objects.exclude(grading_status="graded")
                    .filter(grading_results__isnull=False)
                    .exists()
                ), "No partial student results may be published."
                if completed and incomplete_ids and first_completion is None:
                    first_completion = time.monotonic() - accepted
                    if args.quiet_observation:
                        detail = {
                            "grading_results": list(
                                GradingResult.objects.filter(
                                    submission_id=completed[0]["id"]
                                ).values("criterion_results")
                            )
                        }
                    else:
                        detail = request(
                            "GET", f"/api/submissions/{completed[0]['id']}/grading"
                        ).json()
                    assert len(detail["grading_results"]) == 10
                    assert all(
                        len(row["criterion_results"]) == 2 for row in detail["grading_results"]
                    )
                    print(
                        f"First complete student visible after {first_completion:.1f}s; other students still running.",
                        flush=True,
                    )
                sample()
                observations += 1
                if parent_state == "succeeded":
                    assert len(completed) == 10
                    break
                if observations % 10 == 0:
                    print(
                        f"Capacity check: {len(completed)}/10 students complete; {peak_memory:.1f} MiB sampled peak.",
                        flush=True,
                    )
                time.sleep(3)
            else:
                raise AssertionError("10x10 workload exceeded the 900-second target.")
            if args.quiet_observation:
                # Confirm normal owned API visibility after the recorded grading interval.
                assert request("GET", f"/api/ai/jobs/{parent_id}/").json()["state"] == "succeeded"
                detail = request("GET", f"/api/submissions/{completed[0]['id']}/grading").json()
                assert len(detail["grading_results"]) == 10
            report.update(
                workload_seconds=round(time.monotonic() - accepted, 2),
                first_student_complete_seconds=round(first_completion, 2)
                if first_completion is not None
                else None,
                observations=observations,
            )
            if timed_only:
                start = next(
                    json.loads(line)["time"]
                    for line in events.read_text().splitlines()
                    if json.loads(line)["event"] == "scoring_start"
                )
                finished = list(parent.children.values_list("finished_at", flat=True))
                assert all(finished)
                report.update(
                    grading_seconds=round(max(row.timestamp() for row in finished) - start, 2),
                    first_student_scored_seconds=round(
                        min(row.timestamp() for row in finished) - start, 2
                    ),
                    preparation_mapping_calls=10 if args.scoring_only else 0,
                    timed_provider_calls=100 if args.scoring_only else 110,
                )
                published = [
                    json.loads(line)
                    for line in events.read_text().splitlines()
                    if json.loads(line)["event"] == "published"
                ]
                if published:
                    assert len(published) == 10 and len({row["job_id"] for row in published}) == 10
                    report["grading_seconds"] = round(
                        max(row["time"] for row in published) - start, 2
                    )
                    report["first_student_scored_seconds"] = round(
                        min(row["time"] for row in published) - start, 2
                    )
                    report["timing_boundary"] = "worker release to last student publication commit"
                else:
                    # Older mounted helpers can finish an already-running benchmark.
                    report["timing_boundary"] = "worker release to last student finished_at"
                report["student_completion_seconds"] = sorted(
                    round(row["time"] - start, 2) for row in published
                )
                dispatches = [
                    json.loads(line)
                    for line in events.read_text().splitlines()
                    if json.loads(line)["event"] in ("start", "end")
                ]
                assert len(dispatches) == report["timed_provider_calls"] * 2
                assert (
                    sum(
                        row["schema"] == "GeneratedQuestionGradeSchema" and row["event"] == "start"
                        for row in dispatches
                    )
                    == 100
                )
                assert sum(
                    row["schema"] == "SubmissionAnswerMappingSchema" and row["event"] == "start"
                    for row in dispatches
                ) == (10 if args.grading_only else 0)
                begun = {
                    row["request_id"]: row["time"] for row in dispatches if row["event"] == "start"
                }
                durations = sorted(
                    row["time"] - begun[row["request_id"]]
                    for row in dispatches
                    if row["event"] == "end"
                )
                report["simulated_call_median_seconds"] = round(statistics.median(durations), 2)
                report["simulated_call_p95_seconds"] = round(
                    durations[ceil(0.95 * len(durations)) - 1], 2
                )
                if args.scoring_only:
                    report["scoring_seconds"] = report["grading_seconds"]
            assert first_completion is not None, (
                "A student must become available before the entire batch completes."
            )
            assert (
                LLMUsage.objects.count() == 110
                and not LLMUsage.objects.exclude(status="succeeded").exists()
            )
            assert GradingResult.objects.count() == 100
            reservations = sorted(
                row.timestamp() for row in LLMUsage.objects.values_list("created_at", flat=True)
            )
            report["peak_reserved_requests_per_minute"] = max(
                sum(start - 60 < stamp <= start for stamp in reservations) for start in reservations
            )
            assert (
                sum(
                    len(parts)
                    for parts in GradingResult.objects.values_list("criterion_results", flat=True)
                )
                == 200
            )
            report["peak_concurrent_provider_calls"] = peak_calls(events)
            assert report["peak_concurrent_provider_calls"] <= args.concurrency
            assert peak_memory < 450, "Sampled memory exceeded the 450 MiB target."
            if not args.skip_restart and not timed_only:
                calls_before_restart = len(events.read_text().splitlines())
                restart = time.monotonic()
                docker("restart", "--time", "25", container)
                ready()
                report["restart_web_ready_seconds"] = round(time.monotonic() - restart, 2)
                restored = request("GET", f"/api/ai/jobs/{parent_id}/")
                assert restored.status_code == 200 and restored.json()["state"] == "succeeded"
                assert GradingResult.objects.count() == 100
                assert (
                    sum(
                        len(parts)
                        for parts in GradingResult.objects.values_list(
                            "criterion_results", flat=True
                        )
                    )
                    == 200
                )
                assert LLMUsage.objects.count() == 110
                time.sleep(3)
                assert len(events.read_text().splitlines()) == calls_before_restart, (
                    "Restart must not repeat completed provider calls."
                )
                sample()
                assert peak_memory < 450, (
                    "Sampled memory exceeded the 450 MiB target after restart."
                )
            report.update(
                sampled_peak_memory_mib=round(peak_memory, 2),
                max_health_seconds=round(max(health_latencies), 2) if health_latencies else None,
                provider_calls=110,
                question_results=100,
                criterion_results=200,
                restart_preserved_results=True if not (args.skip_restart or timed_only) else None,
                no_oom=True,
                passed=True,
            )
            write_report()
            print(json.dumps(report, indent=2), flush=True)
            client.close()
        except Exception as exc:
            report.update(passed=False, failure_type=type(exc).__name__, failure=str(exc))
            if connections is not None:
                try:
                    report["job_states"] = list(AIJob.objects.values_list("state", flat=True))
                    report["completed_questions"] = GradingResult.objects.count()
                except Exception:
                    pass
            write_report()
            if container_started:
                print(docker("logs", "--tail", "25", container), file=sys.stderr)
            raise
        finally:
            if container_started:
                docker("rm", "--force", container)
            if attached:
                docker("network", "disconnect", network, args.postgres_container)
            if network_created:
                docker("network", "rm", network)
            if created:
                if connections is not None:
                    connections.close_all()
                with psycopg.connect(admin_url, autocommit=True) as admin:
                    admin.execute(
                        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
                    )


if __name__ == "__main__":
    main()
