"""Operational endpoints (health checks, etc.)."""

from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Lightweight liveness/readiness probe used by Docker and orchestrators."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        responses={200: {"type": "object"}},
        description="Returns service and database status.",
    )
    def get(self, request: Request) -> Response:
        db_ok = True
        try:
            connection.ensure_connection()
        except Exception:  # noqa: BLE001 - report DB down rather than 500
            db_ok = False

        status_code = 200 if db_ok else 503
        return Response(
            {"status": "ok" if db_ok else "degraded", "database": db_ok},
            status=status_code,
        )


health_check = HealthCheckView.as_view()
