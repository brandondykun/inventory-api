"""Test settings: fast password hashing, eager Celery, no external brokers."""

from .base import *  # noqa: F403

DEBUG = False
ENVIRONMENT = "test"

# Fast, insecure hasher — acceptable because it only runs in the test suite.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Run Celery tasks synchronously in-process; never touch a real broker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# In-memory cache so tests don't require Redis.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Don't gate login on email verification in tests; capture mail in memory.
ACCOUNT_EMAIL_VERIFICATION = "none"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Allow overriding the DB host so the suite can run on the host or in CI.
DATABASES["default"]["HOST"] = env(  # noqa: F405
    "POSTGRES_HOST", default="localhost"
)
