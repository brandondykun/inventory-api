import pytest
from django.db import IntegrityError

from apps.inventory.models import Item, UnitOfMeasure, UnitType
from apps.inventory.tests.factories import UnitOfMeasureFactory, UnitTypeFactory
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_unit_type_name_unique_per_org_but_reusable_across_orgs():
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    UnitType.objects.create(organization=org_a, name="Ambulance")
    # Same name in a different org is fine.
    UnitType.objects.create(organization=org_b, name="Ambulance")
    # Duplicate within the same org is rejected.
    with pytest.raises(IntegrityError):
        UnitType.objects.create(organization=org_a, name="Ambulance")


@pytest.mark.django_db
def test_unit_of_measure_name_unique_per_org():
    org = OrganizationFactory()
    UnitOfMeasure.objects.create(organization=org, name="Crate", abbreviation="bx")
    with pytest.raises(IntegrityError):
        UnitOfMeasure.objects.create(organization=org, name="Crate")


@pytest.mark.django_db
def test_str_returns_name():
    ut = UnitTypeFactory(name="Trailer")
    uom = UnitOfMeasureFactory(name="Drum")
    assert str(ut) == "Trailer"
    assert str(uom) == "Drum"


@pytest.mark.django_db
def test_item_defaults_and_flags():
    org = OrganizationFactory()
    item = Item.objects.create(organization=org, name="Bandage")
    assert item.tracks_expiration is False
    assert item.tracks_serial is False
    assert item.expiration_warning_days is None
    assert item.parent is None
    assert str(item) == "Bandage"


@pytest.mark.django_db
def test_item_default_uom_set_null_on_uom_delete():
    org = OrganizationFactory()
    uom = UnitOfMeasure.objects.create(organization=org, name="Each", abbreviation="ea")
    item = Item.objects.create(organization=org, name="Syringe", default_unit_of_measure=uom)
    uom.delete()
    item.refresh_from_db()
    assert item.default_unit_of_measure is None


@pytest.mark.django_db
def test_item_parent_grouping_set_null_on_parent_delete():
    org = OrganizationFactory()
    kit = Item.objects.create(organization=org, name="Trauma Kit")
    child = Item.objects.create(organization=org, name="Gauze", parent=kit)
    assert list(kit.children.all()) == [child]
    kit.delete()
    child.refresh_from_db()
    assert child.parent is None
