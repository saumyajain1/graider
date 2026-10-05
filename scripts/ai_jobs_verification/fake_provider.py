"""Test-only OpenAI SDK transport; never copied into the production image."""

import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4

import httpx
import openai
from django.db import connection

REAL_OPENAI = openai.OpenAI


def event(kind, **values):
    path = os.environ.get("GRAIDER_VERIFY_EVENTS")
    if path:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(
                descriptor,
                (json.dumps({"event": kind, "time": time.time(), **values}) + "\n").encode(),
            )
        finally:
            os.close(descriptor)


def pause(marker):
    path = Path(marker)
    info = getattr(connection.connection, "info", None)
    path.write_text(str(getattr(info, "backend_pid", "ready")))
    while not Path(str(path) + ".release").exists():
        time.sleep(0.01)


def reply(request):
    assert not connection.in_atomic_block and connection.get_autocommit()
    payload = json.loads(request.content)
    schema = payload["response_format"]["json_schema"]["name"]
    prompt = payload["messages"][-1]["content"]
    request_id = uuid4().hex
    event("start", request_id=request_id, schema=schema)
    if os.environ.get("GRAIDER_VERIFY_FAULT") == "dispatch":
        pause(os.environ["GRAIDER_VERIFY_MARKER"])
    slow = "SLOW_STUDENT" in prompt
    time.sleep(
        float(os.environ.get("GRAIDER_VERIFY_SLOW_DELAY" if slow else "GRAIDER_VERIFY_DELAY", "0"))
    )
    if schema == "SubmissionAnswerMappingSchema":
        output = {
            "answers": [
                {
                    "part_key": key,
                    "extracted_answer_text": ("SLOW_STUDENT " if slow else "")
                    + "2+2=4; addition is shown.",
                    "mapping_confidence": 0.98,
                }
                for key in re.findall(r"internal_key=([^\s]+)", prompt)
            ]
        }
    elif schema == "GeneratedQuestionGradeSchema":
        output = {
            "criteria": [
                {
                    "criterion_id": int(key),
                    "score": float(points),
                    "feedback": "Correct method and evidence in the synthetic response.",
                }
                for key, points in re.findall(r"criterion_id=(\d+):[^\n]*?\(([\d.]+) pts\)", prompt)
            ],
            "feedback": "The synthetic response satisfies the reference answer and rubric.",
            "reasoning_summary": "Each supplied criterion was assessed against the reference answer.",
            "confidence_score": 0.98,
            "needs_review": False,
        }
    elif schema == "GeneratedReferenceAnswerSchema":
        output = {"answer_text": "2 + 2 = 4."}
    elif schema == "GeneratedRubricSchema":
        output = {
            "criteria": [
                {"title": "Correct result", "description": "Correct addition.", "max_points": 5}
            ]
        }
    elif schema == "GeneratedQuestionSetSchema":
        output = {
            "parts": [
                {
                    "part_type": "question",
                    "source_label": "1",
                    "text": "What is 2+2?",
                    "max_marks": 5,
                }
            ]
        }
    else:
        raise AssertionError(f"Unsupported verification schema: {schema}")
    event("end", request_id=request_id, schema=schema)
    input_tokens = sum(len(message["content"]) for message in payload["messages"]) // 4
    output_tokens = len(json.dumps(output)) // 4
    return httpx.Response(
        200,
        headers={"x-request-id": "verification-" + request_id},
        json={
            "id": "chatcmpl_verification",
            "object": "chat.completion",
            "created": 0,
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(output)},
                }
            ],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        },
    )


def install():
    def factory(**kwargs):
        return REAL_OPENAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(reply)))

    openai.OpenAI = factory
    # The subprocess helper initializes Django before installing the transport.
    from apps.grading.services import openai_client

    openai_client.OpenAI = factory
