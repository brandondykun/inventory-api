"""
Base settings shared across every environment.

Environment-specific modules (dev, test, e2e, staging, production) import
everything from here with ``from .base import *`` and override as needed.

All configuration is sourced from environment variables via django-environ so
the same image can run in any environment by swapping the ``.env`` file and
``DJANGO_SETTINGS_MODULE``.
"""

from datetime import timedelta
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# config/settings/base.py -> config/settings -> config -> <project root>
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
env = environ.Env()

# ENVIRONMENT is an informational label (dev/test/e2e/staging/production).
ENVIRONMENT = env("DJANGO_ENV", default="dev")

# ---------------------------------------------------------------------------
# Core security
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="insecure-change-me-in-real-environments")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    # django-unfold must come before django.contrib.admin.
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",  # required by allauth (SITE_ID below)
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "django_celery_beat",
    # allauth: identity/account layer. Owns accounts, email verification,
    # social providers, and account linking.
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.apple",
    # dj-rest-auth: used ONLY for the social-token login bridge (see
    # apps/authentication/views.py). Our custom JWT delivery stays the single
    # token mechanism for email/password login.
    "dj_rest_auth",
]

LOCAL_APPS = [
    "apps.common",
    "apps.users",
    "apps.authentication",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # allauth account middleware (required by allauth).
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="api"),
        "USER": env("POSTGRES_USER", default="api"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="api"),
        "HOST": env("POSTGRES_HOST", default="db"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
    }
}

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "users.User"

# Django ModelBackend (email/password) + allauth backend (social + account flows).
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# allauth uses the sites framework.
SITE_ID = env.int("SITE_ID", default=1)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.authentication.authentication.CookieOrHeaderJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": env.int("DRF_PAGE_SIZE", default=25),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="60/min"),
        "user": env("THROTTLE_USER", default="1000/min"),
        # Strict, dedicated buckets for unauthenticated abuse vectors
        # (credential stuffing on login, signup spam / enumeration on register).
        "login": env("THROTTLE_LOGIN", default="10/min"),
        "register": env("THROTTLE_REGISTER", default="10/min"),
    },
    # Number of trusted proxies in front of the app, so throttles key on the real
    # client IP (the Nth-from-last X-Forwarded-For entry) instead of the proxy's
    # IP — otherwise every client shares one bucket. 0 = no proxy (use
    # REMOTE_ADDR); production sits behind nginx and overrides this to 1.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
}

# ---------------------------------------------------------------------------
# Simple JWT
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_LIFETIME_MIN", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_LIFETIME_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Auth cookie configuration (web clients). Mobile clients receive tokens in the
# response body instead and ignore these.
AUTH_COOKIE_ACCESS = env("AUTH_COOKIE_ACCESS", default="access_token")
AUTH_COOKIE_REFRESH = env("AUTH_COOKIE_REFRESH", default="refresh_token")
AUTH_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=False)
AUTH_COOKIE_HTTP_ONLY = True
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", default="Lax")
AUTH_COOKIE_PATH = "/"
AUTH_COOKIE_DOMAIN = env("AUTH_COOKIE_DOMAIN", default=None)

# ---------------------------------------------------------------------------
# django-allauth (identity layer)
# ---------------------------------------------------------------------------
# Email-first: no username field; the email IS the identifier.
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_PREVENT_ENUMERATION = True

# "optional" by default so the base boots with zero email infrastructure;
# production overrides this to "mandatory". When "mandatory", unverified users
# are blocked from email/password login (enforced in LoginSerializer).
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="optional")

ACCOUNT_ADAPTER = "apps.users.adapters.CustomAccountAdapter"
SOCIALACCOUNT_ADAPTER = "apps.authentication.adapters.CustomSocialAccountAdapter"

# Trust the provider's verified email instead of re-emailing social sign-ups,
# and don't persist provider access/refresh tokens we don't use.
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_STORE_TOKENS = False

# Provider apps are configured here (12-factor) rather than via DB SocialApp
# rows, so client IDs/secrets come from the environment. Empty defaults keep the
# base runnable; sign-in for a provider only works once its creds are set.
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": env("GOOGLE_CLIENT_ID", default=""),
            "secret": env("GOOGLE_CLIENT_SECRET", default=""),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        # Trust Google-verified emails for account linking.
        "VERIFIED_EMAIL": True,
    },
    "apple": {
        # Apple's field mapping is non-obvious — see envs/.env.*.example + README:
        #   client_id  -> Services ID (web) or app Bundle ID (native)
        #   secret     -> Key ID of the .p8 sign-in key
        #   key        -> Apple Team ID
        #   certificate_key -> the full contents of the .p8 private key
        "APP": {
            "client_id": env("APPLE_CLIENT_ID", default=""),
            "secret": env("APPLE_KEY_ID", default=""),
            "key": env("APPLE_TEAM_ID", default=""),
            "settings": {
                "certificate_key": env("APPLE_PRIVATE_KEY", default=""),
            },
        },
    },
}

# Redirect URI used by the OAuth *code* flow. Native apps using the id_token
# flow don't need a real value ("postmessage" is Google's JS-client sentinel).
GOOGLE_CALLBACK_URL = env("GOOGLE_CALLBACK_URL", default="postmessage")
APPLE_CALLBACK_URL = env("APPLE_CALLBACK_URL", default="")

# dj-rest-auth: we use JWT and override the social view's response, so disable
# its DRF-authtoken model and session login entirely. TOKEN_MODEL=None avoids
# requiring rest_framework.authtoken in INSTALLED_APPS.
REST_AUTH = {
    "USE_JWT": True,
    "TOKEN_MODEL": None,
    "SESSION_LOGIN": False,
    "JWT_AUTH_HTTPONLY": True,
}

# ---------------------------------------------------------------------------
# Email (verification / password reset). Console backend by default so the base
# runs without SMTP; production points these at a real server via env.
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@example.com")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)

# ---------------------------------------------------------------------------
# drf-spectacular
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": env("API_TITLE", default="API"),
    "DESCRIPTION": env("API_DESCRIPTION", default="Generic DRF base application API"),
    "VERSION": env("API_VERSION", default="0.1.0"),
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
}

# Whether the interactive docs (swagger/redoc) URLs are mounted. Off by default;
# dev/staging turn it on. Production keeps it disabled.
ENABLE_API_DOCS = env.bool("ENABLE_API_DOCS", default=False)

# ---------------------------------------------------------------------------
# CORS (cookie auth for web requires explicit credentialed origins)
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# ---------------------------------------------------------------------------
# Cache (Redis)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", default="redis://redis:6379/2"),
    }
}

# ---------------------------------------------------------------------------
# Unfold admin theme
# ---------------------------------------------------------------------------
UNFOLD = {
    "SITE_TITLE": env("ADMIN_SITE_TITLE", default="API Admin"),
    "SITE_HEADER": env("ADMIN_SITE_HEADER", default="API Administration"),
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "COLORS": {
        "base": {
            "50": "#f9fafb",
            "100": "#f3f4f6",
            "200": "#e5e7eb",
            "300": "#d1d5db",
            "400": "#9ca3af",
            "500": "#6b7280",
            "600": "#4b5563",
            "700": "#374151",
            "800": "#1f2937",
            "900": "#111827",
            "950": "#030712",
        },
        "primary": {
            "50": "#f7fee7",
            "100": "#ecfccb",
            "200": "#d9f99d",
            "300": "#bef264",
            "400": "#a3e635",
            "500": "#84cc16",
            "600": "#65a30d",
            "700": "#4d7c0f",
            "800": "#3f6212",
            "900": "#365314",
            "950": "#1a2e05",
        },
    },
}

# ---------------------------------------------------------------------------
# Logging (structured, level driven by env)
# ---------------------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
