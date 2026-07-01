"""Test factories for the users app."""

import factory
from django.contrib.auth import get_user_model

User = get_user_model()

DEFAULT_PASSWORD = "password123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"
    # Stores a properly hashed password as a normal field value (persisted on
    # save), so the login flow works in tests.
    password = factory.django.Password(DEFAULT_PASSWORD)
