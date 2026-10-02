import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import jwt
import requests
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialToken
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.assignments.models import Assignment

from .models import User
from .throttles import IPScopedRateThrottle

PROVIDERS = {
    "google": {
        "APP": {"client_id": "google-test-client", "secret": "google-test-secret", "key": ""},
        "SCOPE": ["openid", "email", "profile"],
        "AUTH_PARAMS": {"access_type": "online", "prompt": "select_account"},
        "OAUTH_PKCE_ENABLED": True,
    }
}


@override_settings(GOOGLE_LOGIN_ENABLED=True, SOCIALACCOUNT_PROVIDERS=PROVIDERS, FRONTEND_URL="")
class GoogleAuthTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Google test certificate")])
        now = datetime.now(timezone.utc)
        cls.certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(cls.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .sign(cls.key, hashes.SHA256())
            .public_bytes(serialization.Encoding.PEM)
            .decode()
        )

    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.token = None
        self.requests = []
        self.mock_http = patch(
            "requests.sessions.Session.request", side_effect=self.provider_request
        )
        self.mock_http.start()
        self.addCleanup(self.mock_http.stop)

    def provider_request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        if url == "https://oauth2.googleapis.com/token":
            data = {"access_token": "not-a-real-token", "token_type": "Bearer"}
            if self.token:
                data["id_token"] = self.token
        elif url == "https://www.googleapis.com/oauth2/v1/certs":
            data = {"test-key": self.certificate}
        else:
            raise AssertionError(f"Unexpected provider endpoint: {url}")
        response = requests.Response()
        response.status_code = 200
        response.headers["content-type"] = "application/json"
        response._content = json.dumps(data).encode()
        return response

    def start(self, process="login", **extra):
        csrf = self.client.get(reverse("auth-options")).cookies["csrftoken"].value
        response = self.client.post(
            reverse("google-start"),
            {"process": process, **extra},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 200, response.content)
        return parse_qs(urlsplit(response.json()["redirect_url"]).query)

    def callback(self, params, **claims):
        now = datetime.now(timezone.utc).timestamp()
        payload = {
            "iss": "https://accounts.google.com",
            "aud": "google-test-client",
            "iat": int(now),
            "exp": int(now + 300),
            "nonce": params["nonce"][0],
            "sub": "google-subject-123",
            "email": "google@example.com",
            "email_verified": True,
            "name": "Google Teacher",
            **claims,
        }
        self.token = jwt.encode(payload, self.key, algorithm="RS256", headers={"kid": "test-key"})
        return self.client.get(
            reverse("google_callback"), {"state": params["state"][0], "code": "test-code"}
        )

    def test_first_google_login_registers_user_and_repeat_login_preserves_identity(self):
        params = self.start()
        response = self.callback(params)
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        user = User.objects.get()
        self.assertEqual(user.full_name, "Google Teacher")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(self.client.get(reverse("me")).json()["id"], user.pk)
        self.assertTrue(EmailAddress.objects.get(user=user).verified)
        self.assertFalse(SocialToken.objects.exists())
        assignment = Assignment.objects.create(teacher=user, title="Existing grading")
        self.client.post(reverse("logout"), HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        response = self.callback(self.start(), email="changed@example.com")
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.client.get(reverse("me")).json()["id"], user.pk)
        self.assertEqual(self.client.get(f"/api/assignments/{assignment.pk}").status_code, 200)

    def test_google_start_uses_minimal_scopes_state_nonce_and_pkce(self):
        params = self.start(next="https://attacker.example", scope="https://mail.google.com/")
        self.assertEqual(set(params["scope"][0].split()), {"openid", "email", "profile"})
        self.assertEqual(params["access_type"], ["online"])
        self.assertEqual(params["prompt"], ["select_account"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(
            params["redirect_uri"], ["http://testserver/accounts/google/login/callback/"]
        )
        self.callback(params)
        exchange = self.requests[0][2]["data"]
        verifier = exchange["code_verifier"]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        self.assertEqual(challenge, params["code_challenge"][0])

    def test_development_callback_preserves_vite_origin_and_session(self):
        csrf = (
            self.client.get(reverse("auth-options"), HTTP_HOST="localhost:5173")
            .cookies["csrftoken"]
            .value
        )
        response = self.client.post(
            reverse("google-start"),
            {"process": "login"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_HOST="localhost:5173",
            HTTP_ORIGIN="http://localhost:5173",
        )
        params = parse_qs(urlsplit(response.json()["redirect_url"]).query)
        self.assertEqual(
            params["redirect_uri"], ["http://localhost:5173/accounts/google/login/callback/"]
        )

    def test_existing_email_never_automatically_links_or_logs_in(self):
        existing = User.objects.create_user(email="Google@example.com", password="Password123!")
        response = self.callback(self.start())
        self.assertRedirects(
            response, "/login?auth=existing_account", fetch_redirect_response=False
        )
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(SocialAccount.objects.filter(user=existing).exists())
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)

    def test_explicit_connection_preserves_profile_and_assignments(self):
        user = User.objects.create_user(
            email="local@example.com", full_name="Local Teacher", password="Password123!"
        )
        assignment = Assignment.objects.create(teacher=user, title="My assignment")
        other = User.objects.create_user(email="other@example.com")
        foreign = Assignment.objects.create(teacher=other, title="Private")
        self.client.force_login(user)
        response = self.callback(self.start("connect"))
        self.assertRedirects(response, "/profile?auth=connected", fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertEqual(user.email, "local@example.com")
        self.assertEqual(user.full_name, "Local Teacher")
        profile = self.client.get(reverse("me")).json()
        self.assertEqual(
            profile["connected_accounts"], [{"provider": "google", "email": "google@example.com"}]
        )
        self.assertEqual(self.client.get(f"/api/assignments/{assignment.pk}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/assignments/{foreign.pk}").status_code, 404)
        self.client.post(reverse("logout"), HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        self.callback(self.start())
        self.assertEqual(self.client.get(reverse("me")).json()["id"], user.pk)

    def test_cannot_connect_another_users_google_account(self):
        owner = User.objects.create_user(email="owner@example.com")
        SocialAccount.objects.create(user=owner, provider="google", uid="google-subject-123")
        user = User.objects.create_user(email="local@example.com")
        self.client.force_login(user)
        response = self.callback(self.start("connect"))
        self.assertRedirects(
            response, "/profile?auth=already_connected", fetch_redirect_response=False
        )
        self.assertEqual(SocialAccount.objects.get().user_id, owner.pk)
        self.assertEqual(self.client.get(reverse("me")).json()["id"], user.pk)

    def test_linking_requires_same_authenticated_user_at_callback(self):
        user = User.objects.create_user(email="local@example.com")
        other = User.objects.create_user(email="other@example.com")
        self.client.force_login(user)
        params = self.start("connect")
        session = self.client.session
        session["_auth_user_id"] = str(other.pk)
        session.save()
        response = self.callback(params)
        self.assertRedirects(response, "/login?auth=session_changed", fetch_redirect_response=False)
        self.assertFalse(SocialAccount.objects.exists())
        self.assertEqual(self.requests, [])

    def test_connect_requires_login_and_start_requires_csrf(self):
        response = self.client.post(
            reverse("google-start"), {"process": "login"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)
        csrf = self.client.get(reverse("auth-options")).cookies["csrftoken"].value
        response = self.client.post(
            reverse("google-start"),
            {"process": "connect"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.requests, [])

    def test_invalid_expired_or_replayed_state_never_contacts_google(self):
        response = self.client.get(reverse("google_callback"), {"state": "invalid", "code": "test"})
        self.assertRedirects(response, "/login?auth=failed", fetch_redirect_response=False)
        params = self.start()
        session = self.client.session
        session["socialaccount_states"][params["state"][0]][1] = 0
        session.save()
        self.callback(params)
        self.assertEqual(self.requests, [])
        params = self.start()
        self.callback(params)
        self.requests.clear()
        response = self.callback(params)
        self.assertRedirects(response, "/login?auth=failed", fetch_redirect_response=False)
        self.assertEqual(self.requests, [])

    def test_invalid_identity_claims_cannot_create_accounts(self):
        for claims in (
            {"nonce": "wrong"},
            {"nonce": None},
            {"aud": "other-client"},
            {"iss": "https://attacker.example"},
            {"exp": 1},
            {"sub": ""},
            {"email_verified": False},
            {"email_verified": "true"},
        ):
            with self.subTest(claims=claims):
                response = self.callback(self.start(), **claims)
                self.assertRedirects(response, "/login?auth=failed", fetch_redirect_response=False)
                self.assertFalse(User.objects.exists())

    def test_invalid_signature_and_missing_id_token_are_rejected(self):
        params = self.start()
        self.token = jwt.encode({"sub": "attacker"}, "untrusted-test-key-" * 3, algorithm="HS256")
        response = self.client.get(
            reverse("google_callback"), {"state": params["state"][0], "code": "test"}
        )
        self.assertRedirects(response, "/login?auth=failed", fetch_redirect_response=False)
        params = self.start()
        self.token = None
        response = self.client.get(
            reverse("google_callback"), {"state": params["state"][0], "code": "test"}
        )
        self.assertRedirects(response, "/login?auth=failed", fetch_redirect_response=False)
        self.assertFalse(User.objects.exists())

    def test_forged_rsa_signature_is_rejected(self):
        params = self.start()
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.token = jwt.encode(
            {"sub": "attacker", "nonce": params["nonce"][0]},
            other_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )
        response = self.client.get(
            reverse("google_callback"), {"state": params["state"][0], "code": "test"}
        )
        self.assertRedirects(response, "/login?auth=failed", fetch_redirect_response=False)
        self.assertFalse(User.objects.exists())

    def test_provider_outage_does_not_expose_errors_or_create_user(self):
        params = self.start()
        with patch(
            "requests.sessions.Session.request",
            side_effect=requests.ConnectionError("private diagnostic"),
        ):
            response = self.client.get(
                reverse("google_callback"), {"state": params["state"][0], "code": "test"}
            )
        self.assertRedirects(response, "/login?auth=failed", fetch_redirect_response=False)
        self.assertFalse(User.objects.exists())

    def test_inactive_google_user_cannot_sign_in(self):
        user = User.objects.create_user(email="google@example.com", is_active=False)
        SocialAccount.objects.create(user=user, provider="google", uid="google-subject-123")
        response = self.callback(self.start())
        self.assertRedirects(response, "/login?auth=unavailable", fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)

    def test_connection_does_not_replace_a_different_connected_account(self):
        user = User.objects.create_user(email="local@example.com")
        SocialAccount.objects.create(user=user, provider="google", uid="existing-subject")
        self.client.force_login(user)
        response = self.callback(self.start("connect"))
        self.assertRedirects(
            response, "/profile?auth=different_google", fetch_redirect_response=False
        )
        self.assertEqual(SocialAccount.objects.get().uid, "existing-subject")

    def test_cross_origin_start_is_rejected_even_with_csrf(self):
        csrf = self.client.get(reverse("auth-options")).cookies["csrftoken"].value
        response = self.client.post(
            reverse("google-start"),
            {"process": "login"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_ORIGIN="https://attacker.example",
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("socialaccount_states", self.client.session)

    def test_local_registration_still_works_after_google_signup(self):
        self.callback(self.start())
        csrf = self.client.cookies["csrftoken"].value
        self.client.post(reverse("logout"), HTTP_X_CSRFTOKEN=csrf)
        csrf = self.client.get(reverse("auth-options")).cookies["csrftoken"].value
        response = self.client.post(
            reverse("register"),
            {
                "email": "password@example.com",
                "full_name": "Password Teacher",
                "password": "LocalPassword123!",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["connected_accounts"], [])
        self.assertEqual(User.objects.count(), 2)

    def test_cancellation_and_provider_errors_are_safe(self):
        for error, expected in (
            ("access_denied", "cancelled"),
            ("secret-provider-error", "failed"),
        ):
            params = self.start()
            response = self.client.get(
                reverse("google_callback"),
                {
                    "state": params["state"][0],
                    "error": error,
                    "error_description": "sensitive diagnostic",
                },
            )
            self.assertRedirects(response, f"/login?auth={expected}", fetch_redirect_response=False)
            self.assertNotIn("sensitive", response.url)
        self.assertEqual(self.requests, [])

    def test_google_start_is_rate_limited(self):
        with patch.object(IPScopedRateThrottle, "THROTTLE_RATES", {"auth_google": "1/min"}):
            self.start()
            csrf = self.client.cookies["csrftoken"].value
            response = self.client.post(
                reverse("google-start"),
                {"process": "login"},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf,
            )
            self.assertEqual(response.status_code, 429)

    def test_google_registration_uses_existing_registration_limit(self):
        rates = {"auth_google": "10/min", "auth_register": "1/hour"}
        with patch.object(IPScopedRateThrottle, "THROTTLE_RATES", rates):
            self.callback(self.start())
            self.client.post(
                reverse("logout"), HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value
            )
            response = self.callback(self.start(), sub="second-subject", email="second@example.com")
            self.assertRedirects(
                response, "/login?auth=rate_limited", fetch_redirect_response=False
            )
            self.assertEqual(User.objects.count(), 1)
            self.assertEqual(SocialAccount.objects.count(), 1)

    @override_settings(GOOGLE_LOGIN_ENABLED=False)
    def test_unconfigured_google_is_disabled_without_exposing_credentials(self):
        options = self.client.get(reverse("auth-options"))
        self.assertEqual(options.json(), {"google_enabled": False})
        response = self.client.post(
            reverse("google-start"),
            {"process": "login"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=options.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 503)
        response = self.client.get(reverse("google_callback"))
        self.assertRedirects(response, "/login?auth=unavailable", fetch_redirect_response=False)

    @override_settings(
        DEBUG=False,
        SECURE_SSL_REDIRECT=False,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_production_callback_uses_external_https_origin(self):
        csrf = self.client.get(reverse("auth-options")).cookies["csrftoken"].value
        response = self.client.post(
            reverse("google-start"),
            {"process": "login"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_HOST="testserver",
            HTTP_ORIGIN="https://testserver",
        )
        self.assertEqual(response.status_code, 200, response.content)
        params = parse_qs(urlsplit(response.json()["redirect_url"]).query)
        self.assertEqual(
            params["redirect_uri"], ["https://testserver/accounts/google/login/callback/"]
        )
