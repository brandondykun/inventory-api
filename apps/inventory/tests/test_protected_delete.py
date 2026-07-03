import pytest
from rest_framework.test import APIClient

from apps.inventory.models import Item, UnitOfMeasure
from apps.inventory.tests.factories import (
    ItemFactory,
    ParTemplateItemFactory,
    UnitOfMeasureFactory,
)
from apps.organizations.tests.factories import OrganizationFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_delete_item_referenced_by_par_line_returns_409(client_for):
    org = OrganizationFactory()
    line = ParTemplateItemFactory(
        template__organization=org,
        item=ItemFactory(organization=org),
        unit_of_measure=UnitOfMeasureFactory(organization=org),
    )
    url = f"/api/organizations/{org.id}/items/{line.item.id}/"
    resp = client_for(org.owner).delete(url)
    assert resp.status_code == 409
    assert Item.objects.filter(pk=line.item.id).exists()


@pytest.mark.django_db
def test_delete_uom_referenced_by_par_line_returns_409(client_for):
    org = OrganizationFactory()
    line = ParTemplateItemFactory(
        template__organization=org,
        item=ItemFactory(organization=org),
        unit_of_measure=UnitOfMeasureFactory(organization=org),
    )
    url = f"/api/organizations/{org.id}/units-of-measure/{line.unit_of_measure.id}/"
    resp = client_for(org.owner).delete(url)
    assert resp.status_code == 409
    assert UnitOfMeasure.objects.filter(pk=line.unit_of_measure.id).exists()


@pytest.mark.django_db
def test_delete_unreferenced_item_still_204(client_for):
    org = OrganizationFactory()
    item = ItemFactory(organization=org)
    url = f"/api/organizations/{org.id}/items/{item.id}/"
    resp = client_for(org.owner).delete(url)
    assert resp.status_code == 204
    assert not Item.objects.filter(pk=item.id).exists()
