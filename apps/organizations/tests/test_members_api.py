import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


def list_url(org):
    return f"/api/organizations/{org.id}/members/"


def detail_url(org, user):
    return f"/api/organizations/{org.id}/members/{user.id}/"


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_member_can_list_members(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(member).get(list_url(org))
    assert resp.status_code == 200
    assert resp.data["count"] == 2


@pytest.mark.django_db
def test_admin_can_change_member_role(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(owner).patch(detail_url(org, member), {"role": "admin"})
    assert resp.status_code == 200
    assert Membership.objects.get(organization=org, user=member).role == "admin"


@pytest.mark.django_db
def test_non_admin_cannot_change_role(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(member).patch(detail_url(org, member), {"role": "admin"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_admin_can_remove_member(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(owner).delete(detail_url(org, member))
    assert resp.status_code == 204
    assert not Membership.objects.filter(organization=org, user=member).exists()


@pytest.mark.django_db
def test_owner_cannot_be_removed_or_demoted(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    assert client_for(owner).delete(detail_url(org, owner)).status_code == 400
    assert client_for(owner).patch(detail_url(org, owner), {"role": "member"}).status_code == 400
