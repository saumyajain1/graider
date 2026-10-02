import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import Mock, patch

import httpx
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from openai import APITimeoutError, RateLimitError
from pydantic import BaseModel

from apps.accounts.models import User

from .models import LLMQuotaLock, LLMUsage
from .services import usage as usage_service
from .services.openai_client import (
    LLMConfigurationError,
    LLMGenerationError,
    LLMSpendLimitError,
    OpenAIChatService,
)
from .services.usage import LLMQuotaExceeded, finish_usage, reserve_usage


class Reply(BaseModel):
    answer: str


def completion(*, prompt_tokens=120, completion_tokens=40, total_tokens=160, request_id="req_test"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(parsed=Reply(answer="done"), refusal=None))
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        _request_id=request_id,
    )


class LLMUsageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="teacher@example.com", full_name="Teacher", password="StrongPass123!"
        )
        self.provider_parse = Mock(return_value=completion())
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=self.provider_parse))
        )
        self.service = OpenAIChatService(client=client)

    def make_request(self):
        return self.service.parse(
            user=self.user,
            operation="reference_answer",
            model="gpt-5.4-mini",
            response_format=Reply,
            system_prompt="Answer carefully.",
            user_prompt="What is osmosis?",
        )

    def test_records_actual_usage_and_caps_output_without_holding_quota_transaction(self):
        baseline_atomic_depth = len(connection.atomic_blocks)

        def provider_call(**kwargs):
            self.assertEqual(len(connection.atomic_blocks), baseline_atomic_depth)
            pending = LLMUsage.objects.get()
            self.assertEqual(pending.status, LLMUsage.Status.PENDING)
            self.assertGreater(pending.reserved_tokens, 0)
            self.assertEqual(kwargs["max_completion_tokens"], 3072)
            return completion()

        self.provider_parse.side_effect = provider_call
        self.assertEqual(self.make_request().answer, "done")

        row = LLMUsage.objects.get()
        self.assertEqual(row.user, self.user)
        self.assertEqual(row.operation, "reference_answer")
        self.assertEqual(row.model, "gpt-5.4-mini")
        self.assertEqual((row.input_tokens, row.output_tokens, row.total_tokens), (120, 40, 160))
        self.assertEqual(row.status, LLMUsage.Status.SUCCEEDED)
        self.assertEqual(row.reserved_tokens, 0)
        self.assertEqual(row.provider_request_id, "req_test")

    def test_same_model_uses_independent_reasoning_settings_for_each_task(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_MAPPING_REASONING_EFFORT": "low",
                "OPENAI_GRADING_REASONING_EFFORT": "high",
            },
        ):
            for operation, expected_effort in (
                ("answer_mapping", "low"),
                ("submission_grading", "high"),
            ):
                self.service.parse(
                    user=self.user,
                    operation=operation,
                    model="gpt-6-luna",
                    response_format=Reply,
                    system_prompt="Follow the task instructions.",
                    user_prompt="Student answer text.",
                )
                kwargs = self.provider_parse.call_args.kwargs
                self.assertEqual(kwargs["model"], "gpt-6-luna")
                self.assertEqual(kwargs["reasoning_effort"], expected_effort)
        self.assertEqual(LLMUsage.objects.count(), 2)

    def test_question_reasoning_can_be_lowered_via_environment(self):
        with patch.dict(os.environ, {"OPENAI_QUESTION_REASONING_EFFORT": "low"}):
            self.service.parse(
                user=self.user,
                operation="question_generation",
                model="gpt-6-luna",
                response_format=Reply,
                system_prompt="Extract the question.",
                user_prompt="1. What is osmosis?",
            )
        self.assertEqual(self.provider_parse.call_args.kwargs["reasoning_effort"], "low")

    def test_invalid_reasoning_does_not_reserve_usage_or_call_openai(self):
        for value in ("minimal", "", "turbo"):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"OPENAI_REFERENCE_REASONING_EFFORT": value}),
            ):
                with self.assertRaisesMessage(
                    LLMConfigurationError, "OPENAI_REFERENCE_REASONING_EFFORT"
                ):
                    self.make_request()
        self.provider_parse.assert_not_called()
        self.assertFalse(LLMUsage.objects.exists())

    @override_settings(
        GRAIDER_USER_DAILY_TOKENS=100,
        GRAIDER_USER_MONTHLY_TOKENS=200,
        GRAIDER_GLOBAL_MONTHLY_TOKENS=300,
    )
    def test_pending_reservation_blocks_another_request_then_releases_unused_tokens(self):
        first = reserve_usage(
            user=self.user, operation="answer_mapping", model="gpt-5.4-mini", estimated_tokens=80
        )
        with self.assertRaises(LLMQuotaExceeded):
            reserve_usage(
                user=self.user,
                operation="answer_mapping",
                model="gpt-5.4-mini",
                estimated_tokens=30,
            )
        self.assertEqual(LLMUsage.objects.count(), 1)

        finish_usage(
            first,
            status=LLMUsage.Status.SUCCEEDED,
            input_tokens=15,
            output_tokens=5,
            total_tokens=20,
        )
        second = reserve_usage(
            user=self.user, operation="answer_mapping", model="gpt-5.4-mini", estimated_tokens=70
        )
        self.assertEqual(second.status, LLMUsage.Status.PENDING)

    @override_settings(
        GRAIDER_USER_DAILY_TOKENS=500,
        GRAIDER_USER_MONTHLY_TOKENS=500,
        GRAIDER_GLOBAL_MONTHLY_TOKENS=100,
    )
    def test_global_budget_counts_pending_requests_from_other_users(self):
        other = User.objects.create_user(
            email="other@example.com", full_name="Other", password="StrongPass123!"
        )
        reserve_usage(
            user=self.user, operation="answer_mapping", model="gpt-5.4-mini", estimated_tokens=80
        )
        with self.assertRaisesMessage(LLMQuotaExceeded, "Graider's AI allowance"):
            reserve_usage(
                user=other, operation="answer_mapping", model="gpt-5.4-mini", estimated_tokens=30
            )

    @override_settings(
        GRAIDER_USER_DAILY_TOKENS=500,
        GRAIDER_USER_MONTHLY_TOKENS=100,
        GRAIDER_GLOBAL_MONTHLY_TOKENS=500,
    )
    def test_monthly_user_budget_counts_previous_completed_usage(self):
        first = reserve_usage(
            user=self.user, operation="answer_mapping", model="gpt-5.4-mini", estimated_tokens=80
        )
        finish_usage(
            first,
            status=LLMUsage.Status.SUCCEEDED,
            input_tokens=60,
            output_tokens=20,
            total_tokens=80,
        )
        with self.assertRaisesMessage(LLMQuotaExceeded, "monthly AI allowance"):
            reserve_usage(
                user=self.user,
                operation="answer_mapping",
                model="gpt-5.4-mini",
                estimated_tokens=30,
            )

    @override_settings(GRAIDER_USER_AI_REQUESTS_PER_MINUTE=1)
    def test_request_burst_limit_counts_completed_calls(self):
        first = reserve_usage(
            user=self.user, operation="answer_mapping", model="gpt-5.4-mini", estimated_tokens=50
        )
        finish_usage(
            first,
            status=LLMUsage.Status.SUCCEEDED,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )
        with self.assertRaisesMessage(LLMQuotaExceeded, "too quickly"):
            reserve_usage(
                user=self.user,
                operation="answer_mapping",
                model="gpt-5.4-mini",
                estimated_tokens=50,
            )

    def test_provider_spend_limit_error_releases_reservation_and_returns_safe_message(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        response = httpx.Response(429, request=request, headers={"x-request-id": "req_limit"})
        self.provider_parse.side_effect = RateLimitError(
            "Sensitive provider message",
            response=response,
            body={"code": "project_spend_limit_exceeded"},
        )

        with self.assertRaises(LLMSpendLimitError):
            self.make_request()
        row = LLMUsage.objects.get()
        self.assertEqual(row.status, LLMUsage.Status.FAILED)
        self.assertEqual(row.reserved_tokens, 0)
        self.assertEqual(row.provider_request_id, "req_limit")

    def test_timeout_keeps_reservation_when_provider_usage_is_uncertain(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        self.provider_parse.side_effect = APITimeoutError(request=request)
        with self.assertRaises(LLMGenerationError):
            self.make_request()
        row = LLMUsage.objects.get()
        self.assertEqual(row.status, LLMUsage.Status.UNCERTAIN)
        self.assertGreater(row.reserved_tokens, 0)

    def test_missing_provider_usage_keeps_conservative_reservation(self):
        result = completion()
        result.usage = None
        self.provider_parse.return_value = result
        self.make_request()
        row = LLMUsage.objects.get()
        self.assertEqual(row.status, LLMUsage.Status.UNMETERED)
        self.assertGreater(row.reserved_tokens, 0)

    def test_model_refusal_still_counts_reported_usage(self):
        result = completion()
        result.choices[0].message.refusal = "Sensitive provider refusal"
        result.choices[0].message.parsed = None
        self.provider_parse.return_value = result
        with self.assertRaises(LLMGenerationError):
            self.make_request()
        row = LLMUsage.objects.get()
        self.assertEqual(row.status, LLMUsage.Status.FAILED)
        self.assertEqual(row.total_tokens, 160)
        self.assertEqual(row.reserved_tokens, 0)

    @override_settings(GRAIDER_USER_DAILY_TOKENS=1)
    def test_over_quota_never_calls_openai(self):
        with self.assertRaises(LLMQuotaExceeded):
            self.make_request()
        self.provider_parse.assert_not_called()
        self.assertFalse(LLMUsage.objects.exists())


@skipUnless(connection.vendor == "postgresql", "Concurrent row locks require PostgreSQL.")
@override_settings(
    GRAIDER_USER_DAILY_TOKENS=500,
    GRAIDER_USER_MONTHLY_TOKENS=500,
    GRAIDER_GLOBAL_MONTHLY_TOKENS=1000,
    GRAIDER_USER_AI_REQUESTS_PER_MINUTE=40,
)
class ConcurrentQuotaTests(TransactionTestCase):
    def setUp(self):
        LLMQuotaLock.objects.get_or_create(pk=1)
        self.users = [
            User.objects.create_user(email=f"race-{index}@example.com", full_name="Teacher")
            for index in range(2)
        ]

    def reserve_simultaneously(self, users, estimated_tokens=51):
        start = Barrier(2)
        charged_tokens = usage_service._charged_tokens

        def slow_quota_read(queryset):
            total = charged_tokens(queryset)
            # Give the competing connection time to read the same allowance if the
            # row lock is removed. These remain real PostgreSQL queries.
            time.sleep(0.05)
            return total

        def request(user):
            try:
                start.wait(timeout=10)
                reserve_usage(
                    user=user,
                    operation="answer_mapping",
                    model="gpt-6-luna",
                    estimated_tokens=estimated_tokens,
                )
                return "reserved"
            except LLMQuotaExceeded:
                return "denied"
            finally:
                connections.close_all()

        with (
            patch.object(usage_service, "_charged_tokens", side_effect=slow_quota_read),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            futures = [pool.submit(request, user) for user in users]
            return sorted(future.result(timeout=10) for future in futures)

    @override_settings(GRAIDER_USER_DAILY_TOKENS=100)
    def test_simultaneous_requests_cannot_exceed_one_users_daily_budget(self):
        self.assertEqual(self.reserve_simultaneously([self.users[0]] * 2), ["denied", "reserved"])
        self.assertEqual(LLMUsage.objects.count(), 1)
        self.assertEqual(LLMUsage.objects.get().reserved_tokens, 51)

    @override_settings(GRAIDER_GLOBAL_MONTHLY_TOKENS=100)
    def test_different_users_cannot_exceed_global_budget_concurrently(self):
        self.assertEqual(self.reserve_simultaneously(self.users), ["denied", "reserved"])
        self.assertEqual(LLMUsage.objects.count(), 1)

    @override_settings(GRAIDER_USER_AI_REQUESTS_PER_MINUTE=1)
    def test_simultaneous_requests_cannot_bypass_burst_limit(self):
        self.assertEqual(self.reserve_simultaneously([self.users[0]] * 2), ["denied", "reserved"])
        self.assertEqual(LLMUsage.objects.count(), 1)

    @override_settings(GRAIDER_USER_DAILY_TOKENS=100, GRAIDER_GLOBAL_MONTHLY_TOKENS=100)
    def test_concurrent_reservations_can_reach_exact_budget_boundary(self):
        self.assertEqual(
            self.reserve_simultaneously([self.users[0]] * 2, estimated_tokens=50),
            ["reserved", "reserved"],
        )
        self.assertEqual(LLMUsage.objects.count(), 2)
        self.assertEqual(sum(LLMUsage.objects.values_list("reserved_tokens", flat=True)), 100)
