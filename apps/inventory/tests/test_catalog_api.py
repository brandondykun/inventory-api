import pytest
from rest_framework.test import APIClient

from apps.inventory.models import UnitOfMeasure, UnitType
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


def ut_list_url(org):
    return f"/api/organizations/{org.id}/unit-types/"


@pytest.mark.django_db
def test_member_can_list_seeded_unit_types(client_for):
    org = OrganizationFactory()
    resp = client_for(org.owner).get(ut_list_url(org))
    assert resp.status_code == 200
    # The 4 seeded defaults, scoped to this org.
    assert resp.data["count"] == 4


@pytest.mark.django_db
def test_admin_can_create_unit_type(client_for):
    org = OrganizationFactory()
    resp = client_for(org.owner).post(ut_list_url(org), {"name": "Trailer"})
    assert resp.status_code == 201
    assert UnitType.objects.filter(organization=org, name="Trailer").exists()


@pytest.mark.django_db
def test_non_member_forbidden(client_for):
    org = OrganizationFactory()
    resp = client_for(UserFactory()).get(ut_list_url(org))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_read_only_member_cannot_create(client_for):
    org = OrganizationFactory()
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)  # role defaults to member
    resp = client_for(member).post(ut_list_url(org), {"name": "Nope"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_cannot_read_another_orgs_unit_types(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    # org_a's owner is not a member of org_b.
    resp = client_for(org_a.owner).get(ut_list_url(org_b))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_unit_of_measure(client_for):
    org = OrganizationFactory()
    url = f"/api/organizations/{org.id}/units-of-measure/"
    resp = client_for(org.owner).post(url, {"name": "Case", "abbreviation": "cs"})
    assert resp.status_code == 201
    assert UnitOfMeasure.objects.filter(organization=org, name="Case").exists()


@pytest.mark.django_db
def test_cannot_retrieve_another_orgs_unit_type_detail(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    foreign_unit_type = UnitType.objects.filter(organization=org_b).first()
    resp = client_for(org_a.owner).get(f"{ut_list_url(org_a)}{foreign_unit_type.id}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_cannot_delete_another_orgs_unit_type_detail(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    foreign_unit_type = UnitType.objects.filter(organization=org_b).first()
    resp = client_for(org_a.owner).delete(f"{ut_list_url(org_a)}{foreign_unit_type.id}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_non_member_forbidden_on_unit_type_detail(client_for):
    org = OrganizationFactory()
    unit_type = UnitType.objects.filter(organization=org).first()
    resp = client_for(UserFactory()).get(f"{ut_list_url(org)}{unit_type.id}/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_cannot_retrieve_another_orgs_uom_detail(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    foreign_uom = UnitOfMeasure.objects.filter(organization=org_b).first()
    url = f"/api/organizations/{org_a.id}/units-of-measure/{foreign_uom.id}/"
    resp = client_for(org_a.owner).get(url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_cannot_delete_another_orgs_uom_detail(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    foreign_uom = UnitOfMeasure.objects.filter(organization=org_b).first()
    url = f"/api/organizations/{org_a.id}/units-of-measure/{foreign_uom.id}/"
    resp = client_for(org_a.owner).delete(url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_non_member_forbidden_on_uom_detail(client_for):
    org = OrganizationFactory()
    uom = UnitOfMeasure.objects.filter(organization=org).first()
    url = f"/api/organizations/{org.id}/units-of-measure/{uom.id}/"
    resp = client_for(UserFactory()).get(url)
    assert resp.status_code == 403
