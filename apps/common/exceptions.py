"""Consistent error envelope for all API responses."""

from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Wrap DRF's default error payload in a stable ``{"error": ...}`` envelope.

    Produces:
        {"error": {"status_code": 400, "detail": <original drf detail>}}

    Returns ``None`` for unhandled exceptions so Django's normal 500 handling
    (and logging) still applies.
    """
    response = exception_handler(exc, context)
    if response is None:
        return None

    response.data = {
        "error": {
            "status_code": response.status_code,
            "detail": response.data,
        }
    }
    return response
