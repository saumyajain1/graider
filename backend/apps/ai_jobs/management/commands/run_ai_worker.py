from django.core.management.base import BaseCommand, CommandError

from apps.ai_jobs.runtime import Worker


class Command(BaseCommand):
    help = "Run the durable AI worker. Requires GRAIDER_AI_JOBS_ENABLED=true."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Drain runnable work, then exit.")

    def handle(self, *args, **options):
        worker = Worker()
        worker.install_signals()
        try:
            worker.run(once=options["once"])
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
