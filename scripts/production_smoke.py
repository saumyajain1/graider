"""Exercise production Gunicorn against a new local PostgreSQL test database.

No Neon, object storage, or real OpenAI calls are used. Requires built frontend
assets and DATABASE_URL pointing to a disposable PostgreSQL server on localhost.
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delay", type=float, default=4.1, help="Seconds per mocked AI call (default: 4.1)."
    )
    args = parser.parse_args()
    admin_url = os.environ.get("DATABASE_URL", "")
    parsed_url = urlsplit(admin_url)
    if parsed_url.scheme not in ("postgresql", "postgres") or parsed_url.hostname not in (
        "127.0.0.1",
        "localhost",
        "::1",
    ):
        parser.error("DATABASE_URL must explicitly point to a local PostgreSQL test server.")
    if args.delay * 30 <= 120:
        parser.error(
            "Use --delay greater than 4 to test a bulk request longer than the 120-second worker timeout."
        )
    if not (ROOT / "frontend/dist/index.html").is_file():
        parser.error("Build the frontend before running this check.")

    database_name = "graider_smoke_" + uuid4().hex[:12]
    test_url = urlunsplit(parsed_url._replace(path="/" + database_name))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    os.environ.update(
        DJANGO_SETTINGS_MODULE="config.settings",
        DJANGO_DEBUG="false",
        DJANGO_SECRET_KEY="smoke-test-only-" + "a1B2c3D4e5" * 6,
        DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost",
        DATABASE_URL=test_url,
        FRONTEND_URL="",
        DJANGO_CORS_ALLOWED_ORIGINS="",
        DJANGO_CSRF_TRUSTED_ORIGINS="",
        AWS_ENDPOINT_URL_S3="https://storage.example.invalid",
        AWS_ACCESS_KEY_ID="smoke-test-only",
        AWS_SECRET_ACCESS_KEY="smoke-test-only",
        OPENAI_API_KEY="smoke-test-only-not-a-real-key",
        OPENAI_TIMEOUT_SECONDS="60",
        GRAIDER_USER_DAILY_TOKENS="250000",
        GRAIDER_USER_MONTHLY_TOKENS="500000",
        GRAIDER_GLOBAL_MONTHLY_TOKENS="2000000",
        GRAIDER_USER_AI_REQUESTS_PER_MINUTE="40",
        GRAIDER_MAX_OUTPUT_TOKENS="8192",
        GRAIDER_MAX_GRADE_ALL_SUBMISSIONS="5",
        GRAIDER_MAX_GRADE_ALL_QUESTIONS="5",
        GRAIDER_GRADE_REPEAT_COOLDOWN_SECONDS="120",
        GUNICORN_WORKERS="1",
        GUNICORN_THREADS="4",
        GUNICORN_TIMEOUT_SECONDS="120",
        GUNICORN_GRACEFUL_TIMEOUT_SECONDS="120",
        PORT=str(port),
        GRAIDER_SMOKE_AI_DELAY=str(args.delay),
        PYTHONPATH=os.pathsep.join((str(ROOT / "backend"), str(ROOT / "scripts"))),
    )
    for name in (
        "OPENAI_QUESTION_MODEL",
        "OPENAI_ARTIFACT_MODEL",
        "OPENAI_MAPPING_MODEL",
        "OPENAI_GRADING_MODEL",
    ):
        os.environ[name] = "gpt-6-luna"
    sys.path.insert(0, str(ROOT / "backend"))

    server = None
    created = False
    with TemporaryDirectory(prefix="graider-smoke-") as directory:
        try:
            with psycopg.connect(admin_url, autocommit=True) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
            created = True
            import django

            django.setup()
            from django.core.management import call_command
            from django.db import connections

            from apps.accounts.models import User
            from apps.assignments.models import Assignment, QuestionPart
            from apps.grading.models import (
                GradingResult,
                LLMUsage,
                ReferenceAnswer,
                RubricCriterion,
                StudentSubmission,
            )

            call_command("migrate", interactive=False, verbosity=0)
            user = User.objects.create_user(
                email="smoke@example.com", full_name="Smoke Test", password="SmokePassword123!"
            )

            def fixture(title, question_count, submission_count):
                assignment = Assignment.objects.create(teacher=user, title=title)
                for number in range(1, question_count + 1):
                    question = QuestionPart.objects.create(
                        assignment=assignment,
                        part_key=f"q{number}",
                        text="Compute 1 + 1.",
                        max_marks=2,
                        display_order=number,
                    )
                    ReferenceAnswer.objects.create(question_part=question, answer_text="2")
                    RubricCriterion.objects.create(
                        question_part=question,
                        title="Correct answer",
                        description="Award 2 for the answer 2.",
                        max_points=2,
                    )
                submissions = [
                    StudentSubmission.objects.create(
                        assignment=assignment,
                        student_name=f"Student {number}",
                        raw_response_text="1. 2\n2. 2\n3. 2\n4. 2\n5. 2",
                    )
                    for number in range(submission_count)
                ]
                return assignment, submissions

            _, single = fixture("Three-question grading", 3, 1)
            bulk, _ = fixture("Maximum-size bulk grading", 5, 5)
            logs_path = Path(directory) / "gunicorn.log"
            with logs_path.open("w+") as logs:
                server = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "gunicorn",
                        "--config",
                        "gunicorn.conf.py",
                        "smoke_wsgi:application",
                    ],
                    cwd=ROOT / "backend",
                    env=os.environ.copy(),
                    stdout=logs,
                    stderr=subprocess.STDOUT,
                )
                base_url = f"http://127.0.0.1:{port}"
                client = httpx.Client(
                    base_url=base_url,
                    headers={"X-Forwarded-Proto": "https"},
                    timeout=300,
                    # Polls occur at Gunicorn's keep-alive boundary; use fresh connections.
                    limits=httpx.Limits(max_keepalive_connections=0),
                )
                try:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        if server.poll() is not None:
                            raise AssertionError("Production server stopped during startup.")
                        try:
                            if client.get("/health/", timeout=2).status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.2)
                    else:
                        raise AssertionError("Production health endpoint did not become ready.")
                    page = client.get("/assignments/123/questions")
                    assert page.status_code == 200
                    assets = re.findall(r'(?:src|href)="(/static/frontend/[^\"]+)"', page.text)
                    assert assets, "Built frontend assets are missing."
                    for asset in assets:
                        assert client.get(asset).status_code == 200, asset
                    assert client.get("/api/not-a-route").status_code == 404
                    assert client.get("/api/auth/me").status_code == 401

                    def post(path, body=None):
                        # The test uses HTTP behind a simulated HTTPS proxy, so send secure cookies explicitly.
                        headers = {
                            "Cookie": "; ".join(
                                f"{key}={value}" for key, value in client.cookies.items()
                            ),
                            "X-CSRFToken": client.cookies.get("csrftoken"),
                            "Origin": base_url.replace("http:", "https:"),
                        }
                        return client.post(path, json=body or {}, headers=headers)

                    login = post(
                        "/api/auth/login", {"email": user.email, "password": "SmokePassword123!"}
                    )
                    assert login.status_code == 200, login.text
                    started = time.monotonic()
                    single_response = post(f"/api/submissions/{single[0].pk}/grade")
                    assert single_response.status_code == 200, single_response.text
                    single_elapsed = time.monotonic() - started
                    print(f"Three-question grading passed in {single_elapsed:.1f}s.", flush=True)

                    started = time.monotonic()
                    health_checks = 0
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        pending = executor.submit(post, f"/api/assignments/{bulk.pk}/grade-all")
                        while True:
                            try:
                                bulk_response = pending.result(timeout=2)
                                break
                            except TimeoutError:
                                health = client.get("/health/", timeout=2)
                                assert health.status_code == 200
                                health_checks += 1
                                if health_checks % 10 == 0:
                                    print(
                                        f"Bulk grading still running; health checks responsive ({time.monotonic() - started:.0f}s).",
                                        flush=True,
                                    )
                    bulk_elapsed = time.monotonic() - started
                    assert bulk_response.status_code == 200, bulk_response.text
                    assert bulk_response.json()["graded_count"] == 5, bulk_response.text
                    assert bulk_response.json()["failed_count"] == 0, bulk_response.text
                    assert bulk_elapsed > 120, (
                        "The request did not cross the configured worker timeout."
                    )
                    assert GradingResult.objects.count() == 28
                    assert LLMUsage.objects.count() == 34
                    assert LLMUsage.objects.exclude(status=LLMUsage.Status.SUCCEEDED).count() == 0
                    assert (
                        StudentSubmission.objects.filter(assignment=bulk, total_score=10).count()
                        == 5
                    )

                    used = LLMUsage.objects.count()
                    repeated = post(f"/api/assignments/{bulk.pk}/grade-all")
                    assert repeated.status_code == 200, repeated.text
                    assert LLMUsage.objects.count() == used, "Repeat grading spent more tokens."
                    assert client.get("/health/", timeout=2).status_code == 200
                    print(
                        json.dumps(
                            {
                                "single_seconds": round(single_elapsed, 1),
                                "bulk_seconds": round(bulk_elapsed, 1),
                                "health_checks_during_bulk": health_checks,
                                "mocked_provider_calls": used,
                                "provider_waits_inside_transactions": 0,
                            }
                        ),
                        flush=True,
                    )
                finally:
                    client.close()
                    server.terminate()
                    server.wait(timeout=15)
                    server = None
                text = logs_path.read_text()
                assert "WORKER TIMEOUT" not in text, text
                assert "Using worker: gthread" in text, text
        except Exception:
            logs_path = Path(directory) / "gunicorn.log"
            if logs_path.exists():
                print(logs_path.read_text(), file=sys.stderr)
            raise
        finally:
            if server is not None:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
            if created:
                from django.db import connections

                connections.close_all()
                with psycopg.connect(admin_url, autocommit=True) as admin:
                    admin.execute(
                        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                            sql.Identifier(database_name)
                        )
                    )


if __name__ == "__main__":
    main()
