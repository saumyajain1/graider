import json
import os
import subprocess
import sys

from django.test import SimpleTestCase

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
        self.assertTrue(config["secure_session"])
        self.assertTrue(config["secure_csrf"])

    def test_sqlite_fallback_requires_explicit_debug(self):
        result = self.load_settings(DJANGO_DEBUG="true", DATABASE_URL="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["engine"], "django.db.backends.sqlite3"
        )

    def test_invalid_debug_value_fails(self):
        result = self.load_settings(DJANGO_DEBUG="perhaps")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_DEBUG", result.stderr)
