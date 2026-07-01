"""allauth social adapter: account linking + profile population."""

from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Link social logins to existing accounts and copy over names.

    Without this, signing in with Google using an email that already has a
    local (email/password) account would create a *second* user. We instead
    connect the social account to the existing user — but only when the
    provider asserts the email is verified, so an attacker can't hijack an
    account by registering an unverified address at a sloppy provider.
    """

    def pre_social_login(self, request, sociallogin):
        # Already connected to a user (returning social user) — nothing to do.
        if sociallogin.is_existing:
            return

        verified_emails = {
            address.email.lower() for address in sociallogin.email_addresses if address.verified
        }
        if not verified_emails:
            return

        existing = (
            User.objects.filter(email__iexact=next(iter(verified_emails)))
            .order_by("created_at")
            .first()
        )
        if existing is None:
            return

        # Defense-in-depth: only link if the *local* account's email is itself
        # verified (or no verification is in force for that address).
        local_verified = EmailAddress.objects.filter(
            user=existing, email__iexact=existing.email, verified=True
        ).exists()
        local_has_any = EmailAddress.objects.filter(user=existing).exists()
        if local_verified or not local_has_any:
            sociallogin.connect(request, existing)

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.first_name = data.get("first_name") or user.first_name or ""
        user.last_name = data.get("last_name") or user.last_name or ""
        return user
