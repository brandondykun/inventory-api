import uuid

import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


def url(org):
    return f"/api/organizations/{org.id}/transfer-ownership/"


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_owner_transfers_to_member(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)

    resp = client_for(owner).post(url(org), {"new_owner": str(member.id)})
    assert resp.status_code == 200
    org.refresh_from_db()
    assert org.owner == member


@pytest.mark.django_db
def test_non_owner_cannot_transfer(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    admin = UserFactory()
    Membership.objects.create(organization=org, user=admin, role=Membership.Role.ADMIN)
    resp = client_for(admin).post(url(org), {"new_owner": str(admin.id)})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_transfer_to_non_member_returns_400(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    outsider = UserFactory()
    resp = client_for(owner).post(url(org), {"new_owner": str(outsider.id)})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_transfer_with_non_uuid_new_owner_returns_400(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    resp = client_for(owner).post(url(org), {"new_owner": "not-a-uuid"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_transfer_with_missing_new_owner_returns_400(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    resp = client_for(owner).post(url(org), {})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_transfer_with_nonexistent_new_owner_returns_400(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    resp = client_for(owner).post(url(org), {"new_owner": str(uuid.uuid4())})
    assert resp.status_code == 400
