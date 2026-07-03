import pytest

from apps.inventory.models import UnitOfMeasure, UnitType
from apps.inventory.signals import DEFAULT_UNIT_TYPES, DEFAULT_UNITS_OF_MEASURE
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_new_org_is_seeded_with_defaults():
    org = OrganizationFactory()
    assert UnitType.objects.filter(organization=org).count() == len(DEFAULT_UNIT_TYPES)
    assert UnitOfMeasure.objects.filter(organization=org).count() == len(DEFAULT_UNITS_OF_MEASURE)
    names = set(UnitType.objects.filter(organization=org).values_list("name", flat=True))
    assert "Vehicle" in names


@pytest.mark.django_db
def test_seeding_is_scoped_per_org():
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    # Each org gets its own independent copies.
    assert UnitType.objects.filter(organization=org_a).count() == len(DEFAULT_UNIT_TYPES)
    assert UnitType.objects.filter(organization=org_b).count() == len(DEFAULT_UNIT_TYPES)


@pytest.mark.django_db
def test_saving_existing_org_does_not_reseed():
    org = OrganizationFactory()
    before = UnitType.objects.filter(organization=org).count()
    org.name = "Renamed"
    org.save()
    assert UnitType.objects.filter(organization=org).count() == before
