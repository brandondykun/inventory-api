"""
JWT auth endpoints with web/mobile-aware token delivery.

- Web clients (default): tokens are set as HttpOnly cookies; the body carries
  only the user payload.
- Mobile clients (``X-Client-Type: mobile``): tokens are returned in the body
  for Bearer-header use; no cookies are set.
"""

import contextlib

from allauth.socialaccount.providers.apple.views import AppleOAuth2Adapter
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.users.serializers import UserSerializer

from .serializers import LoginSerializer
from .utils import (
    clear_auth_cookies,
    ensure_csrf_cookie,
    is_web_client,
    set_access_cookie,
    set_auth_cookies,
    set_refresh_cookie,
)


def _issue_jwt_response(request: Request, user) -> Response:
    """Issue OUR JWTs for ``user`` via the shared web/mobile delivery.

    Web clients (default) get HttpOnly cookies + a user payload; mobile clients
    (``X-Client-Type: mobile``) get tokens in the body. This is the same
    contract as :class:`LoginView`, reused by the social-login bridge.
    """
    refresh = LoginSerializer.get_token(user)
    access = refresh.access_token
    user_data = UserSerializer(user).data

    if is_web_client(request):
        response = Response({"user": user_data}, status=status.HTTP_200_OK)
        set_auth_cookies(response, str(access), str(refresh))
        ensure_csrf_cookie(request)
        return response

    return Response(
        {"access": str(access), "refresh": str(refresh), "user": user_data},
        status=status.HTTP_200_OK,
    )


CLIENT_TYPE_PARAM = OpenApiParameter(
    name="X-Client-Type",
    location=OpenApiParameter.HEADER,
    required=False,
    description="`web` (default) sets HttpOnly cookies; `mobile` returns tokens in the body.",
    enum=["web", "mobile"],
)


@extend_schema(parameters=[CLIENT_TYPE_PARAM])
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    # Dedicated, strict throttle bucket to blunt credential stuffing/brute force.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tokens = serializer.validated_data
        user_data = UserSerializer(serializer.user).data

        if is_web_client(request):
            response = Response({"user": user_data}, status=status.HTTP_200_OK)
            set_auth_cookies(response, tokens["access"], tokens["refresh"])
            ensure_csrf_cookie(request)
            return response

        return Response(
            {
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "user": user_data,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Social login (web + mobile)
# ---------------------------------------------------------------------------
# dj-rest-auth's SocialLoginView verifies the provider token (via allauth's
# provider adapters) and resolves/links the user. We subclass it ONLY to
# replace its response with our own JWT delivery, so social sign-in returns
# the exact same web-cookie/mobile-body tokens as email/password login.
#
# Clients POST a provider token, e.g. {"id_token": "<google_id_token>"} for a
# native app, or {"access_token": "..."} / {"code": "..."} for web flows.


class _BaseSocialLoginView(SocialLoginView):
    client_class = OAuth2Client

    @extend_schema(parameters=[CLIENT_TYPE_PARAM])
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)

    def get_response(self) -> Response:
        # self.user is set by dj-rest-auth after the serializer verifies the
        # provider token; hand off to our shared token delivery.
        return _issue_jwt_response(self.request, self.user)


class GoogleLoginView(_BaseSocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    callback_url = settings.GOOGLE_CALLBACK_URL


class AppleLoginView(_BaseSocialLoginView):
    adapter_class = AppleOAuth2Adapter
    callback_url = settings.APPLE_CALLBACK_URL


@extend_schema(parameters=[CLIENT_TYPE_PARAM])
class RefreshView(TokenRefreshView):
    def post(self, request: Request, *args, **kwargs) -> Response:
        web = is_web_client(request)

        if web:
            refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
            payload = {"refresh": refresh} if refresh else {}
        else:
            payload = request.data

        serializer = self.get_serializer(data=payload)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc

        validated = serializer.validated_data

        if web:
            response = Response({"detail": "Token refreshed."}, status=status.HTTP_200_OK)
            set_access_cookie(response, validated["access"])
            # With ROTATE_REFRESH_TOKENS a fresh refresh token is issued too.
            if "refresh" in validated:
                set_refresh_cookie(response, validated["refresh"])
            return response

        return Response(validated, status=status.HTTP_200_OK)


@extend_schema(parameters=[CLIENT_TYPE_PARAM], request=None, responses={205: None})
class LogoutView(APIView):
    """Blacklist the refresh token and (for web) clear auth cookies."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request: Request) -> Response:
        web = is_web_client(request)
        raw = (
            request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
            if web
            else request.data.get("refresh")
        )

        if raw:
            # Logout is idempotent — ignore already invalid/expired tokens.
            with contextlib.suppress(TokenError):
                RefreshToken(raw).blacklist()

        response = Response(status=status.HTTP_205_RESET_CONTENT)
        if web:
            clear_auth_cookies(response)
        return response
