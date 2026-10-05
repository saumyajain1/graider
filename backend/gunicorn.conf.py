import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def positive_int(name, default):
    try:
        value = int(os.getenv(name, default))
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


bind = f"0.0.0.0:{positive_int('PORT', 10000)}"
workers = positive_int("GUNICORN_WORKERS", 1)
worker_class = "gthread"
threads = positive_int("GUNICORN_THREADS", 4)
# With gthread, this watches worker liveness, not the duration of a background AI job.
timeout = positive_int("GUNICORN_TIMEOUT_SECONDS", 120)
graceful_timeout = positive_int("GUNICORN_GRACEFUL_TIMEOUT_SECONDS", 120)
accesslog = "-"
errorlog = "-"
capture_output = True
max_requests = 1000
max_requests_jitter = 50


def post_worker_init(worker):
    from apps.ai_jobs.runtime import notify_worker

    notify_worker()
