"""
End-to-end settings: production-like (DEBUG off, real Postgres/Redis/Celery)
but pointed at an isolated database for full-stack browser/API tests.
"""

from .base import *  # noqa: F403

DEBUG = False
ENVIRONMENT = "e2e"

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])  # noqa: F405

# Expose docs so e2e suites can drive against the schema if needed.
ENABLE_API_DOCS = True

# Real Celery (not eager) so async flows are exercised exactly as in prod.
CELERY_TASK_ALWAYS_EAGER = False
