"""Tests for the shared building blocks every fork inherits.

These cover the generic pieces in ``apps.common`` — the health probe, the
error-envelope exception handler, and the project-wide pagination — rather than
any business logic.
"""

import pytest
from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.test import APIRequestFactory

from apps.common.exceptions import api_exception_handler
from apps.common.pagination import StandardResultsSetPagination

HEALTH_URL = "/healthz/"


@pytest.mark.django_db
class TestHealthCheck:
    """``GET /healthz/`` reports service + database status."""

    def test_healthy_returns_200(self, api_client):
        resp = api_client.get(HEALTH_URL)
        assert resp.status_code == 200
        assert resp.data == {"status": "ok", "database": True}

    def test_unauthenticated_access_is_allowed(self, api_client):
        # The probe opts out of the global IsAuthenticated default.
        assert api_client.get(HEALTH_URL).status_code == 200

    def test_database_down_returns_503(self, api_client, monkeypatch):
        # Simulate the DB being unreachable: the view must report "degraded"
        # with a 503 rather than bubbling up a 500.
        def _boom():
            raise Exception("db unreachable")

        monkeypatch.setattr("apps.common.views.connection.ensure_connection", _boom)
        resp = api_client.get(HEALTH_URL)
        assert resp.status_code == 503
        assert resp.data == {"status": "degraded", "database": False}


class TestApiExceptionHandler:
    """All handled DRF errors get wrapped in a stable ``{"error": ...}`` envelope."""

    def test_wraps_drf_error_in_envelope(self):
        exc = ValidationError({"email": ["This field is required."]})
        response = api_exception_handler(exc, {})

        assert response is not None
        assert response.status_code == 400
        assert response.data == {
            "error": {
                "status_code": 400,
                "detail": {"email": ["This field is required."]},
            }
        }

    def test_preserves_status_code(self):
        response = api_exception_handler(NotAuthenticated(), {})
        assert response.status_code == 401
        assert response.data["error"]["status_code"] == 401

    def test_returns_none_for_unhandled_exception(self):
        # Non-DRF exceptions fall through to Django's normal 500 handling.
        assert api_exception_handler(ValueError("boom"), {}) is None


class TestStandardResultsSetPagination:
    """Client-overridable page size, capped at ``max_page_size``."""

    def _page_size_for(self, query):
        paginator = StandardResultsSetPagination()
        request = APIRequestFactory().get(f"/items/{query}")
        # DRF wraps the request; get_page_size reads it from query_params.
        from rest_framework.request import Request

        return paginator.get_page_size(Request(request))

    def test_client_can_override_page_size(self):
        assert self._page_size_for("?page_size=5") == 5

    def test_page_size_is_capped_at_max(self):
        assert self._page_size_for("?page_size=999") == StandardResultsSetPagination.max_page_size

    def test_max_page_size_is_100(self):
        assert StandardResultsSetPagination.max_page_size == 100
