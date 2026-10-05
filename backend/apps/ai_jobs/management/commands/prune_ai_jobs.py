from django.core.management.base import BaseCommand, CommandError

from apps.ai_jobs.retention import prune_jobs


class Command(BaseCommand):
    help = "Preview old terminal AI job cleanup; --apply deletes job diagnostics, never grades or usage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=30, help="Keep at least this many days (default: 30)."
        )
        parser.add_argument(
            "--batch-size", type=int, default=100, help="Root jobs per transaction, 1–100."
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Delete eligible job trees; otherwise preview only.",
        )

    def handle(self, *args, **options):
        try:
            result = prune_jobs(
                days=options["days"], batch_size=options["batch_size"], apply=options["apply"]
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        action = "Deleted" if options["apply"] else "Would delete"
        self.stdout.write(
            f"{action} {result['jobs']} job records in {result['roots']} root job trees."
        )
