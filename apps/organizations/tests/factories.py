"""Test factories for the organizations app."""

import factory

from apps.organizations.models import Organization
from apps.users.tests.factories import UserFactory


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Org {n}")
    owner = factory.SubFactory(UserFactory)
    created_by = factory.SelfAttribute("owner")
