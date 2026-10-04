"""Run real job code in an isolated subprocess with controllable crash boundaries."""

import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from fake_provider import event, install, pause  # noqa: E402

from apps.ai_jobs import engine  # noqa: E402
from apps.ai_jobs.accounting import AttemptAccounting  # noqa: E402
from apps.ai_jobs.runtime import Worker  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("single", "drain", "worker", "publish", "seed-local", "verify-local")
    )
    parser.add_argument(
        "--fault",
        choices=("claim", "dispatch", "response", "checkpoint", "publication", "published"),
    )
    parser.add_argument("--claim", nargs=2)
    args = parser.parse_args()
    install()
    if args.mode in ("seed-local", "verify-local"):
        from django.conf import settings
        from django.core.files.base import ContentFile

        from apps.accounts.models import User
        from apps.ai_jobs.services import enqueue_job
        from apps.assignments.models import Assignment, QuestionPart
        from apps.grading.models import LLMUsage, ReferenceAnswer

        settings.MEDIA_ROOT = Path(os.environ["GRAIDER_VERIFY_MEDIA_ROOT"])
        if args.mode == "seed-local":
            owner = User.objects.create_user(
                email="persistent@example.test", password="LocalTest2026!"
            )
            assignment = Assignment.objects.create(
                teacher=owner, title="Persistent local fixture", raw_assignment_text="What is 2+2?"
            )
            assignment.source_file.save("fixture.txt", ContentFile(b"Synthetic persistent upload"))
            QuestionPart.objects.create(
                assignment=assignment, part_key="Q1", text="What is 2+2?", max_marks=5
            )
            enqueue_job(owner=owner, operation="reference_answers", assignment_id=assignment.id)
        else:
            assignment = Assignment.objects.get()
            assert assignment.source_file.read() == b"Synthetic persistent upload"
            assert ReferenceAnswer.objects.get().answer_text == "2 + 2 = 4."
            assert LLMUsage.objects.count() == 1
            from apps.ai_jobs.models import AIJob

            assert AIJob.objects.get().state == "succeeded"
        print(json.dumps({"finished": True}), flush=True)
        return
    if args.fault == "dispatch":
        os.environ["GRAIDER_VERIFY_FAULT"] = "dispatch"

    def boundary(function, *, response_only=False):
        def wrapped(*positional, **kwargs):
            result = function(*positional, **kwargs)
            if not response_only or kwargs.get("output"):
                pause(os.environ["GRAIDER_VERIFY_MARKER"])
            return result

        return wrapped

    target = None
    if args.fault == "response":
        target = patch.object(
            AttemptAccounting, "finish", boundary(AttemptAccounting.finish, response_only=True)
        )
    elif args.fault == "checkpoint":
        target = patch.object(engine, "execute_recipe", boundary(engine.execute_recipe))
    elif args.fault == "publication":
        target = patch.object(engine, "publish", boundary(engine.publish))
    if target:
        target.start()
    try:
        if args.mode == "worker":
            worker = Worker()
            original_cycle = worker.cycle

            def observed_cycle():
                event("scan")
                return original_cycle()

            worker.cycle = observed_cycle
            worker.install_signals()
            worker.run()
        elif args.mode == "publish":
            claim = engine.claim_next()
            assert claim is None, "Publication-only process must not find remaining AI work."
            if args.fault == "published":
                pause(os.environ["GRAIDER_VERIFY_MARKER"])
        else:
            for _ in range(200):
                claim = (
                    (int(args.claim[0]), UUID(args.claim[1])) if args.claim else engine.claim_next()
                )
                if not claim:
                    break
                if args.fault == "claim":
                    pause(os.environ["GRAIDER_VERIFY_MARKER"])
                engine.run_claim(*claim)
                if args.mode == "single":
                    break
        print(json.dumps({"finished": True}), flush=True)
    finally:
        if target:
            target.stop()


if __name__ == "__main__":
    main()
