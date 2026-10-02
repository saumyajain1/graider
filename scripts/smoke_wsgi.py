"""Test-only WSGI wrapper: real Django and quotas, an in-memory OpenAI transport.

This file is outside backend/ and is never copied into the production image.
"""

import json
import os
import time

import httpx
from django.db import connection
from openai import OpenAI
from psycopg.pq import TransactionStatus

# Initialize Django before importing services that access its models.
from config.wsgi import application as application  # isort: skip

from apps.grading.services import openai_client


def provider_reply(request):
    assert connection.get_autocommit() and not connection.in_atomic_block
    assert connection.connection.info.transaction_status == TransactionStatus.IDLE
    payload = json.loads(request.content)
    schema_name = payload["response_format"]["json_schema"]["name"]
    if schema_name == "SubmissionAnswerMappingSchema":
        result = {
            "answers": [
                {"part_key": f"q{i}", "extracted_answer_text": "2", "mapping_confidence": 1}
                for i in range(1, 6)
            ]
        }
    elif schema_name == "GeneratedQuestionGradeSchema":
        result = {
            "score": 2,
            "feedback": "Correct.",
            "reasoning_summary": "1 + 1 = 2.",
            "confidence_score": 1,
            "needs_review": False,
        }
    else:
        raise AssertionError(f"Unexpected smoke-test operation: {schema_name}")
    time.sleep(float(os.environ["GRAIDER_SMOKE_AI_DELAY"]))
    assert not connection.in_atomic_block
    return httpx.Response(
        200,
        headers={"x-request-id": "req_smoke"},
        json={
            "id": "chatcmpl_smoke",
            "object": "chat.completion",
            "created": 0,
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(result)},
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        },
    )


def fake_openai(**kwargs):
    return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(provider_reply)))


openai_client.OpenAI = fake_openai
