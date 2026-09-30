from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import User
from .throttles import IPScopedRateThrottle


class AuthApiTests(TestCase):
    def test_register_logs_user_in(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "teacher@example.com",
                "full_name": "Teacher Example",
                "password": "StrongPass123!",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.count(), 1)
        me_response = self.client.get(reverse("me"))
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["email"], "teacher@example.com")

    @override_settings(DEBUG=True)
    def test_register_allows_local_test_password_in_debug(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "tester@example.com",
                "full_name": "Tester Example",
                "password": "test1234",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().email, "tester@example.com")

    def test_login_returns_user_payload(self):
        User.objects.create_user(
            email="grader@example.com",
            full_name="Grader",
            password="StrongPass123!",
        )

        response = self.client.post(
            reverse("login"),
            {"email": "grader@example.com", "password": "StrongPass123!"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["full_name"], "Grader")

    def test_me_returns_401_when_logged_out(self):
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, 401)

    def test_me_sets_csrf_cookie_for_login_page_bootstrap(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse("me"))

        self.assertEqual(response.status_code, 401)
        self.assertIn("csrftoken", response.cookies)

    def test_logout_clears_session(self):
        user = User.objects.create_user(
            email="logout@example.com",
            full_name="Logout Example",
            password="StrongPass123!",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 204)
        me_response = self.client.get(reverse("me"))
        self.assertEqual(me_response.status_code, 401)


class AuthSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)

    def csrf_token(self):
        response = self.client.get(reverse("me"))
        return response.cookies["csrftoken"].value

    def test_anonymous_registration_and_login_require_csrf(self):
        registration = {
            "email": "teacher@example.com",
            "full_name": "Teacher",
            "password": "StrongPass123!",
        }
        self.assertEqual(
            self.client.post(reverse("register"), registration, content_type="application/json").status_code,
            403,
        )
        self.assertFalse(User.objects.exists())

        token = self.csrf_token()
        self.assertEqual(
            self.client.post(
                reverse("register"), registration, content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            ).status_code,
            201,
        )

        login_client = Client(enforce_csrf_checks=True)
        credentials = {"email": registration["email"], "password": registration["password"]}
        self.assertEqual(
            login_client.post(reverse("login"), credentials, content_type="application/json").status_code,
            403,
        )
        token = login_client.get(reverse("me")).cookies["csrftoken"].value
        self.assertEqual(
            login_client.post(
                reverse("login"), credentials, content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            ).status_code,
            200,
        )

    def test_cross_origin_registration_is_rejected_even_with_token(self):
        token = self.csrf_token()
        response = self.client.post(
            reverse("register"),
            {"email": "cross@example.com", "full_name": "Cross", "password": "StrongPass123!"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://attacker.example",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.exists())

    def test_logout_requires_csrf(self):
        user = User.objects.create_user(
            email="logout@example.com", full_name="Teacher", password="StrongPass123!"
        )
        self.client.force_login(user)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 403)
        self.assertEqual(self.client.get(reverse("me")).status_code, 200)

    def test_auth_routes_are_throttled_per_client_ip(self):
        rates = {"auth_login": "2/min", "auth_register": "1/hour", "auth_me": "2/min"}
        with patch.object(IPScopedRateThrottle, "THROTTLE_RATES", rates):
            client = Client(REMOTE_ADDR="192.0.2.1")
            for _ in range(2):
                self.assertEqual(
                    client.post(reverse("login"), {"email": "nobody@example.com", "password": "wrong"},
                                content_type="application/json").status_code,
                    400,
                )
            self.assertEqual(
                client.post(reverse("login"), {"email": "nobody@example.com", "password": "wrong"},
                            content_type="application/json").status_code,
                429,
            )
            self.assertEqual(
                Client(REMOTE_ADDR="192.0.2.2").post(
                    reverse("login"), {"email": "nobody@example.com", "password": "wrong"},
                    content_type="application/json",
                ).status_code,
                400,
            )
            self.assertEqual(client.post(reverse("register"), {}, content_type="application/json").status_code, 400)
            self.assertEqual(client.post(reverse("register"), {}, content_type="application/json").status_code, 429)
            self.assertEqual(client.get(reverse("me")).status_code, 401)
            self.assertEqual(client.get(reverse("me")).status_code, 401)
            self.assertEqual(client.get(reverse("me")).status_code, 429)

    @override_settings(DEBUG=False)
    def test_render_forwarded_client_ip_is_used_for_throttling(self):
        rates = {"auth_login": "1/min", "auth_register": "1/hour", "auth_me": "2/min"}
        with patch.object(IPScopedRateThrottle, "THROTTLE_RATES", rates):
            client = Client(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="192.0.2.10, 10.0.0.1")
            payload = {"email": "nobody@example.com", "password": "wrong"}
            self.assertEqual(client.post(reverse("login"), payload, content_type="application/json").status_code, 400)
            self.assertEqual(client.post(reverse("login"), payload, content_type="application/json").status_code, 429)

            other_client = Client(
                REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="192.0.2.11, 10.0.0.1"
            )
            self.assertEqual(
                other_client.post(reverse("login"), payload, content_type="application/json").status_code,
                400,
            )
