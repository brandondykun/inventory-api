import pytest
from rest_framework.test import APIClient

from apps.inventory.models import ParTemplate
from apps.inventory.tests.factories import ParTemplateFactory, ParTemplateItemFactory
from apps.organizations.models import Membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def list_url(org):
    return f"/api/organizations/{org.id}/par-templates/"


def detail_url(org, tmpl):
    return f"/api/organizations/{org.id}/par-templates/{tmpl.id}/"


@pytest.mark.django_db
def test_admin_creates_template(client_for):
    org = OrganizationFactory()
    resp = client_for(org.owner).post(list_url(org), {"name": "Rig A"})
    assert resp.status_code == 201
    assert ParTemplate.objects.filter(organization=org, name="Rig A").exists()


@pytest.mark.django_db
def test_list_defaults_to_active_only(client_for):
    org = OrganizationFactory()
    ParTemplateFactory(organization=org, name="Active", is_active=True)
    ParTemplateFactory(organization=org, name="Retired", is_active=False)
    resp = client_for(org.owner).get(list_url(org))
    assert resp.status_code == 200
    names = [row["name"] for row in resp.data["results"]]
    assert names == ["Active"]


@pytest.mark.django_db
def test_list_is_active_false_and_all(client_for):
    org = OrganizationFactory()
    ParTemplateFactory(organization=org, name="Active", is_active=True)
    ParTemplateFactory(organization=org, name="Retired", is_active=False)
    inactive = client_for(org.owner).get(list_url(org) + "?is_active=false")
    assert [r["name"] for r in inactive.data["results"]] == ["Retired"]
    allrows = client_for(org.owner).get(list_url(org) + "?is_active=all")
    assert allrows.data["count"] == 2


@pytest.mark.django_db
def test_detail_includes_nested_lines(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org)
    ParTemplateItemFactory(template=tmpl)
    resp = client_for(org.owner).get(detail_url(org, tmpl))
    assert resp.status_code == 200
    assert len(resp.data["lines"]) == 1
    assert "par_quantity" in resp.data["lines"][0]


@pytest.mark.django_db
def test_patch_edits_header_ignores_lines(client_for):
    org = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=org, name="Old")
    resp = client_for(org.owner).patch(
        detail_url(org, tmpl), {"name": "New", "lines": []}, format="json"
    )
    assert resp.status_code == 200
    tmpl.refresh_from_db()
    assert tmpl.name == "New"


@pytest.mark.django_db
def test_member_reads_admin_writes(client_for):
    org = OrganizationFactory()
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    assert client_for(member).get(list_url(org)).status_code == 200
    assert client_for(member).post(list_url(org), {"name": "X"}).status_code == 403


@pytest.mark.django_db
def test_non_member_and_cross_org(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    tmpl = ParTemplateFactory(organization=other)
    assert client_for(UserFactory()).get(list_url(org)).status_code == 403
    # org.owner is not a member of `other`, requesting other's template under other's org
    assert client_for(org.owner).get(detail_url(other, tmpl)).status_code == 403
