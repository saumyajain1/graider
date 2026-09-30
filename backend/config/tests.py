import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import Client, SimpleTestCase, TestCase, override_settings

from .settings import BASE_DIR


class ProductionSettingsTests(SimpleTestCase):
    def load_settings(self, **overrides):
        env = os.environ.copy()
        env.update(
            DJANGO_DEBUG="false",
            DJANGO_SECRET_KEY="test-secret-" + "a1B2c3D4e5" * 5,
            DJANGO_ALLOWED_HOSTS="graider.onrender.com",
            DATABASE_URL="postgresql://user:password@db.example:5432/graider?sslmode=require",
            FRONTEND_URL="",
            DJANGO_CORS_ALLOWED_ORIGINS="",
            DJANGO_CSRF_TRUSTED_ORIGINS="",
            AWS_ENDPOINT_URL_S3="https://storage.example.invalid",
            AWS_ACCESS_KEY_ID="test-access-key",
            AWS_SECRET_ACCESS_KEY="test-secret-key",
        )
        env.update(overrides)
        code = (
            "import json; from config import settings; "
            "print(json.dumps({"
            "'debug': settings.DEBUG, "
            "'hosts': settings.ALLOWED_HOSTS, "
            "'engine': settings.DATABASES['default']['ENGINE'], "
            "'sslmode': settings.DATABASES['default'].get('OPTIONS', {}).get('sslmode'), "
            "'cors': settings.CORS_ALLOWED_ORIGINS, "
            "'csrf': settings.CSRF_TRUSTED_ORIGINS, "
            "'ssl_redirect': settings.SECURE_SSL_REDIRECT, "
            "'hsts_seconds': settings.SECURE_HSTS_SECONDS, "
            "'referrer_policy': settings.SECURE_REFERRER_POLICY, "
            "'nosniff': settings.SECURE_CONTENT_TYPE_NOSNIFF, "
            "'frame_options': settings.X_FRAME_OPTIONS, "
            "'secure_session': settings.SESSION_COOKIE_SECURE, "
            "'secure_csrf': settings.CSRF_COOKIE_SECURE"
            "}))"
        )
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_production_requires_secret_hosts_and_database_url(self):
        for key, value in (
            ("DJANGO_SECRET_KEY", ""),
            ("DJANGO_SECRET_KEY", "replace-with-a-long-random-local-secret"),
            ("DJANGO_SECRET_KEY", "a" * 60),
            ("DJANGO_ALLOWED_HOSTS", ""),
            ("DJANGO_ALLOWED_HOSTS", "*"),
            ("DATABASE_URL", ""),
            ("DATABASE_URL", "sqlite:///local.sqlite3"),
        ):
            with self.subTest(key=key, value=value):
                result = self.load_settings(**{key: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key, result.stderr)

    def test_production_postgres_and_https_configuration(self):
        result = self.load_settings(
            DJANGO_ALLOWED_HOSTS="graider.onrender.com,example.com",
            DJANGO_CORS_ALLOWED_ORIGINS="https://example.com",
            DJANGO_CSRF_TRUSTED_ORIGINS="https://example.com",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertFalse(config["debug"])
        self.assertEqual(config["hosts"], ["graider.onrender.com", "example.com"])
        self.assertEqual(config["engine"], "django.db.backends.postgresql")
        self.assertEqual(config["sslmode"], "require")
        self.assertEqual(config["cors"], ["https://example.com"])
        self.assertEqual(config["csrf"], ["https://example.com"])
        self.assertTrue(config["ssl_redirect"])
        self.assertEqual(config["hsts_seconds"], 3600)
        self.assertEqual(config["referrer_policy"], "same-origin")
        self.assertTrue(config["nosniff"])
        self.assertEqual(config["frame_options"], "DENY")
        self.assertTrue(config["secure_session"])
        self.assertTrue(config["secure_csrf"])

    def test_sqlite_fallback_requires_explicit_debug(self):
        result = self.load_settings(DJANGO_DEBUG="true", DATABASE_URL="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["engine"], "django.db.backends.sqlite3")

    def test_invalid_debug_value_fails(self):
        result = self.load_settings(DJANGO_DEBUG="perhaps")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_DEBUG", result.stderr)

    def test_invalid_auth_throttle_rate_fails_closed(self):
        result = self.load_settings(GRAIDER_LOGIN_RATE="not-a-rate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GRAIDER_LOGIN_RATE", result.stderr)

    @override_settings(
        DEBUG=False,
        SECURE_SSL_REDIRECT=True,
        SECURE_HSTS_SECONDS=3600,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_production_redirect_and_security_headers(self):
        redirect = self.client.get("/health/", HTTP_HOST="localhost")
        self.assertEqual(redirect.status_code, 301)
        self.assertEqual(redirect["Location"], "https://localhost/health/")

        response = self.client.get(
            "/health/", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Strict-Transport-Security"], "max-age=3600")
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["X-Frame-Options"], "DENY")


class FrontendRouteTests(SimpleTestCase):
    def test_spa_routes_use_built_index_without_swallowing_reserved_paths(self):
        with TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text("<title>Graider test build</title>")
            with override_settings(FRONTEND_DIST_DIR=Path(directory)):
                for route in ("/", "/login", "/assignments/12/questions"):
                    response = self.client.get(route, HTTP_HOST="localhost")
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(b"Graider test build", b"".join(response.streaming_content))
                    self.assertEqual(response["Cache-Control"], "no-store")

                for route in ("/api/missing", "/static/missing.js", "/favicon.ico"):
                    self.assertEqual(self.client.get(route, HTTP_HOST="localhost").status_code, 404)

                health = self.client.get("/health/", HTTP_HOST="localhost")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json(), {"status": "ok"})

    def test_spa_returns_404_until_frontend_is_built(self):
        with TemporaryDirectory() as directory:
            with override_settings(FRONTEND_DIST_DIR=Path(directory)):
                self.assertEqual(self.client.get("/", HTTP_HOST="localhost").status_code, 404)


class SameOriginAuthTests(TestCase):
    @override_settings(
        DEBUG=False,
        SECURE_SSL_REDIRECT=False,
        CSRF_COOKIE_SECURE=True,
        SESSION_COOKIE_SECURE=True,
    )
    def test_built_page_and_api_share_session_and_csrf_cookie(self):
        with TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text("<title>Graider test build</title>")
            with override_settings(FRONTEND_DIST_DIR=Path(directory)):
                client = Client(enforce_csrf_checks=True, HTTP_HOST="localhost")
                self.assertEqual(client.get("/", secure=True).status_code, 200)
                initial = client.get("/api/auth/me", secure=True)
                self.assertEqual(initial.status_code, 401)
                csrf_token = initial.cookies["csrftoken"].value
                self.assertTrue(initial.cookies["csrftoken"]["secure"])

                registered = client.post(
                    "/api/auth/register",
                    json.dumps(
                        {
                            "email": "same-origin@example.com",
                            "full_name": "Same Origin",
                            "password": "StrongPass123!",
                        }
                    ),
                    content_type="application/json",
                    HTTP_X_CSRFTOKEN=csrf_token,
                    HTTP_ORIGIN="https://localhost",
                    secure=True,
                )
                self.assertEqual(registered.status_code, 201, registered.content)
                self.assertIn("sessionid", registered.cookies)
                self.assertTrue(registered.cookies["sessionid"]["secure"])
                self.assertEqual(
                    client.get("/api/auth/me", secure=True).json()["email"],
                    "same-origin@example.com",
                )
