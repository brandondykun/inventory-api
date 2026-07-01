"""Auth serializers built on Simple JWT."""

from allauth.account.models import EmailAddress
from django.conf import settings
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class LoginSerializer(TokenObtainPairSerializer):
    """Email/password login. Uses the configured USERNAME_FIELD (email)."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Embed lightweight claims useful to clients without a DB round trip.
        token["email"] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # When verification is mandatory, block unverified accounts at login.
        # Other modes ("optional"/"none") let unverified users in.
        if settings.ACCOUNT_EMAIL_VERIFICATION == "mandatory" and not _is_verified(self.user):
            raise serializers.ValidationError(
                {"detail": "E-mail address is not verified."},
                code="email_not_verified",
            )
        return data


def _is_verified(user) -> bool:
    return EmailAddress.objects.filter(user=user, verified=True).exists()
