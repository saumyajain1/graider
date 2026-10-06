"""Opt-in numeric execution logs; never log prompts, responses or credentials."""

import json
import logging
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("graider.ai_metrics")


def container_resources():
    values = {}
    root = Path("/sys/fs/cgroup")
    try:
        if (root / "memory.current").exists():
            values["memory_bytes"] = int((root / "memory.current").read_text())
            values["cpu_seconds"] = (
                int(
                    dict(line.split() for line in (root / "cpu.stat").read_text().splitlines())[
                        "usage_usec"
                    ]
                )
                / 1_000_000
            )
            values["oom_kills"] = int(
                dict(line.split() for line in (root / "memory.events").read_text().splitlines())[
                    "oom_kill"
                ]
            )
        else:
            values["memory_bytes"] = int((root / "memory/memory.usage_in_bytes").read_text())
            values["cpu_seconds"] = (
                int((root / "cpuacct/cpuacct.usage").read_text()) / 1_000_000_000
            )
    except (OSError, ValueError, KeyError):
        pass  # Unsupported hosts still emit execution timing.
    return values


def metric(event, **values):
    if settings.GRAIDER_AI_METRICS:
        logger.info(
            "AI_METRIC %s",
            json.dumps(
                {
                    "event": event,
                    "timestamp": datetime.now(UTC).isoformat(),
                    **container_resources(),
                    **values,
                },
                separators=(",", ":"),
            ),
        )


@contextmanager
def provider_timing(usage_id, operation, model):
    if not settings.GRAIDER_AI_METRICS:
        yield
        return
    started = time.monotonic()
    metric("provider_start", usage_id=usage_id, operation=operation, model=model)
    outcome = "error"
    try:
        yield
        outcome = "returned"
    finally:
        metric(
            "provider_end",
            usage_id=usage_id,
            operation=operation,
            model=model,
            outcome=outcome,
            duration_seconds=round(time.monotonic() - started, 6),
        )
