import pytest
from rest_framework.test import APIClient

from apps.inventory.models import Item, UnitOfMeasure
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def items_url(org):
    return f"/api/organizations/{org.id}/items/"


@pytest.mark.django_db
def test_admin_creates_item_with_default_uom(client_for):
    org = OrganizationFactory()
    uom = UnitOfMeasure.objects.filter(organization=org).first()
    resp = client_for(org.owner).post(
        items_url(org),
        {"name": "Saline", "default_unit_of_measure": str(uom.id)},
    )
    assert resp.status_code == 201
    item = Item.objects.get(id=resp.data["id"])
    assert item.organization == org
    assert item.default_unit_of_measure == uom


@pytest.mark.django_db
def test_cannot_use_another_orgs_uom_as_default(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    foreign_uom = UnitOfMeasure.objects.filter(organization=other).first()
    resp = client_for(org.owner).post(
        items_url(org),
        {"name": "Saline", "default_unit_of_measure": str(foreign_uom.id)},
    )
    assert resp.status_code == 400
    assert "default_unit_of_measure" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_cannot_parent_item_to_another_orgs_item(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    foreign_item = Item.objects.create(organization=other, name="Foreign Kit")
    resp = client_for(org.owner).post(
        items_url(org),
        {"name": "Gauze", "parent": str(foreign_item.id)},
    )
    assert resp.status_code == 400
    assert "parent" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_list_scoped_to_org(client_for):
    org = OrganizationFactory()
    Item.objects.create(organization=org, name="Mine")
    Item.objects.create(organization=OrganizationFactory(), name="Theirs")
    resp = client_for(org.owner).get(items_url(org))
    assert resp.status_code == 200
    names = [row["name"] for row in resp.data["results"]]
    assert names == ["Mine"]


@pytest.mark.django_db
def test_cannot_retrieve_another_orgs_item_detail(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    foreign_item = Item.objects.create(organization=org_b, name="Theirs")
    resp = client_for(org_a.owner).get(f"{items_url(org_a)}{foreign_item.id}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_cannot_delete_another_orgs_item_detail(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    foreign_item = Item.objects.create(organization=org_b, name="Theirs")
    resp = client_for(org_a.owner).delete(f"{items_url(org_a)}{foreign_item.id}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_non_member_forbidden_on_item_detail(client_for):
    org = OrganizationFactory()
    item = Item.objects.create(organization=org, name="Mine")
    resp = client_for(UserFactory()).get(f"{items_url(org)}{item.id}/")
    assert resp.status_code == 403
