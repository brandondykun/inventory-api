"""Shared pytest fixtures."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Reset DRF throttle history (stored in the cache) between tests so rate
    limits don't bleed across the suite."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    """A persisted user whose password is ``password123``."""
    return UserFactory()


@pytest.fixture
def auth_client(api_client, user):
    """An APIClient authenticated as ``user`` (bypasses the token flow)."""
    api_client.force_authenticate(user=user)
    return api_client
