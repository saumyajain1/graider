from datetime import timedelta
from unittest.mock import patch

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import User
from .throttles import IPScopedRateThrottle


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", PASSWORD_RESET_ENABLED=True
)
class AccountManagementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="recover@example.com", full_name="Teacher", password="Current-Test-Password!23"
        )

    def post(self, route, payload):
        return self.client.post(reverse(route), payload, content_type="application/json")

    def reset_payload(self):
        return {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
            "new_password": "New-Test-Password!456",
            "confirm_password": "New-Test-Password!456",
        }

    def test_reset_request_is_generic_and_link_has_trusted_origin_and_fragment(self):
        with override_settings(FRONTEND_URL="https://graider.example"):
            found = self.post("password-reset", {"email": self.user.email.upper()})
            missing = self.post("password-reset", {"email": "missing@example.com"})
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json(), missing.json())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://graider.example/reset-password#", mail.outbox[0].body)
        self.assertNotIn("token", found.json())

    def test_reset_is_single_use_and_preserves_existing_data_and_invalidates_sessions(self):
        self.client.force_login(self.user)
        other = Client()
        other.force_login(self.user)
        payload = self.reset_payload()
        self.assertEqual(self.post("password-reset-confirm", payload).status_code, 200)
        self.assertEqual(self.post("password-reset-confirm", payload).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(payload["new_password"]))
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)
        self.assertEqual(other.get(reverse("me")).status_code, 401)
        self.assertEqual(User.objects.count(), 1)

    def test_invalid_expired_and_weak_password_reset_links(self):
        payload = self.reset_payload()
        for changes in (
            {"uid": "garbage"},
            {"token": "bad"},
            {"confirm_password": "different"},
            {"new_password": "password", "confirm_password": "password"},
        ):
            self.assertEqual(
                self.post("password-reset-confirm", {**payload, **changes}).status_code, 400
            )
        with patch.object(
            default_token_generator,
            "_now",
            return_value=default_token_generator._now() + timedelta(hours=2),
        ):
            self.assertEqual(self.post("password-reset-confirm", payload).status_code, 400)

    def test_google_only_account_can_set_password_through_verified_mailbox(self):
        self.user.set_unusable_password()
        self.user.save()
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="test-google",
            extra_data={"email": self.user.email},
        )
        self.assertEqual(self.post("password-reset", {"email": self.user.email}).status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.post("password-reset-confirm", self.reset_payload()).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.has_usable_password())
        self.assertEqual(self.user.socialaccount_set.count(), 1)

    def test_profile_name_change_and_password_change_keep_current_session_only(self):
        self.client.force_login(self.user)
        other = Client()
        other.force_login(self.user)
        response = self.client.patch(
            reverse("profile-update"),
            {"full_name": "Updated Teacher"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["full_name"], "Updated Teacher")
        payload = {
            "current_password": "Current-Test-Password!23",
            "new_password": "Changed-Test-Password!456",
            "confirm_password": "Changed-Test-Password!456",
        }
        self.assertEqual(
            self.post("password-change", {**payload, "current_password": "wrong"}).status_code, 400
        )
        self.assertEqual(self.post("password-change", payload).status_code, 200)
        self.assertEqual(self.client.get(reverse("me")).status_code, 200)
        self.assertEqual(other.get(reverse("me")).status_code, 401)

    def test_disconnect_requires_password_and_preserves_other_login(self):
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="test-google",
            extra_data={"email": self.user.email},
        )
        self.client.force_login(self.user)
        self.assertEqual(
            self.post(
                "account-disconnect", {"provider": "google", "current_password": "wrong"}
            ).status_code,
            400,
        )
        self.assertEqual(self.user.socialaccount_set.count(), 1)
        self.assertEqual(
            self.post(
                "account-disconnect",
                {"provider": "google", "current_password": "Current-Test-Password!23"},
            ).status_code,
            200,
        )
        self.assertEqual(self.user.socialaccount_set.count(), 0)
        self.assertEqual(self.client.get(reverse("me")).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.has_usable_password())

    def test_google_only_account_cannot_disconnect_last_login(self):
        self.user.set_unusable_password()
        self.user.save()
        SocialAccount.objects.create(user=self.user, provider="google", uid="test-google")
        self.client.force_login(self.user)
        self.assertEqual(
            self.post(
                "account-disconnect", {"provider": "google", "current_password": "anything"}
            ).status_code,
            400,
        )
        self.assertEqual(self.user.socialaccount_set.count(), 1)

    def test_new_account_endpoints_require_csrf_and_private_endpoints_require_login(self):
        secure = Client(enforce_csrf_checks=True)
        for name in (
            "password-reset",
            "password-reset-confirm",
            "password-change",
            "account-disconnect",
        ):
            self.assertEqual(
                secure.post(reverse(name), {}, content_type="application/json").status_code, 403
            )
        self.assertEqual(self.post("password-change", {}).status_code, 403)
        self.assertEqual(self.post("account-disconnect", {}).status_code, 403)
        self.assertEqual(
            self.client.patch(
                reverse("profile-update"), {"full_name": "X"}, content_type="application/json"
            ).status_code,
            403,
        )

    def test_password_recovery_is_rate_limited(self):
        with patch.object(IPScopedRateThrottle, "THROTTLE_RATES", {"auth_recovery": "1/hour"}):
            self.assertEqual(
                self.post("password-reset", {"email": "none@example.com"}).status_code, 200
            )
            self.assertEqual(
                self.post("password-reset", {"email": "none@example.com"}).status_code, 429
            )

    @override_settings(PASSWORD_RESET_ENABLED=False)
    def test_unconfigured_recovery_is_explicitly_unavailable(self):
        self.assertEqual(self.post("password-reset", {"email": self.user.email}).status_code, 503)

    @patch("apps.accounts.views.send_mail", side_effect=RuntimeError("sensitive provider data"))
    def test_delivery_failure_does_not_leak_provider_errors_or_account_existence(self, send):
        response = self.post("password-reset", {"email": self.user.email})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("sensitive", str(response.json()))


class EmailDeliveryTests(TestCase):
    @override_settings(BREVO_API_KEY="test-only-key")
    @patch("apps.accounts.email_backend.httpx.Client")
    def test_reset_mail_uses_https_and_verified_sender(self, client):
        from django.core.mail import EmailMessage

        from .email_backend import BrevoEmailBackend

        message = EmailMessage(
            "Reset password",
            "Test-only reset link",
            "Graider <sender@example.com>",
            ["recipient@example.com"],
        )
        backend = BrevoEmailBackend()
        self.assertEqual(backend.send_messages([message]), 1)
        call = client.return_value.__enter__.return_value.post.call_args
        self.assertEqual(call.args[0], "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(
            call.kwargs["json"]["sender"], {"name": "Graider", "email": "sender@example.com"}
        )
        self.assertEqual(call.kwargs["json"]["textContent"], "Test-only reset link")
        self.assertEqual(call.kwargs["headers"]["api-key"], "test-only-key")
        client.return_value.__enter__.return_value.post.return_value.raise_for_status.assert_called_once()
