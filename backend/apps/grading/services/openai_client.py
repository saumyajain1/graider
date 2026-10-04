import json
import logging
import os

from django.conf import settings
from openai import APIConnectionError, InternalServerError, OpenAI, OpenAIError, RateLimitError

from ..models import LLMUsage
from .usage import finish_usage, reserve_usage

logger = logging.getLogger(__name__)

OPERATION_OUTPUT_CAPS = {
    "question_generation": 8192,
    "question_repair": 4096,
    "reference_answer": 3072,
    "rubric_generation": 3072,
    "answer_mapping": 3072,
    "submission_grading": 2048,
}
OPERATION_REASONING_SETTINGS = {
    "question_generation": ("OPENAI_QUESTION_REASONING_EFFORT", "medium"),
    "question_repair": ("OPENAI_QUESTION_REPAIR_REASONING_EFFORT", "low"),
    "reference_answer": ("OPENAI_REFERENCE_REASONING_EFFORT", "medium"),
    "rubric_generation": ("OPENAI_RUBRIC_REASONING_EFFORT", "medium"),
    "answer_mapping": ("OPENAI_MAPPING_REASONING_EFFORT", "low"),
    "submission_grading": ("OPENAI_GRADING_REASONING_EFFORT", "medium"),
}
VALID_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
SPEND_LIMIT_CODES = {
    "project_spend_limit_exceeded",
    "organization_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
    "credit_balance_exhausted",
}


class LLMConfigurationError(Exception):
    pass


class LLMGenerationError(Exception):
    pass


class LLMTransientError(LLMGenerationError):
    pass


class LLMSpendLimitError(LLMGenerationError):
    pass


def public_llm_error(exc):
    if isinstance(exc, LLMSpendLimitError):
        return (
            "AI is unavailable because its spending limit has been reached. Please try again later."
        )
    if isinstance(exc, LLMConfigurationError):
        return "AI is temporarily unavailable. Please try again later."
    return "AI request failed. Please try again."


def get_float_env(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def get_reasoning_effort(operation):
    name, default = OPERATION_REASONING_SETTINGS[operation]
    value = os.getenv(name, default).strip().lower()
    if value not in VALID_REASONING_EFFORTS:
        raise LLMConfigurationError(
            f"{name} must be one of: {', '.join(sorted(VALID_REASONING_EFFORTS))}."
        )
    return value


def _provider_error_code(exc):
    code = getattr(exc, "code", None)
    body = getattr(exc, "body", None)
    if not code and isinstance(body, dict):
        nested = body.get("error")
        code = body.get("code") or (nested.get("code") if isinstance(nested, dict) else None)
    return code


def _estimate_tokens(system_prompt, user_prompt, response_format, max_output_tokens):
    schema = json.dumps(response_format.model_json_schema(), ensure_ascii=False)
    # Each UTF-8 byte is charged as one estimated input token, plus framing headroom.
    return (
        sum(len(text.encode("utf-8")) for text in (system_prompt, user_prompt, schema))
        + 256
        + max_output_tokens
    )


class OpenAIChatService:
    def __init__(self, client=None):
        if client is not None:
            self.client = client
            return

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMConfigurationError(
                "OPENAI_API_KEY is not configured. Add it to your environment to use AI generation."
            )

        self.client = OpenAI(
            api_key=api_key,
            timeout=get_float_env("OPENAI_TIMEOUT_SECONDS", 60.0),
            max_retries=0,
        )

    def parse(
        self,
        *,
        user,
        operation,
        model,
        response_format,
        system_prompt,
        user_prompt,
        reasoning_effort=None,
        accounting=None,
    ):
        if operation not in OPERATION_OUTPUT_CAPS:
            raise ValueError(f"Unknown AI operation: {operation}")
        reasoning_effort = (
            reasoning_effort if reasoning_effort is not None else get_reasoning_effort(operation)
        )
        max_output_tokens = min(
            settings.GRAIDER_MAX_OUTPUT_TOKENS, OPERATION_OUTPUT_CAPS[operation]
        )
        reserve = accounting.reserve if accounting else reserve_usage
        finish = accounting.finish if accounting else finish_usage
        usage_row = reserve(
            user=user,
            operation=operation,
            model=model,
            estimated_tokens=_estimate_tokens(
                system_prompt, user_prompt, response_format, max_output_tokens
            ),
        )
        try:
            completion = self.client.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_format,
                reasoning_effort=reasoning_effort,
                max_completion_tokens=max_output_tokens,
            )
        except OpenAIError as exc:
            uncertain = isinstance(exc, (APIConnectionError, InternalServerError))
            finish(
                usage_row,
                status=LLMUsage.Status.UNCERTAIN if uncertain else LLMUsage.Status.FAILED,
                request_id=getattr(exc, "request_id", None),
            )
            if _provider_error_code(exc) in SPEND_LIMIT_CODES:
                raise LLMSpendLimitError("OpenAI spending or usage limit reached.") from exc
            if isinstance(exc, RateLimitError):
                raise LLMTransientError("Provider rate limit reached.") from exc
            raise LLMGenerationError(str(exc)) from exc
        except Exception as exc:
            finish(usage_row, status=LLMUsage.Status.UNCERTAIN)
            if accounting:
                logger.warning("Unexpected background AI request failure (%s).", type(exc).__name__)
            else:
                logger.exception("Unexpected AI request failure")
            raise LLMGenerationError("Unexpected AI request failure.") from exc

        provider_usage = getattr(completion, "usage", None)
        input_tokens = getattr(provider_usage, "prompt_tokens", None)
        output_tokens = getattr(provider_usage, "completion_tokens", None)
        total_tokens = getattr(provider_usage, "total_tokens", None)
        metered = all(
            isinstance(value, int) for value in (input_tokens, output_tokens, total_tokens)
        )
        try:
            message = completion.choices[0].message
            refusal = getattr(message, "refusal", None)
            parsed = getattr(message, "parsed", None)
        except (AttributeError, IndexError, TypeError):
            refusal = None
            parsed = None

        finish(
            usage_row,
            **(
                {
                    "output": parsed.model_dump(mode="json")
                    if parsed is not None and not refusal
                    else {}
                }
                if accounting
                else {}
            ),
            status=(
                LLMUsage.Status.SUCCEEDED
                if parsed is not None and not refusal
                else LLMUsage.Status.FAILED
            )
            if metered
            else LLMUsage.Status.UNMETERED,
            input_tokens=input_tokens if metered else 0,
            output_tokens=output_tokens if metered else 0,
            total_tokens=total_tokens if metered else 0,
            request_id=getattr(completion, "_request_id", None),
        )
        if refusal:
            raise LLMGenerationError("Model declined the request.")
        if parsed is None:
            raise LLMGenerationError("Model returned no parsed output.")

        return parsed
