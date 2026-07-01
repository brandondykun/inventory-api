"""Tests for the web/mobile-aware JWT auth flow."""

import pytest
from allauth.account.models import EmailAddress
from django.conf import settings
from django.middleware.csrf import get_token
from django.test import RequestFactory
from rest_framework.settings import api_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.users.tests.factories import DEFAULT_PASSWORD

LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"
LOGOUT_URL = "/api/auth/logout/"
ME_URL = "/api/users/me/"

ACCESS_COOKIE = settings.AUTH_COOKIE_ACCESS
REFRESH_COOKIE = settings.AUTH_COOKIE_REFRESH


def _credentials(user):
    return {"email": user.email, "password": DEFAULT_PASSWORD}


@pytest.mark.django_db
class TestWebAuth:
    """Web clients (default): tokens delivered as HttpOnly cookies."""

    def test_login_sets_httponly_cookies_and_hides_tokens(self, api_client, user):
        resp = api_client.post(LOGIN_URL, _credentials(user))
        assert resp.status_code == 200
        assert ACCESS_COOKIE in resp.cookies
        assert REFRESH_COOKIE in resp.cookies
        assert resp.cookies[ACCESS_COOKIE]["httponly"]
        # Tokens must NOT appear in the body for web.
        assert "access" not in resp.data
        assert "refresh" not in resp.data
        assert resp.data["user"]["email"] == user.email

    def test_login_sets_csrf_cookie(self, api_client, user):
        # The CSRF cookie is readable by JS (not HttpOnly) so an SPA can echo it
        # back as the X-CSRFToken header on later unsafe requests.
        resp = api_client.post(LOGIN_URL, _credentials(user))
        assert settings.CSRF_COOKIE_NAME in resp.cookies
        assert not resp.cookies[settings.CSRF_COOKIE_NAME]["httponly"]

    def test_cookie_authenticates_protected_endpoint(self, api_client, user):
        api_client.post(LOGIN_URL, _credentials(user))  # sets cookies on client
        resp = api_client.get(ME_URL)
        assert resp.status_code == 200
        assert resp.data["email"] == user.email

    def test_refresh_from_cookie(self, api_client, user):
        api_client.post(LOGIN_URL, _credentials(user))
        resp = api_client.post(REFRESH_URL)
        assert resp.status_code == 200
        assert ACCESS_COOKIE in resp.cookies

    def test_logout_clears_cookies(self, api_client, user):
        api_client.post(LOGIN_URL, _credentials(user))
        resp = api_client.post(LOGOUT_URL)
        assert resp.status_code == 205
        # delete_cookie expires the cookie (empty value / past expiry).
        assert api_client.cookies.get(ACCESS_COOKIE).value == ""

    def test_logout_blacklists_refresh_token(self, api_client, user):
        # Clearing the cookie isn't enough — the refresh token itself must be
        # blacklisted so a copy can't be replayed after logout.
        login = api_client.post(LOGIN_URL, _credentials(user))
        refresh = login.cookies[REFRESH_COOKIE].value
        assert api_client.post(LOGOUT_URL).status_code == 205

        # Re-present the (now blacklisted) refresh token: it must be rejected.
        api_client.cookies[REFRESH_COOKIE] = refresh
        resp = api_client.post(REFRESH_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestMobileAuth:
    """Mobile clients: tokens delivered in the response body."""

    HEADER = {"HTTP_X_CLIENT_TYPE": "mobile"}

    def test_login_returns_tokens_in_body_no_cookies(self, api_client, user):
        resp = api_client.post(LOGIN_URL, _credentials(user), **self.HEADER)
        assert resp.status_code == 200
        assert resp.data["access"]
        assert resp.data["refresh"]
        assert ACCESS_COOKIE not in resp.cookies

    def test_bearer_authenticates_protected_endpoint(self, api_client, user):
        login = api_client.post(LOGIN_URL, _credentials(user), **self.HEADER)
        access = login.data["access"]
        resp = api_client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert resp.status_code == 200
        assert resp.data["email"] == user.email

    def test_refresh_from_body(self, api_client, user):
        login = api_client.post(LOGIN_URL, _credentials(user), **self.HEADER)
        resp = api_client.post(REFRESH_URL, {"refresh": login.data["refresh"]}, **self.HEADER)
        assert resp.status_code == 200
        assert resp.data["access"]

    def test_logout_blacklists_refresh_token(self, api_client, user):
        # Mobile sends the refresh token in the body; logout must blacklist it
        # so it can't be reused to mint new access tokens.
        login = api_client.post(LOGIN_URL, _credentials(user), **self.HEADER)
        refresh = login.data["refresh"]
        logout = api_client.post(LOGOUT_URL, {"refresh": refresh}, **self.HEADER)
        assert logout.status_code == 205

        resp = api_client.post(REFRESH_URL, {"refresh": refresh}, **self.HEADER)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestCookieCsrf:
    """Cookie-authenticated unsafe requests must carry a valid CSRF token.

    The browser sends the access-token cookie ambiently, so without a CSRF
    check a cross-site page could drive state-changing calls. Bearer-header
    (mobile/API) clients don't send ambient cookies and stay exempt.
    """

    def _csrf_client(self):
        # enforce_csrf_checks=True makes the test client behave like a browser
        # w.r.t. CSRF (the default DRF test client suppresses the check).
        return APIClient(enforce_csrf_checks=True)

    def test_cookie_unsafe_request_without_csrf_is_blocked(self, user):
        client = self._csrf_client()
        client.post(LOGIN_URL, _credentials(user))  # sets auth cookies
        resp = client.patch(ME_URL, {"first_name": "X"})
        assert resp.status_code == 403

    def test_cookie_safe_request_without_csrf_is_allowed(self, user):
        # GET is a safe method — no CSRF token required.
        client = self._csrf_client()
        client.post(LOGIN_URL, _credentials(user))
        assert client.get(ME_URL).status_code == 200

    def test_cookie_unsafe_request_with_csrf_succeeds(self, user):
        client = self._csrf_client()
        client.post(LOGIN_URL, _credentials(user))

        token = get_token(RequestFactory().get("/"))
        client.cookies["csrftoken"] = token
        resp = client.patch(ME_URL, {"first_name": "X"}, HTTP_X_CSRFTOKEN=token)
        assert resp.status_code == 200
        assert resp.data["first_name"] == "X"

    def test_bearer_unsafe_request_is_exempt_from_csrf(self, user):
        client = self._csrf_client()
        login = client.post(LOGIN_URL, _credentials(user), HTTP_X_CLIENT_TYPE="mobile")
        access = login.data["access"]
        resp = client.patch(ME_URL, {"first_name": "X"}, HTTP_AUTHORIZATION=f"Bearer {access}")
        assert resp.status_code == 200


@pytest.mark.django_db
class TestLoginThrottle:
    """Login has its own (strict) rate limit, keyed on the real client IP."""

    @staticmethod
    def _set_login_rate(monkeypatch, rate):
        # DRF freezes ``THROTTLE_RATES`` on the throttle class at import, so a
        # runtime ``settings`` change won't reach it — patch the attribute the
        # throttle actually reads (auto-restored by monkeypatch).
        monkeypatch.setattr(
            SimpleRateThrottle,
            "THROTTLE_RATES",
            {**SimpleRateThrottle.THROTTLE_RATES, "login": rate},
        )

    def test_login_is_rate_limited(self, api_client, user, monkeypatch):
        self._set_login_rate(monkeypatch, "3/min")
        creds = {"email": user.email, "password": "wrong"}
        for _ in range(3):
            assert api_client.post(LOGIN_URL, creds).status_code == 401
        # The 4th attempt within the window is throttled, not merely rejected.
        assert api_client.post(LOGIN_URL, creds).status_code == 429

    def test_throttle_keys_on_client_ip_behind_proxy(self, api_client, user, monkeypatch):
        # With one trusted proxy, the bucket key is the rightmost (nginx-appended)
        # XFF entry — the real client. A spoofed XFF prefix can't dodge the limit,
        # and distinct clients don't share one nginx-IP bucket.
        self._set_login_rate(monkeypatch, "1/min")
        monkeypatch.setattr(api_settings, "NUM_PROXIES", 1)
        creds = {"email": user.email, "password": "wrong"}

        a = "9.9.9.9, 1.1.1.1"  # client A behind proxy
        assert api_client.post(LOGIN_URL, creds, HTTP_X_FORWARDED_FOR=a).status_code == 401
        assert api_client.post(LOGIN_URL, creds, HTTP_X_FORWARDED_FOR=a).status_code == 429

        # Different real client → its own bucket, still allowed.
        b = "9.9.9.9, 2.2.2.2"
        assert api_client.post(LOGIN_URL, creds, HTTP_X_FORWARDED_FOR=b).status_code == 401


@pytest.mark.django_db
def test_login_rejects_bad_credentials(api_client, user):
    resp = api_client.post(LOGIN_URL, {"email": user.email, "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.django_db
class TestMandatoryEmailVerification:
    """When verification is mandatory, unverified users can't log in."""

    def test_unverified_user_is_blocked(self, api_client, user, settings):
        settings.ACCOUNT_EMAIL_VERIFICATION = "mandatory"
        resp = api_client.post(LOGIN_URL, _credentials(user))
        assert resp.status_code == 400
        assert "verified" in str(resp.data).lower()

    def test_verified_user_succeeds(self, api_client, user, settings):
        settings.ACCOUNT_EMAIL_VERIFICATION = "mandatory"
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
        resp = api_client.post(LOGIN_URL, _credentials(user))
        assert resp.status_code == 200
