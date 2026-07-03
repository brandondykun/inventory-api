import pytest
from rest_framework.test import APIClient

from apps.inventory.models import ParTemplateItem
from apps.inventory.tests.factories import (
    ItemFactory,
    ParTemplateFactory,
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


def lines_url(org, tmpl):
    return f"/api/organizations/{org.id}/par-templates/{tmpl.id}/lines/"


@pytest.mark.django_db
def test_add_line(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    item = ItemFactory(organization=org)
    uom = UnitOfMeasureFactory(organization=org)
    resp = client_for(org.owner).post(
        lines_url(org, tmpl),
        {"item": str(item.id), "par_quantity": "5.00", "unit_of_measure": str(uom.id)},
    )
    assert resp.status_code == 201
    assert ParTemplateItem.objects.filter(template=tmpl, item=item).exists()


@pytest.mark.django_db
def test_cross_org_item_rejected(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    foreign_item = ItemFactory(organization=OrganizationFactory())
    uom = UnitOfMeasureFactory(organization=org)
    resp = client_for(org.owner).post(
        lines_url(org, tmpl),
        {"item": str(foreign_item.id), "par_quantity": "1", "unit_of_measure": str(uom.id)},
    )
    assert resp.status_code == 400
    assert "item" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_cross_org_uom_rejected(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    item = ItemFactory(organization=org)
    foreign_uom = UnitOfMeasureFactory(organization=OrganizationFactory())
    resp = client_for(org.owner).post(
        lines_url(org, tmpl),
        {"item": str(item.id), "par_quantity": "1", "unit_of_measure": str(foreign_uom.id)},
    )
    assert resp.status_code == 400
    assert "unit_of_measure" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_negative_par_and_min_gt_par_rejected(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    item = ItemFactory(organization=org)
    uom = UnitOfMeasureFactory(organization=org)
    neg = client_for(org.owner).post(
        lines_url(org, tmpl),
        {"item": str(item.id), "par_quantity": "-1", "unit_of_measure": str(uom.id)},
    )
    assert neg.status_code == 400
    assert "par_quantity" in neg.data["error"]["detail"]
    bad_min = client_for(org.owner).post(
        lines_url(org, tmpl),
        {
            "item": str(item.id),
            "par_quantity": "5",
            "min_quantity": "9",
            "unit_of_measure": str(uom.id),
        },
    )
    assert bad_min.status_code == 400
    assert "min_quantity" in bad_min.data["error"]["detail"]


@pytest.mark.django_db
def test_negative_min_rejected(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    item = ItemFactory(organization=org)
    uom = UnitOfMeasureFactory(organization=org)
    resp = client_for(org.owner).post(
        lines_url(org, tmpl),
        {
            "item": str(item.id),
            "par_quantity": "5",
            "min_quantity": "-1",
            "unit_of_measure": str(uom.id),
        },
    )
    assert resp.status_code == 400
    assert "min_quantity" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_duplicate_line_rejected(client_for):
    org = OrganizationFactory()
    line = ParTemplateItemFactory(template=ParTemplateFactory(organization=org))
    resp = client_for(org.owner).post(
        lines_url(org, line.template),
        {
            "item": str(line.item.id),
            "par_quantity": "3",
            "unit_of_measure": str(line.unit_of_measure.id),
        },
    )
    assert resp.status_code == 400
    assert "item" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_lines_scoped_to_template_and_org(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    ParTemplateItemFactory(template=tmpl)
    # A template belonging to another org is not reachable under this org.
    foreign_tmpl = ParTemplateFactory(organization=other)
    resp = client_for(org.owner).get(lines_url(org, foreign_tmpl))
    assert resp.status_code == 404
