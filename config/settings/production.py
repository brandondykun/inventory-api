"""
Production settings: hardened, served behind nginx + gunicorn.

Secrets have NO defaults here — a missing SECRET_KEY/JWT key/DB password fails
loudly at startup rather than silently running insecure.
"""

from .base import *  # noqa: F403

DEBUG = False
ENVIRONMENT = "production"

# Required — raises ImproperlyConfigured if absent.
SECRET_KEY = env("SECRET_KEY")  # noqa: F405
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # noqa: F405

# Interactive docs are disabled in production.
ENABLE_API_DOCS = env.bool("ENABLE_API_DOCS", default=False)  # noqa: F405

# --- TLS / proxy -----------------------------------------------------------
# nginx terminates TLS and forwards X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405

# --- HSTS ------------------------------------------------------------------
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# --- Cookies ---------------------------------------------------------------
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
AUTH_COOKIE_SECURE = True

# --- Misc hardening --------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Behind nginx (one proxy): derive the client IP from X-Forwarded-For so rate
# limits bucket per real client, not per proxy. Override if more proxies are
# added (e.g. a CDN/load balancer in front of nginx).
REST_FRAMEWORK["NUM_PROXIES"] = env.int("NUM_PROXIES", default=1)  # noqa: F405

# --- Auth / email ----------------------------------------------------------
# Require verified emails before email/password login, and send real mail.
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="mandatory")  # noqa: F405
EMAIL_BACKEND = env(  # noqa: F405
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
