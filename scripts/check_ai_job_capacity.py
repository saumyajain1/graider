"""Check 10x10 jobs in the production image at 0.1 CPU / 512 MiB.

Requires an explicitly selected disposable local PostgreSQL container. AI uses
an opt-in mounted MockTransport; no real credentials or external calls are used.
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
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
        else:
            active.remove(event["request_id"])
    assert not active, "Every simulated provider dispatch must complete."
    return peak


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--image", default="graider:step4-review")
    parser.add_argument("--delay", type=float, default=8)
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
        "GRAIDER_AI_CONCURRENCY": "3",
        "GRAIDER_AI_STUDENT_CONCURRENCY": "3",
        "GRAIDER_AI_LEASE_SECONDS": "90",
        "GRAIDER_AI_HEARTBEAT_SECONDS": "10",
        "GRAIDER_AI_SCAN_SECONDS": "2",
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
        "GRAIDER_USER_AI_REQUESTS_PER_MINUTE": "40",
        "GRAIDER_MAX_OUTPUT_TOKENS": "8192",
        "GUNICORN_WORKERS": "1",
        "GUNICORN_THREADS": "4",
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
            "memory_limit_mib": 512,
            "students": 10,
            "questions_per_student": 10,
            "provider_delay_seconds": args.delay,
            "slow_student_delay_seconds": args.delay + 2,
            "simulated_provider": True,
            "external_database": "disposable local PostgreSQL",
            "runtime_image_id": docker("image", "inspect", args.image, "--format", "{{.Id}}"),
        }
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
                "0.1",
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
            for key, value in environment.items():
                command += ["--env", f"{key}={value}"]
            command.append(args.image)
            started = time.monotonic()
            docker(*command)
            container_started = True
            configuration = json.loads(docker("inspect", container))[0]["HostConfig"]
            assert configuration["NanoCpus"] == 100000000 and configuration["Memory"] == 536870912
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
            report["cold_web_ready_seconds"] = round(time.monotonic() - started, 2)
            assert client.get("/login").status_code == 200
            assert (
                client.get("/api/auth/me").status_code == 401
            )  # Establish the normal CSRF cookie.
            login = request(
                "POST", "/api/auth/login", {"email": teacher.email, "password": "CapacityTest2026!"}
            )
            assert login.status_code == 200, login.text
            # The worker can become ready after the web server; unavailable admission writes no job.
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
                heartbeat_started = time.monotonic()
                assert client.get("/health/").status_code == 200
                health_latencies.append(time.monotonic() - heartbeat_started)
                progress = request("GET", f"/api/ai/jobs/{parent_id}/")
                assert progress.status_code == 200, progress.text
                children = progress.json()["children"]
                assert not {child["state"] for child in children} & {
                    "failed",
                    "paused_quota",
                    "needs_attention",
                    "superseded",
                }, progress.text
                roster = request("GET", f"/api/assignments/{assignment.id}/submissions").json()
                completed = [row for row in roster if row["grading_status"] == "graded"]
                for student in completed:
                    assert GradingResult.objects.filter(submission_id=student["id"]).count() == 10
                    assert student["total_score"] == "50.00"
                incomplete_ids = [row["id"] for row in roster if row["grading_status"] != "graded"]
                assert not GradingResult.objects.filter(
                    submission_id__in=incomplete_ids
                ).exists(), "No partial student results may be published."
                if completed and incomplete_ids and first_completion is None:
                    first_completion = time.monotonic() - accepted
                    detail = request("GET", f"/api/submissions/{completed[0]['id']}/grading").json()
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
                if progress.json()["state"] == "succeeded":
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
            report.update(
                workload_seconds=round(time.monotonic() - accepted, 2),
                first_student_complete_seconds=round(first_completion, 2)
                if first_completion is not None
                else None,
                observations=observations,
            )
            assert first_completion is not None, (
                "A student must become available before the entire batch completes."
            )
            assert (
                LLMUsage.objects.count() == 110
                and not LLMUsage.objects.exclude(status="succeeded").exists()
            )
            assert GradingResult.objects.count() == 100
            assert (
                sum(
                    len(parts)
                    for parts in GradingResult.objects.values_list("criterion_results", flat=True)
                )
                == 200
            )
            report["peak_concurrent_provider_calls"] = peak_calls(events)
            assert report["peak_concurrent_provider_calls"] == 3
            assert peak_memory < 450, "Sampled memory exceeded the 450 MiB target."
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
                    for parts in GradingResult.objects.values_list("criterion_results", flat=True)
                )
                == 200
            )
            assert LLMUsage.objects.count() == 110
            time.sleep(3)
            assert len(events.read_text().splitlines()) == calls_before_restart, (
                "Restart must not repeat completed provider calls."
            )
            sample()
            assert peak_memory < 450, "Sampled memory exceeded the 450 MiB target after restart."
            report.update(
                sampled_peak_memory_mib=round(peak_memory, 2),
                max_health_seconds=round(max(health_latencies), 2),
                provider_calls=110,
                question_results=100,
                criterion_results=200,
                restart_preserved_results=True,
                no_oom=True,
            )
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
            client.close()
        except Exception:
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
