"""Client-type detection and auth-cookie helpers."""

from django.conf import settings
from django.middleware.csrf import get_token
from rest_framework.request import Request
from rest_framework.response import Response


def ensure_csrf_cookie(request: Request) -> None:
    """Make Django emit the CSRF cookie on this response.

    Web clients authenticate via the access-token cookie, so unsafe requests are
    CSRF-checked (see ``CookieOrHeaderJWTAuthentication``). Calling this on login
    hands the browser a CSRF token to echo back as the ``X-CSRFToken`` header.
    """
    get_token(getattr(request, "_request", request))


def is_web_client(request: Request) -> bool:
    """Web is the default; mobile clients opt in via ``X-Client-Type: mobile``."""
    client = request.headers.get("X-Client-Type", "web").strip().lower()
    return client != "mobile"


def _cookie_kwargs() -> dict:
    return {
        "httponly": settings.AUTH_COOKIE_HTTP_ONLY,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "path": settings.AUTH_COOKIE_PATH,
        "domain": settings.AUTH_COOKIE_DOMAIN,
    }


def set_access_cookie(response: Response, token: str) -> None:
    max_age = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
    response.set_cookie(settings.AUTH_COOKIE_ACCESS, token, max_age=max_age, **_cookie_kwargs())


def set_refresh_cookie(response: Response, token: str) -> None:
    max_age = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
    response.set_cookie(settings.AUTH_COOKIE_REFRESH, token, max_age=max_age, **_cookie_kwargs())


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    set_access_cookie(response, access)
    set_refresh_cookie(response, refresh)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        settings.AUTH_COOKIE_ACCESS,
        path=settings.AUTH_COOKIE_PATH,
        domain=settings.AUTH_COOKIE_DOMAIN,
    )
    response.delete_cookie(
        settings.AUTH_COOKIE_REFRESH,
        path=settings.AUTH_COOKIE_PATH,
        domain=settings.AUTH_COOKIE_DOMAIN,
    )
