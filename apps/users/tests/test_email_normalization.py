"""Emails must always be stored lowercase, regardless of creation path."""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestEmailNormalization:
    def test_save_lowercases_mixed_case_email(self):
        user = User(email="Foo@Example.COM")
        user.set_unusable_password()
        user.save()
        assert user.email == "foo@example.com"

    def test_create_user_lowercases_email(self):
        user = User.objects.create_user("Bar@X.com", password="x")
        assert user.email == "bar@x.com"
