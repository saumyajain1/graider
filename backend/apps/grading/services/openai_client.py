import os

from openai import OpenAI
from openai import OpenAIError


class LLMConfigurationError(Exception):
    pass


class LLMGenerationError(Exception):
    pass


def get_float_env(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def get_int_env(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


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
            max_retries=get_int_env("OPENAI_MAX_RETRIES", 2),
        )

    def parse(
        self,
        *,
        model,
        response_format,
        system_prompt,
        user_prompt,
        reasoning_effort="medium",
    ):
        try:
            completion = self.client.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_format,
                reasoning_effort=reasoning_effort,
            )
        except OpenAIError as exc:
            raise LLMGenerationError(str(exc)) from exc

        message = completion.choices[0].message
        if getattr(message, "refusal", None):
            raise LLMGenerationError(message.refusal)

        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise LLMGenerationError("Model returned no parsed output.")

        return parsed
