"""Verify image defaults, maintenance mode and saved-response recovery on a local test DB."""

import argparse
import json
import os
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
import psycopg
from check_ai_job_capacity import docker
from psycopg import sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--image", default="graider:step5-review")
    args = parser.parse_args()
    admin_url = os.environ.get("DATABASE_URL", "")
    parsed = urlsplit(admin_url)
    if parsed.scheme not in ("postgres", "postgresql") or parsed.hostname not in (
        "127.0.0.1",
        "localhost",
        "::1",
    ):
        parser.error("DATABASE_URL must explicitly select a disposable local PostgreSQL server.")
    identity = uuid4().hex[:12]
    database, name = "graider_rollout_" + identity, "graider-rollout-" + identity
    source_url = urlunsplit(parsed._replace(path="/" + database))
    image_url = urlunsplit(
        parsed._replace(
            netloc=f"{parsed.username}:{parsed.password}@graider-rollout-db:5432",
            path="/" + database,
            query="",
        )
    )
    environment = {
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_DEBUG": "true",
        "DJANGO_SECRET_KEY": "rollout-test-only",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "FRONTEND_URL": "",
        "DJANGO_CORS_ALLOWED_ORIGINS": "",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "",
        "AWS_ENDPOINT_URL_S3": "",
        "AWS_ACCESS_KEY_ID": "",
        "AWS_SECRET_ACCESS_KEY": "",
        "OPENAI_API_KEY": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "BREVO_API_KEY": "",
    }
    os.environ.update(environment, DATABASE_URL=source_url, GRAIDER_AI_JOBS_ENABLED="false")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    created = network_created = attached = started = False
    try:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        created = True
        import django

        django.setup()
        from django.core.management import call_command
        from django.db import connections

        from apps.accounts.models import User
        from apps.ai_jobs.models import AIJobAttempt
        from apps.ai_jobs.services import enqueue_job
        from apps.assignments.models import Assignment, QuestionPart
        from apps.grading.models import LLMUsage, ReferenceAnswer

        call_command("migrate", interactive=False, verbosity=0)
        owner = User.objects.create_user(email="rollout@example.test", password="RolloutTest2026!")
        assignment = Assignment.objects.create(
            teacher=owner, title="Saved response recovery", raw_assignment_text="What is 2+2?"
        )
        question = QuestionPart.objects.create(
            assignment=assignment, part_key="Q1", text="What is 2+2?", max_marks=5
        )
        job, _ = enqueue_job(
            owner=owner, assignment_id=assignment.id, operation="reference_answers"
        )
        usage = LLMUsage.objects.create(
            user=owner,
            operation="reference_answer",
            model="test-only",
            status="succeeded",
            total_tokens=20,
        )
        AIJobAttempt.objects.create(
            step=job.steps.get(),
            number=1,
            claim_token=uuid4(),
            usage=usage,
            state="succeeded",
            output={"answer_text": "Recovered from saved response."},
        )
        docker("network", "create", name)
        network_created = True
        docker("network", "connect", "--alias", "graider-rollout-db", name, args.postgres_container)
        attached = True

        def start(paused):
            nonlocal started
            command = [
                "run",
                "--detach",
                "--name",
                name,
                "--network",
                name,
                "--publish",
                f"127.0.0.1:{port}:10000",
                "--memory",
                "512m",
            ]
            for key, value in {**environment, "DATABASE_URL": image_url}.items():
                command += ["--env", f"{key}={value}"]
            if paused:
                command += ["--env", "GRAIDER_AI_JOBS_ENABLED=false"]
            command.append(args.image)
            docker(*command)
            started = True
            until = time.monotonic() + 60
            while time.monotonic() < until:
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/health/", timeout=2).status_code == 200:
                        return
                except httpx.TransportError:
                    pass
                time.sleep(0.3)
            raise AssertionError("Verification container did not become healthy.")

        @contextmanager
        def session():
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
                assert client.get("/api/auth/me").status_code == 401
                response = client.post(
                    "/api/auth/login",
                    json={"email": owner.email, "password": "RolloutTest2026!"},
                    headers={"X-CSRFToken": client.cookies["csrftoken"]},
                )
                assert response.status_code == 200, response.text
                yield client

        start(paused=True)
        with session() as client:
            response = client.post(
                f"/api/assignments/{assignment.id}/reference-answers/generate",
                json={},
                headers={"X-CSRFToken": client.cookies["csrftoken"]},
            )
            assert response.status_code == 503 and "maintenance" in response.text
            assert client.get(f"/api/ai/jobs/{job.id}/").json()["state"] == "queued"
            assert client.get(f"/api/assignments/{assignment.id}").status_code == 200
        docker("rm", "--force", name)
        started = False
        start(
            paused=False
        )  # Omit the flag: verify that the released image enables its worker by default.
        until = time.monotonic() + 60
        while time.monotonic() < until:
            job.refresh_from_db()
            if job.state == "succeeded":
                break
            assert job.state in {"queued", "running"}, job.state
            time.sleep(0.3)
        assert job.state == "succeeded"
        with session() as client:
            response = client.get(f"/api/ai/jobs/{job.id}/")
            assert response.status_code == 200 and response.json()["state"] == "succeeded"
            answers = client.get(f"/api/assignments/{assignment.id}/reference-answers").json()
            assert answers[0]["answer_text"] == "Recovered from saved response."
        assert (
            ReferenceAnswer.objects.get(question_part=question).answer_text
            == "Recovered from saved response."
        )
        assert LLMUsage.objects.count() == 1 and AIJobAttempt.objects.count() == 1
        assert owner.__class__.objects.filter(pk=owner.id).exists()
        print(
            json.dumps(
                {
                    "image_default_enabled": True,
                    "maintenance_returns_503": True,
                    "job_history_survives_maintenance": True,
                    "saved_response_published_on_restart": True,
                    "accounts_preserved": True,
                    "additional_provider_calls": 0,
                }
            ),
            flush=True,
        )
    except Exception:
        if started:
            print(docker("logs", "--tail", "25", name), file=sys.stderr)
        raise
    finally:
        if started:
            docker("rm", "--force", name)
        if attached:
            docker("network", "disconnect", name, args.postgres_container)
        if network_created:
            docker("network", "rm", name)
        if created:
            if "connections" in locals():
                connections.close_all()
            with psycopg.connect(admin_url, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
                )


if __name__ == "__main__":
    main()
