"""One atomic usage reservation per actual request; saved responses survive worker death."""

from django.db import transaction
from django.utils import timezone

from apps.grading.models import LLMUsage
from apps.grading.services.openai_client import OpenAIChatService
from apps.grading.services.usage import finish_usage, reserve_usage

from .models import AIJob, AIJobAttempt, AIJobStep, JobState
from .services import lock_coordinator


class ClaimLost(Exception):
    pass


def assert_claim(step_id, token):
    step = AIJobStep.objects.select_related("job").filter(pk=step_id).first()
    if step is None:
        raise ClaimLost()
    if (
        step.claim_token != token
        or step.state != JobState.RUNNING
        or step.lease_expires_at <= timezone.now()
    ):
        raise ClaimLost()
    if step.job.cancel_requested:
        raise ClaimLost()
    return step


class AttemptAccounting:
    def __init__(self, step, token):
        self.step_id = step.id
        self.token = token
        self.attempt_id = None

    def reserve(self, **kwargs):
        with transaction.atomic():
            lock_coordinator()
            step = assert_claim(self.step_id, self.token)
            usage = reserve_usage(**kwargs)
            attempt = AIJobAttempt.objects.create(
                step=step,
                number=step.attempts.count() + 1,
                claim_token=self.token,
                usage=usage,
                state=AIJobAttempt.State.DISPATCHED,
            )
            self.attempt_id = attempt.id
            return usage

    def finish(self, usage, *, output=None, **kwargs):
        with transaction.atomic():
            lock_coordinator()
            try:
                finish_usage(usage, **kwargs)
            except LLMUsage.DoesNotExist as exc:
                raise ClaimLost() from exc
            state = (
                AIJobAttempt.State.SUCCEEDED
                if output
                else (
                    AIJobAttempt.State.UNCERTAIN
                    if kwargs["status"] == LLMUsage.Status.UNCERTAIN
                    else AIJobAttempt.State.FAILED
                )
            )
            AIJobAttempt.objects.filter(pk=self.attempt_id).update(
                state=state,
                output=output or {},
                provider_request_id=kwargs.get("request_id") or "",
                finished_at=timezone.now(),
            )
            # A late response can resolve a lost-lease pause without repeating the charge.
            if output:
                step = AIJobStep.objects.select_related("job").filter(pk=self.step_id).first()
                if step and (
                    step.job.state == JobState.NEEDS_ATTENTION
                    and step.job.error_code == "uncertain_charge"
                    and not step.job.cancel_requested
                ):
                    step.state = JobState.QUEUED
                    step.save(update_fields=("state",))
                    AIJob.objects.filter(pk=step.job_id).update(
                        state=JobState.QUEUED,
                        error_code="",
                        error_message="",
                        updated_at=timezone.now(),
                    )


class RecipeService:
    def __init__(self, step, token, client=None):
        self.step, self.token, self.client = step, token, client

    def parse(self, **kwargs):
        operation = kwargs["operation"]
        # Revalidate domain constraints on replay; never repeat a saved provider response.
        cached = (
            self.step.attempts.filter(
                state=AIJobAttempt.State.SUCCEEDED, usage__operation=operation
            )
            .order_by("-number")
            .first()
        )
        if cached and cached.output:
            return kwargs["response_format"].model_validate(cached.output)
        config = self.step.job.input_snapshot["configuration"][operation]
        kwargs.update(
            model=config["model"],
            reasoning_effort=config["reasoning_effort"],
            accounting=AttemptAccounting(self.step, self.token),
        )
        provider = OpenAIChatService(client=self.client)
        try:
            return provider.parse(**kwargs)
        finally:
            if self.client is None:
                provider.client.close()
