import pytest
from django.core.exceptions import ValidationError

from apps.inventory.models import InventoryUnit
from apps.organizations.models import Plan
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_root_resolves_top_level_ancestor():
    org = OrganizationFactory()
    ambulance = InventoryUnit.objects.create(organization=org, name="Medic 1")
    cabinet = InventoryUnit.objects.create(organization=org, name="Cabinet A", parent=ambulance)
    drawer = InventoryUnit.objects.create(organization=org, name="Drawer 1", parent=cabinet)
    assert drawer.root == ambulance
    assert ambulance.root == ambulance


@pytest.mark.django_db
def test_subtree_and_descendant_counts():
    org = OrganizationFactory()
    ambulance = InventoryUnit.objects.create(organization=org, name="Medic 1")
    cab_a = InventoryUnit.objects.create(organization=org, name="Cab A", parent=ambulance)
    InventoryUnit.objects.create(organization=org, name="Cab B", parent=ambulance)
    InventoryUnit.objects.create(organization=org, name="Drawer", parent=cab_a)
    assert ambulance._descendant_count() == 3
    assert ambulance.subtree_size() == 4


@pytest.mark.django_db
def test_cannot_be_its_own_parent():
    org = OrganizationFactory()
    unit = InventoryUnit.objects.create(organization=org, name="Room")
    unit.parent = unit
    with pytest.raises(ValidationError):
        unit.save()


@pytest.mark.django_db
def test_cannot_nest_under_own_descendant():
    org = OrganizationFactory()
    parent = InventoryUnit.objects.create(organization=org, name="Room")
    child = InventoryUnit.objects.create(organization=org, name="Cabinet", parent=parent)
    parent.parent = child  # would create a cycle
    with pytest.raises(ValidationError):
        parent.save()


@pytest.mark.django_db
def test_delete_cascades_to_subunits():
    org = OrganizationFactory()
    ambulance = InventoryUnit.objects.create(organization=org, name="Medic 1")
    InventoryUnit.objects.create(organization=org, name="Cabinet", parent=ambulance)
    ambulance.delete()
    assert InventoryUnit.objects.filter(organization=org).count() == 0


@pytest.mark.django_db
def test_can_add_subdivision_respects_free_limit():
    org = OrganizationFactory()  # free plan → max_subdivisions = 5
    root = InventoryUnit.objects.create(organization=org, name="Ambulance")
    # Add 5 sub-units; the 6th should be disallowed.
    for i in range(5):
        assert root.can_add_subdivision() is True
        InventoryUnit.objects.create(organization=org, name=f"Cab {i}", parent=root)
    assert root.can_add_subdivision() is False


@pytest.mark.django_db
def test_can_add_subdivision_counts_whole_subtree():
    org = OrganizationFactory()
    root = InventoryUnit.objects.create(organization=org, name="Ambulance")
    cab = InventoryUnit.objects.create(organization=org, name="Cab", parent=root)
    # Nested sub-units count against the same root.
    for i in range(4):
        InventoryUnit.objects.create(organization=org, name=f"Drawer {i}", parent=cab)
    # root subtree now has 5 descendants → at the limit.
    assert cab.can_add_subdivision() is False
    assert root.can_add_subdivision() is False


@pytest.mark.django_db
def test_can_add_subdivision_unlimited_when_limit_null():
    org = OrganizationFactory()
    sub = org.subscription
    sub.plan = Plan.objects.get(tier=Plan.Tier.ENTERPRISE)  # max_subdivisions = None
    sub.save()
    root = InventoryUnit.objects.create(organization=org, name="Warehouse")
    for i in range(10):
        InventoryUnit.objects.create(organization=org, name=f"Aisle {i}", parent=root)
    assert root.can_add_subdivision() is True
