import pytest
from rest_framework.test import APIClient

from apps.inventory.models import InventoryUnit
from apps.organizations.models import Plan
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def units_url(org):
    return f"/api/organizations/{org.id}/units/"


@pytest.mark.django_db
def test_create_top_level_unit(client_for):
    org = OrganizationFactory()
    resp = client_for(org.owner).post(units_url(org), {"name": "Ambulance"})
    assert resp.status_code == 201
    assert InventoryUnit.objects.get(id=resp.data["id"]).parent_id is None


@pytest.mark.django_db
def test_create_sub_unit(client_for):
    org = OrganizationFactory()
    parent = InventoryUnit.objects.create(organization=org, name="Ambulance")
    resp = client_for(org.owner).post(units_url(org), {"name": "Cabinet", "parent": str(parent.id)})
    assert resp.status_code == 201
    assert InventoryUnit.objects.get(id=resp.data["id"]).parent_id == parent.id


@pytest.mark.django_db
def test_subdivisions_cap_enforced_on_free(client_for):
    org = OrganizationFactory()  # free → max_subdivisions = 5
    parent = InventoryUnit.objects.create(organization=org, name="Ambulance")
    for i in range(5):
        InventoryUnit.objects.create(organization=org, name=f"Cab {i}", parent=parent)
    resp = client_for(org.owner).post(units_url(org), {"name": "Cab 6", "parent": str(parent.id)})
    assert resp.status_code == 400
    assert "parent" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_subdivisions_unlimited_on_enterprise(client_for):
    org = OrganizationFactory()
    sub = org.subscription
    sub.plan = Plan.objects.get(tier=Plan.Tier.ENTERPRISE)
    sub.save()
    parent = InventoryUnit.objects.create(organization=org, name="Warehouse")
    for i in range(6):
        resp = client_for(org.owner).post(
            units_url(org), {"name": f"Aisle {i}", "parent": str(parent.id)}
        )
        assert resp.status_code == 201


@pytest.mark.django_db
def test_cannot_parent_to_another_orgs_unit(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    foreign = InventoryUnit.objects.create(organization=other, name="Foreign")
    resp = client_for(org.owner).post(
        units_url(org), {"name": "Cabinet", "parent": str(foreign.id)}
    )
    assert resp.status_code == 400
    assert "parent" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_reparent_under_own_descendant_rejected(client_for):
    org = OrganizationFactory()
    parent = InventoryUnit.objects.create(organization=org, name="Room")
    child = InventoryUnit.objects.create(organization=org, name="Cabinet", parent=parent)
    resp = client_for(org.owner).patch(f"{units_url(org)}{parent.id}/", {"parent": str(child.id)})
    assert resp.status_code == 400
    assert "parent" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_cannot_retrieve_another_orgs_unit_detail(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    foreign_unit = InventoryUnit.objects.create(organization=org_b, name="Theirs")
    resp = client_for(org_a.owner).get(f"{units_url(org_a)}{foreign_unit.id}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_cannot_delete_another_orgs_unit_detail(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    foreign_unit = InventoryUnit.objects.create(organization=org_b, name="Theirs")
    resp = client_for(org_a.owner).delete(f"{units_url(org_a)}{foreign_unit.id}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_non_member_forbidden_on_unit_detail(client_for):
    org = OrganizationFactory()
    unit = InventoryUnit.objects.create(organization=org, name="Mine")
    resp = client_for(UserFactory()).get(f"{units_url(org)}{unit.id}/")
    assert resp.status_code == 403
