"""Django settings for TrustVault."""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_list(name, default=""):
    """Read a comma-separated environment variable into a clean list."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("Set SECRET_KEY in the environment or .env file.")
if not DEBUG and (len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure")):
    raise ImproperlyConfigured("Use a long random SECRET_KEY when DEBUG is off.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# PostgreSQL only. The append-only audit protections and the row locks in the
# plan need it, and a silent SQLite fallback would hide production problems.
database_url = os.getenv("DATABASE_URL", "")
if not database_url.startswith(("postgres://", "postgresql://")):
    raise ImproperlyConfigured(
        "Set DATABASE_URL to a PostgreSQL URL (postgres://user:pass@host:5432/db)."
    )
DATABASES = {"default": dj_database_url.parse(database_url, conn_max_age=0)}

# The public Django admin app is not installed at all (not just unmounted).
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "vault.apps.VaultConfig",
]

AUTH_USER_MODEL = "vault.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "vault.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "vault.middleware.UploadRequestSizeLimitMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

FILE_UPLOAD_HANDLERS = [
    "vault.upload_handlers.UploadSizeLimitHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
DATA_UPLOAD_MAX_MEMORY_SIZE = 1_000_000

ROOT_URLCONF = "trustvault.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "trustvault.wsgi.application"
ASGI_APPLICATION = "trustvault.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Sessions: stored on the server, so deleting a session row revokes access.
# Identity only; document permissions are never kept in the session.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60  # 1 hour idle timeout
SESSION_SAVE_EVERY_REQUEST = True  # renew the timer on each request
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG

# --- CSRF
# HttpOnly means scripts cannot read the cookie; take the token from the page.
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG

# --- HTTPS and headers
# Trust X-Forwarded-Proto only because the host's proxy sets it and overwrites
# any value a client sends. Confirm this in your host's documentation.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG
SECURE_REDIRECT_EXEMPT = [r"^health/$"]  # lets host health checks use plain HTTP
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Start short. Raise to a year only after HTTPS is confirmed to work everywhere.
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False

# Add these lines at the bottom of trustvault/settings.py

# --- Day 2: login and the authorisation gate
# Never wrap whole requests in a transaction: the gate must commit its audit row
# before it raises the 404, and a request-wide transaction would roll that row back.
DATABASES["default"]["ATOMIC_REQUESTS"] = False
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "document_list"
LOGOUT_REDIRECT_URL = "login"


# --- Day 5: tamper-evident audit chain ---
# Keep this key outside the database and source control.
AUDIT_HMAC_KEY = os.getenv("AUDIT_HMAC_KEY", "")

if not AUDIT_HMAC_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "Set AUDIT_HMAC_KEY (a long random value kept outside the database)."
        )
    AUDIT_HMAC_KEY = "dev-only-audit-key-not-a-secret"
elif not DEBUG and len(AUDIT_HMAC_KEY) < 32:
    raise ImproperlyConfigured(
        "AUDIT_HMAC_KEY must be at least 32 characters when DEBUG is off."
    )
