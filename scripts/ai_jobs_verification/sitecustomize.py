"""Opt-in SDK replacement for the constrained verification container only."""

import os

if os.environ.get("GRAIDER_VERIFY_FAKE_AI") == "true":
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from fake_provider import install

    install()

    # Only the scoring benchmark waits here; production never mounts this module.
    release = os.environ.get("GRAIDER_VERIFY_SCORING_RELEASE")
    if release:
        import time
        from pathlib import Path

        from django.db import transaction
        from fake_provider import event

        from apps.ai_jobs import engine
        from apps.ai_jobs.runtime import Worker

        original_run = Worker.run

        def scoring_run(self, **kwargs):
            event("worker_waiting")
            while not Path(release).exists():
                time.sleep(0.1)
            event("scoring_start")
            return original_run(self, **kwargs)

        Worker.run = scoring_run
        original_publish = engine.publish

        def scoring_publish(job):
            result = original_publish(job)
            transaction.on_commit(lambda: event("published", job_id=str(job.id)))
            return result

        engine.publish = scoring_publish
