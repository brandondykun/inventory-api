import pytest

from apps.organizations.models import Organization, Plan
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_plans_are_seeded():
    tiers = set(Plan.objects.values_list("tier", flat=True))
    assert {"free", "pro", "enterprise"} <= tiers


@pytest.mark.django_db
def test_free_plan_has_member_limit():
    free = Plan.objects.get(tier=Plan.Tier.FREE)
    assert free.max_members == 3


@pytest.mark.django_db
def test_organization_str_and_owner():
    org = OrganizationFactory(name="Acme")
    assert str(org) == "Acme"
    assert org.owner_id is not None
    assert isinstance(org, Organization)
