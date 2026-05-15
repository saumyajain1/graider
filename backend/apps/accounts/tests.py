from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import User


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
