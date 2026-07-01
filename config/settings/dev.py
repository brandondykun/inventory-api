"""Local development settings: DEBUG on, docs + debug toolbar enabled."""

from .base import *  # noqa: F403

DEBUG = True
ENVIRONMENT = "dev"

ALLOWED_HOSTS = ["*"]

# Interactive API docs on in development.
ENABLE_API_DOCS = True

# --- Developer tooling -----------------------------------------------------
INSTALLED_APPS += [  # noqa: F405
    "debug_toolbar",
    "django_extensions",
]

MIDDLEWARE.insert(  # noqa: F405
    0, "debug_toolbar.middleware.DebugToolbarMiddleware"
)

# django-debug-toolbar inside Docker: show for any internal IP. Setting
# SHOW_TOOLBAR_CALLBACK to always-true is acceptable for local dev only.
INTERNAL_IPS = ["127.0.0.1", "localhost"]
DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG}

# Permissive CORS for local frontends.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list(  # noqa: F405
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)
