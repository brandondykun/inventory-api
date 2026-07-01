"""
Authentication class that accepts a JWT from EITHER an HttpOnly cookie (web
clients) OR the ``Authorization: Bearer`` header (mobile clients).

Registered as the project's default authentication class, so both client types
work transparently without per-view configuration.

CSRF: when the token comes from the cookie the browser sends it ambiently, so a
cross-site page could otherwise drive state-changing requests. We therefore run
Django's CSRF check on the cookie path (same approach as DRF's
``SessionAuthentication``). The Bearer-header path is exempt — those clients
don't send ambient cookies, so they aren't reachable by CSRF.
"""

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication


class _CSRFCheck(CsrfViewMiddleware):
    def _reject(self, request, reason):
        # Surface the failure reason to the caller instead of returning a
        # response, mirroring DRF's SessionAuthentication.enforce_csrf.
        return reason


class CookieOrHeaderJWTAuthentication(JWTAuthentication):
    def authenticate(self, request: Request):
        header = self.get_header(request)
        if header is None:
            # No Authorization header — fall back to the access-token cookie.
            raw_token = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)
            from_cookie = True
        else:
            raw_token = self.get_raw_token(header)
            from_cookie = False

        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)

        # Cookie-borne credentials are sent ambiently by the browser, so unsafe
        # methods must carry a valid CSRF token. Bearer clients are exempt.
        if from_cookie:
            self.enforce_csrf(request)

        return user, validated_token

    def enforce_csrf(self, request: Request) -> None:
        """Run Django's CSRF check; raise PermissionDenied on failure."""

        def dummy_get_response(request):  # pragma: no cover
            return None

        check = _CSRFCheck(dummy_get_response)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")
