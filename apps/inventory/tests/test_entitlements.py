import pytest

from apps.inventory.models import InventoryUnit
from apps.organizations.models import Plan
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_free_plan_seeded_with_max_subdivisions_five():
    free = Plan.objects.get(tier=Plan.Tier.FREE)
    assert free.max_subdivisions == 5


@pytest.mark.django_db
def test_limit_for_subdivisions_reads_plan_then_override():
    org = OrganizationFactory()
    sub = org.subscription
    assert sub.limit_for("subdivisions") == 5
    sub.max_subdivisions_override = 20
    sub.save()
    assert sub.limit_for("subdivisions") == 20


@pytest.mark.django_db
def test_usage_locations_counts_top_level_units_only():
    org = OrganizationFactory()
    top = InventoryUnit.objects.create(organization=org, name="Ambulance")
    InventoryUnit.objects.create(organization=org, name="Cabinet", parent=top)
    InventoryUnit.objects.create(organization=org, name="Room")
    # Two top-level units; the cabinet (a sub-unit) does not count.
    assert org.usage("locations") == 2
