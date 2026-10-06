import os
import re
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env")


def _boolean_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be true or false.")


def _csv_env(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _positive_int_env(name, default):
    try:
        value = int(os.getenv(name, default))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise ImproperlyConfigured(f"{name} must be a positive integer.")
    return value


def _nonnegative_int_env(name, default):
    try:
        value = int(os.getenv(name, default))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a nonnegative integer.") from exc
    if value < 0:
        raise ImproperlyConfigured(f"{name} must be a nonnegative integer.")
    return value


def _throttle_rate_env(name, default):
    value = os.getenv(name, default)
    if not re.fullmatch(r"[1-9][0-9]*/(second|minute|hour|day|sec|min|hr|s|m|h|d)", value):
        raise ImproperlyConfigured(f"{name} must be a positive rate such as 10/min.")
    return value


DEBUG = _boolean_env("DJANGO_DEBUG")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set.")
if not DEBUG and (
    len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-")
):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong, unique value.")

ALLOWED_HOSTS = _csv_env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost" if DEBUG else "")
_render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if not DEBUG and _render_hostname and _render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_hostname)
if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list explicit hostnames in production.")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173" if DEBUG else "")

INSTALLED_APPS = [
    "config.apps.GraiderAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "apps.accounts",
    "apps.assignments",
    "apps.grading",
    "apps.ai_jobs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(DATABASE_URL, conn_max_age=60, conn_health_checks=True)
    }
elif DEBUG:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    raise ImproperlyConfigured("DATABASE_URL must be set in production.")

if not DEBUG and DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Production DATABASE_URL must use PostgreSQL.")

# Local SQLite serializes short job transactions; production uses PostgreSQL row locks.
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"].setdefault("OPTIONS", {})["transaction_mode"] = "IMMEDIATE"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("APP_TIME_ZONE", "America/Vancouver")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
STATICFILES_DIRS = [("frontend", FRONTEND_DIST_DIR)] if FRONTEND_DIST_DIR.is_dir() else []
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

GRAIDER_MAX_UPLOAD_BYTES = _positive_int_env("GRAIDER_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
GRAIDER_MAX_PDF_PAGES = _positive_int_env("GRAIDER_MAX_PDF_PAGES", 30)
GRAIDER_MAX_ASSIGNMENT_CHARS = _positive_int_env("GRAIDER_MAX_ASSIGNMENT_CHARS", 100_000)
GRAIDER_MAX_RESPONSE_CHARS = _positive_int_env("GRAIDER_MAX_RESPONSE_CHARS", 50_000)
GRAIDER_MAX_CSV_BYTES = _positive_int_env("GRAIDER_MAX_CSV_BYTES", 2 * 1024 * 1024)
GRAIDER_MAX_CSV_ROWS = _positive_int_env("GRAIDER_MAX_CSV_ROWS", 100)
GRAIDER_MAX_SUBMISSIONS_PER_ASSIGNMENT = _positive_int_env(
    "GRAIDER_MAX_SUBMISSIONS_PER_ASSIGNMENT", 100
)
GRAIDER_USER_DAILY_TOKENS = _positive_int_env("GRAIDER_USER_DAILY_TOKENS", 250_000)
GRAIDER_USER_MONTHLY_TOKENS = _positive_int_env("GRAIDER_USER_MONTHLY_TOKENS", 500_000)
GRAIDER_GLOBAL_MONTHLY_TOKENS = _positive_int_env("GRAIDER_GLOBAL_MONTHLY_TOKENS", 2_000_000)
GRAIDER_USER_AI_REQUESTS_PER_MINUTE = _positive_int_env("GRAIDER_USER_AI_REQUESTS_PER_MINUTE", 40)
GRAIDER_MAX_OUTPUT_TOKENS = _positive_int_env("GRAIDER_MAX_OUTPUT_TOKENS", 8_192)
# Disable admission and execution together for maintenance; no synchronous fallback.
GRAIDER_AI_JOBS_ENABLED = _boolean_env("GRAIDER_AI_JOBS_ENABLED", True)
GRAIDER_AI_CONCURRENCY = _positive_int_env("GRAIDER_AI_CONCURRENCY", 3)
GRAIDER_AI_STUDENT_CONCURRENCY = _positive_int_env(
    "GRAIDER_AI_STUDENT_CONCURRENCY", GRAIDER_AI_CONCURRENCY
)
GRAIDER_AI_LEASE_SECONDS = _positive_int_env("GRAIDER_AI_LEASE_SECONDS", 90)
GRAIDER_AI_HEARTBEAT_SECONDS = _positive_int_env("GRAIDER_AI_HEARTBEAT_SECONDS", 10)
GRAIDER_AI_SCAN_SECONDS = _positive_int_env("GRAIDER_AI_SCAN_SECONDS", 2)
GRAIDER_AI_FAIRNESS_SECONDS = _positive_int_env("GRAIDER_AI_FAIRNESS_SECONDS", 30)
GRAIDER_AI_SAFE_RETRIES = _nonnegative_int_env("GRAIDER_AI_SAFE_RETRIES", 2)
GRAIDER_AI_RETRY_SECONDS = _positive_int_env("GRAIDER_AI_RETRY_SECONDS", 10)
GRAIDER_AI_DRAIN_SECONDS = _positive_int_env("GRAIDER_AI_DRAIN_SECONDS", 20)
GRAIDER_AI_WAKE_SOCKET = os.getenv("GRAIDER_AI_WAKE_SOCKET", "/tmp/graider-ai-worker.sock")
GRAIDER_AI_USER_QUEUE_LIMIT = _positive_int_env("GRAIDER_AI_USER_QUEUE_LIMIT", 20)
GRAIDER_AI_GLOBAL_QUEUE_LIMIT = _positive_int_env("GRAIDER_AI_GLOBAL_QUEUE_LIMIT", 50)
GRAIDER_AI_MAX_BATCH_SUBMISSIONS = _positive_int_env("GRAIDER_AI_MAX_BATCH_SUBMISSIONS", 10)
GRAIDER_AI_MAX_GRADING_QUESTIONS = _positive_int_env("GRAIDER_AI_MAX_GRADING_QUESTIONS", 10)

if GRAIDER_AI_LEASE_SECONDS <= GRAIDER_AI_HEARTBEAT_SECONDS * 3:
    raise ImproperlyConfigured("GRAIDER_AI_LEASE_SECONDS must exceed three heartbeat intervals.")

DATA_UPLOAD_MAX_MEMORY_SIZE = GRAIDER_MAX_UPLOAD_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

_storage_endpoint = os.getenv("AWS_ENDPOINT_URL_S3", "")
_storage_access_key = os.getenv("AWS_ACCESS_KEY_ID", "")
_storage_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")
_storage_configured = any((_storage_endpoint, _storage_access_key, _storage_secret_key))
if _storage_configured and not all((_storage_endpoint, _storage_access_key, _storage_secret_key)):
    raise ImproperlyConfigured(
        "AWS_ENDPOINT_URL_S3, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY must be set together."
    )
if not DEBUG and not _storage_configured:
    raise ImproperlyConfigured("Neon Object Storage credentials are required in production.")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
if _storage_configured:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": _storage_access_key,
            "secret_key": _storage_secret_key,
            "bucket_name": os.getenv("NEON_STORAGE_BUCKET", "uploads"),
            "endpoint_url": _storage_endpoint,
            "region_name": os.getenv("AWS_REGION", "us-east-2"),
            "addressing_style": "path",
            "signature_version": "s3v4",
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 60,
            "file_overwrite": False,
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# Password recovery: HTTPS email works on Render's free service; local links print to the terminal.
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
DEFAULT_FROM_EMAIL = os.getenv("GRAIDER_FROM_EMAIL", "").strip() or "Graider <noreply@localhost>"
if BREVO_API_KEY and DEFAULT_FROM_EMAIL == "Graider <noreply@localhost>":
    raise ImproperlyConfigured("Set GRAIDER_FROM_EMAIL to your verified Brevo sender.")
EMAIL_BACKEND = (
    "apps.accounts.email_backend.BrevoEmailBackend"
    if BREVO_API_KEY
    else "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.dummy.EmailBackend"
)
PASSWORD_RESET_ENABLED = DEBUG or bool(BREVO_API_KEY)
PASSWORD_RESET_TIMEOUT = 3600

# Password endpoints retain their existing validation, throttling, and sessions.
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_ADAPTER = "apps.accounts.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_REQUESTS_TIMEOUT = 15

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
if bool(GOOGLE_CLIENT_ID) != bool(GOOGLE_CLIENT_SECRET):
    raise ImproperlyConfigured("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set together.")
GOOGLE_LOGIN_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {"client_id": GOOGLE_CLIENT_ID, "secret": GOOGLE_CLIENT_SECRET, "key": ""},
        "SCOPE": ["openid", "email", "profile"],
        "AUTH_PARAMS": {"access_type": "online", "prompt": "select_account"},
        "OAUTH_PKCE_ENABLED": True,
    }
}

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": _throttle_rate_env("GRAIDER_LOGIN_RATE", "10/min"),
        "auth_register": _throttle_rate_env("GRAIDER_REGISTER_RATE", "5/hour"),
        "auth_me": _throttle_rate_env("GRAIDER_AUTH_CHECK_RATE", "120/min"),
        "auth_recovery": _throttle_rate_env("GRAIDER_PASSWORD_RESET_RATE", "5/hour"),
        "auth_account": _throttle_rate_env("GRAIDER_ACCOUNT_RATE", "10/min"),
        "auth_google": _throttle_rate_env("GRAIDER_GOOGLE_RATE", "10/min"),
    },
}

CORS_ALLOWED_ORIGINS = _csv_env("DJANGO_CORS_ALLOWED_ORIGINS", FRONTEND_URL)
CSRF_TRUSTED_ORIGINS = _csv_env("DJANGO_CSRF_TRUSTED_ORIGINS", FRONTEND_URL)
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # React reads this cookie and sends X-CSRFToken.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Render terminates HTTPS at its proxy and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if not DEBUG else None
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG

SPECTACULAR_SETTINGS = {
    "TITLE": "Graider API",
    "VERSION": "1.0.0",
    "DESCRIPTION": (
        "Sign in at /login, then use your browser session in Try it out. "
        "Write requests require CSRF protection, including login and registration. "
        "Files and assignment data are restricted to their teacher. "
        "AI operations enforce the configured token quotas and grading limits."
    ),
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "SWAGGER_UI_SETTINGS": {"deepLinking": True, "displayRequestDuration": True},
}


# Numeric AI timing/resource events are opt-in and omit all user content.
GRAIDER_AI_METRICS = _boolean_env("GRAIDER_AI_METRICS", False)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"ai_metrics_console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "graider.ai_metrics": {
            "handlers": ["ai_metrics_console"],
            "level": "INFO",
            "propagate": False,
        }
    },
}
