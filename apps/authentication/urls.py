"""Authentication routes (mounted under /api/auth/)."""

from django.urls import path

from .views import (
    AppleLoginView,
    GoogleLoginView,
    LoginView,
    LogoutView,
    RefreshView,
)

app_name = "authentication"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # Social sign-in — POST a provider token; returns our JWTs (web/mobile).
    path("social/google/", GoogleLoginView.as_view(), name="social-google"),
    path("social/apple/", AppleLoginView.as_view(), name="social-apple"),
]
