from datetime import UTC, timedelta

from django.conf import settings
from django.db import models, transaction
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import LLMQuotaLock, LLMUsage


class LLMQuotaExceeded(Exception):
    pass


RESERVED_STATUSES = (
    LLMUsage.Status.PENDING,
    LLMUsage.Status.UNCERTAIN,
    LLMUsage.Status.UNMETERED,
)


def _charged_tokens(queryset):
    charge = models.Case(
        models.When(status__in=RESERVED_STATUSES, then=models.F("reserved_tokens")),
        default=models.F("total_tokens"),
        output_field=models.IntegerField(),
    )
    return queryset.aggregate(total=Coalesce(models.Sum(charge), 0))["total"]


def reserve_usage(*, user, operation, model, estimated_tokens):
    now = timezone.now().astimezone(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)

    with transaction.atomic():
        # Every reservation takes this same row lock, including requests by different users.
        LLMQuotaLock.objects.select_for_update().get(pk=1)
        recent = LLMUsage.objects.filter(user=user, created_at__gte=now - timedelta(minutes=1))
        if recent.count() >= settings.GRAIDER_USER_AI_REQUESTS_PER_MINUTE:
            raise LLMQuotaExceeded("You are making AI requests too quickly. Please try again shortly.")

        own = LLMUsage.objects.filter(user=user)
        if _charged_tokens(own.filter(created_at__gte=day_start)) + estimated_tokens > settings.GRAIDER_USER_DAILY_TOKENS:
            raise LLMQuotaExceeded("Your daily AI allowance is used up. Please try again tomorrow.")
        if _charged_tokens(own.filter(created_at__gte=month_start)) + estimated_tokens > settings.GRAIDER_USER_MONTHLY_TOKENS:
            raise LLMQuotaExceeded("Your monthly AI allowance is used up. Please try again next month.")
        if _charged_tokens(LLMUsage.objects.filter(created_at__gte=month_start)) + estimated_tokens > settings.GRAIDER_GLOBAL_MONTHLY_TOKENS:
            raise LLMQuotaExceeded("Graider's AI allowance is used up. Please try again later.")

        return LLMUsage.objects.create(
            user=user,
            operation=operation,
            model=model,
            reserved_tokens=estimated_tokens,
        )


def finish_usage(usage, *, status, input_tokens=0, output_tokens=0, total_tokens=0, request_id=""):
    with transaction.atomic():
        LLMQuotaLock.objects.select_for_update().get(pk=1)
        row = LLMUsage.objects.select_for_update().get(pk=usage.pk)
        row.status = status
        row.input_tokens = input_tokens
        row.output_tokens = output_tokens
        row.total_tokens = total_tokens
        row.reserved_tokens = row.reserved_tokens if status in RESERVED_STATUSES else 0
        row.provider_request_id = request_id or ""
        row.completed_at = timezone.now()
        row.save(update_fields=(
            "status", "input_tokens", "output_tokens", "total_tokens", "reserved_tokens",
            "provider_request_id", "completed_at",
        ))
        return row
