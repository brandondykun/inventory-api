"""Tests for the custom user model and user endpoints."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from .factories import DEFAULT_PASSWORD, UserFactory

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_uses_email(self):
        user = User.objects.create_user(email="a@example.com", password="x")
        assert user.email == "a@example.com"
        assert user.check_password("x")
        assert not user.is_staff and not user.is_superuser

    def test_create_superuser(self):
        admin = User.objects.create_superuser(email="root@example.com", password="x")
        assert admin.is_staff and admin.is_superuser

    def test_email_required(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password="x")


@pytest.mark.django_db
class TestUserEndpoints:
    def test_register(self, api_client):
        resp = api_client.post(
            "/api/users/register/",
            {"email": "new@example.com", "password": "supersecret1"},
        )
        assert resp.status_code == 201
        assert User.objects.filter(email="new@example.com").exists()

    def test_register_creates_allauth_email_address(self, api_client):
        # An EmailAddress record must exist so verification + social linking work.
        api_client.post(
            "/api/users/register/",
            {"email": "ea@example.com", "password": "supersecret1"},
        )
        user = User.objects.get(email="ea@example.com")
        assert EmailAddress.objects.filter(user=user, email=user.email).exists()

    def test_register_response_hides_user_object(self, api_client):
        # The response must not echo id/email (those differ for new vs existing
        # and would leak account existence).
        resp = api_client.post(
            "/api/users/register/",
            {"email": "shape@example.com", "password": "supersecret1"},
        )
        assert resp.status_code == 201
        assert "id" not in resp.data
        assert "email" not in resp.data

    def test_register_existing_email_is_enumeration_safe(self, api_client, user):
        # Registering an already-registered email must look identical to a fresh
        # registration: same status, same body, and no second user created.
        before = User.objects.count()
        existing = api_client.post(
            "/api/users/register/",
            {"email": user.email, "password": "supersecret1"},
        )
        fresh = api_client.post(
            "/api/users/register/",
            {"email": "brandnew@example.com", "password": "supersecret1"},
        )
        assert existing.status_code == fresh.status_code == 201
        assert existing.data == fresh.data
        # The existing email must NOT have produced a duplicate user.
        assert User.objects.filter(email__iexact=user.email).count() == 1
        assert User.objects.count() == before + 1  # only the fresh one

    def test_register_rejects_weak_password(self, api_client):
        # Passes the 8-char minimum but must be rejected by Django's password
        # validators (common + all-numeric). No user may be created.
        resp = api_client.post(
            "/api/users/register/",
            {"email": "weak@example.com", "password": "12345678"},
        )
        assert resp.status_code == 400
        assert not User.objects.filter(email="weak@example.com").exists()

    def test_register_rejects_password_similar_to_email(self, api_client):
        # UserAttributeSimilarityValidator must run, so a password derived from
        # the email is rejected.
        resp = api_client.post(
            "/api/users/register/",
            {"email": "alicecooper@example.com", "password": "alicecooper"},
        )
        assert resp.status_code == 400
        assert not User.objects.filter(email="alicecooper@example.com").exists()

    def test_me_requires_auth(self, api_client):
        assert api_client.get("/api/users/me/").status_code == 401

    def test_me_returns_current_user(self, auth_client, user):
        resp = auth_client.get("/api/users/me/")
        assert resp.status_code == 200
        assert resp.data["email"] == user.email

    def test_me_can_update_name(self, auth_client, user):
        resp = auth_client.patch("/api/users/me/", {"first_name": "Changed"})
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.first_name == "Changed"

    def test_me_cannot_change_email(self, auth_client, user):
        # Email is the login identifier and gates verification; it must not be
        # changeable through the generic profile endpoint (no re-verification).
        original = user.email
        resp = auth_client.patch("/api/users/me/", {"email": "attacker@example.com"})
        assert resp.status_code == 200  # ignored, not rejected (read-only field)
        user.refresh_from_db()
        assert user.email == original
        assert resp.data["email"] == original

    def test_me_unused_factory_password(self):
        # Sanity check the factory wiring used across the auth tests.
        user = UserFactory()
        assert user.check_password(DEFAULT_PASSWORD)
