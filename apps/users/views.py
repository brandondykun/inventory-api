"""User API views."""

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .serializers import RegisterSerializer, UserSerializer

User = get_user_model()

# Identical for new and already-registered emails so the response can't be used
# to tell which addresses have accounts (see ``RegisterView``).
REGISTRATION_DETAIL = "Registration received. Check your email to continue."


class RegisterView(generics.CreateAPIView):
    """Public self-service user registration (email/password).

    Registers the user with allauth so an ``EmailAddress`` record exists — this
    drives email verification and lets a later social sign-in with the same
    verified email link to this account instead of creating a duplicate.

    Enumeration-safe: an already-registered email returns the *same* 201 body as
    a fresh signup (no duplicate is created); the address owner is notified out
    of band instead of the response revealing that the account exists.
    """

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    # Dedicated throttle bucket to limit signup spam / email-enumeration probing.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Fixed body in every case — never echo the user object.
        return Response({"detail": REGISTRATION_DETAIL}, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        email = serializer.validated_data["email"]
        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None:
            # Don't create a duplicate; tell the real owner someone tried.
            self._notify_existing_account(existing.email)
            return

        user = serializer.save()
        email_address, _ = EmailAddress.objects.get_or_create(
            user=user,
            email=user.email,
            defaults={"primary": True, "verified": False},
        )
        # Send a confirmation mail unless verification is disabled (e.g. tests).
        if settings.ACCOUNT_EMAIL_VERIFICATION != "none":
            email_address.send_confirmation(self.request, signup=True)

    def _notify_existing_account(self, email: str) -> None:
        if settings.ACCOUNT_EMAIL_VERIFICATION == "none":
            return
        send_mail(
            subject="You already have an account",
            message=(
                "Someone tried to register an account with this email address. "
                "If this was you, you can sign in or reset your password — "
                "there's no need to register again."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )


class MeView(generics.RetrieveUpdateAPIView):
    """Retrieve or update the currently authenticated user."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
