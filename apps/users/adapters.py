"""allauth account adapter for the email-based custom user model."""

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings


class CustomAccountAdapter(DefaultAccountAdapter):
    """Account-level allauth hooks.

    Centralizes account policy so forks have a single place to tweak signup
    rules, name population, and email behavior.
    """

    def is_open_for_signup(self, request) -> bool:
        # Flip to False (or gate on an env flag) to make the instance
        # invite-only. Kept open so the base works out of the box.
        return getattr(settings, "ACCOUNT_ALLOW_SIGNUPS", True)

    def save_user(self, request, user, form, commit=True):
        """Populate first/last name from signup data when present."""
        user = super().save_user(request, user, form, commit=False)
        data = getattr(form, "cleaned_data", {}) or {}
        user.first_name = data.get("first_name", user.first_name)
        user.last_name = data.get("last_name", user.last_name)
        if commit:
            user.save()
        return user
