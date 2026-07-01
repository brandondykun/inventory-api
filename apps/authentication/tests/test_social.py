"""Tests for the social-login bridge (dj-rest-auth -> our JWT delivery).

Provider token verification is mocked: real Google/Apple tokens require live
client IDs and developer accounts, so here we stub the verification step and
assert our half — token delivery (web cookies vs mobile body) and account
linking — behaves correctly.
"""

from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings

from apps.authentication.adapters import CustomSocialAccountAdapter
from apps.users.tests.factories import UserFactory

GOOGLE_URL = "/api/auth/social/google/"
ACCESS_COOKIE = settings.AUTH_COOKIE_ACCESS
REFRESH_COOKIE = settings.AUTH_COOKIE_REFRESH

# Where dj-rest-auth's social serializer lives; patching its validate() lets us
# bypass the real provider round-trip and inject a resolved user.
VALIDATE = "dj_rest_auth.registration.serializers.SocialLoginSerializer.validate"


@pytest.mark.django_db
class TestSocialLoginDelivery:
    def test_web_sets_httponly_cookies_no_body_tokens(self, api_client, user):
        with patch(VALIDATE, return_value={"user": user}):
            resp = api_client.post(GOOGLE_URL, {"id_token": "stub"})
        assert resp.status_code == 200
        assert ACCESS_COOKIE in resp.cookies
        assert REFRESH_COOKIE in resp.cookies
        assert resp.cookies[ACCESS_COOKIE]["httponly"]
        assert "access" not in resp.data
        assert resp.data["user"]["email"] == user.email

    def test_mobile_returns_tokens_in_body_no_cookies(self, api_client, user):
        with patch(VALIDATE, return_value={"user": user}):
            resp = api_client.post(GOOGLE_URL, {"id_token": "stub"}, HTTP_X_CLIENT_TYPE="mobile")
        assert resp.status_code == 200
        assert resp.data["access"]
        assert resp.data["refresh"]
        assert ACCESS_COOKIE not in resp.cookies


@pytest.mark.django_db
class TestSocialAccountLinking:
    """CustomSocialAccountAdapter.pre_social_login behavior."""

    def _sociallogin(self, email, *, verified):
        account = SocialAccount(provider="google", uid="uid-123")
        addresses = [EmailAddress(email=email, verified=verified, primary=True)]
        return SocialLogin(account=account, email_addresses=addresses)

    def test_links_to_existing_user_when_email_verified(self, rf):
        user = UserFactory(email="link@example.com")
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
        sociallogin = self._sociallogin("link@example.com", verified=True)
        request = rf.post(GOOGLE_URL)

        with patch.object(SocialLogin, "connect") as mock_connect:
            CustomSocialAccountAdapter().pre_social_login(request, sociallogin)
        mock_connect.assert_called_once_with(request, user)

    def test_does_not_link_when_provider_email_unverified(self, rf):
        user = UserFactory(email="noverify@example.com")
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
        sociallogin = self._sociallogin("noverify@example.com", verified=False)
        request = rf.post(GOOGLE_URL)

        with patch.object(SocialLogin, "connect") as mock_connect:
            CustomSocialAccountAdapter().pre_social_login(request, sociallogin)
        mock_connect.assert_not_called()

    def test_no_link_when_no_matching_user(self, rf):
        sociallogin = self._sociallogin("stranger@example.com", verified=True)
        request = rf.post(GOOGLE_URL)

        with patch.object(SocialLogin, "connect") as mock_connect:
            CustomSocialAccountAdapter().pre_social_login(request, sociallogin)
        mock_connect.assert_not_called()
