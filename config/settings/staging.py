"""
Staging settings: identical hardening to production, but with interactive API
docs enabled so the team can exercise the API against a prod-like deployment.
"""

from .production import *  # noqa: F403

ENVIRONMENT = "staging"

# Staging exposes the docs by default (override with ENABLE_API_DOCS=false).
ENABLE_API_DOCS = env.bool("ENABLE_API_DOCS", default=True)  # noqa: F405
