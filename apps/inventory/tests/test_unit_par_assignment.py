import pytest
from rest_framework.test import APIClient

from apps.inventory.tests.factories import InventoryUnitFactory, ParTemplateFactory
from apps.organizations.tests.factories import OrganizationFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def unit_detail(org, unit):
    return f"/api/organizations/{org.id}/units/{unit.id}/"


@pytest.mark.django_db
def test_assign_and_clear_par_template(client_for):
    org = OrganizationFactory()
    unit = InventoryUnitFactory(organization=org)
    tmpl = ParTemplateFactory(organization=org)
    assign = client_for(org.owner).patch(unit_detail(org, unit), {"par_template": str(tmpl.id)})
    assert assign.status_code == 200
    unit.refresh_from_db()
    assert unit.par_template_id == tmpl.id
    clear = client_for(org.owner).patch(
        unit_detail(org, unit), {"par_template": None}, format="json"
    )
    assert clear.status_code == 200
    unit.refresh_from_db()
    assert unit.par_template_id is None


@pytest.mark.django_db
def test_cannot_assign_inactive_template(client_for):
    org = OrganizationFactory()
    unit = InventoryUnitFactory(organization=org)
    inactive = ParTemplateFactory(organization=org, is_active=False)
    resp = client_for(org.owner).patch(unit_detail(org, unit), {"par_template": str(inactive.id)})
    assert resp.status_code == 400
    assert "par_template" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_cannot_assign_other_orgs_template(client_for):
    org = OrganizationFactory()
    unit = InventoryUnitFactory(organization=org)
    foreign = ParTemplateFactory(organization=OrganizationFactory())
    resp = client_for(org.owner).patch(unit_detail(org, unit), {"par_template": str(foreign.id)})
    assert resp.status_code == 400
    assert "par_template" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_deleting_template_detaches_unit(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    unit = InventoryUnitFactory(organization=org, par_template=tmpl)
    tmpl.delete()
    unit.refresh_from_db()
    assert unit.par_template_id is None
