import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization, Subscription
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory

LIST_URL = "/api/organizations/"


def detail_url(org):
    return f"/api/organizations/{org.id}/"


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_create_org_makes_owner_admin_with_free_subscription(client_for):
    user = UserFactory()
    resp = client_for(user).post(LIST_URL, {"name": "Acme"})
    assert resp.status_code == 201
    org = Organization.objects.get(id=resp.data["id"])
    assert org.owner == user
    assert Membership.objects.get(organization=org, user=user).role == "admin"
    assert Subscription.objects.get(organization=org).plan.tier == "free"


@pytest.mark.django_db
def test_create_second_free_org_rejected(client_for):
    user = UserFactory()
    OrganizationFactory(owner=user)
    resp = client_for(user).post(LIST_URL, {"name": "Second"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_list_only_returns_my_orgs(client_for):
    user = UserFactory()
    mine = OrganizationFactory(owner=user)
    OrganizationFactory()  # someone else's
    resp = client_for(user).get(LIST_URL)
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.data["results"]]
    assert str(mine.id) in ids
    assert len(ids) == 1


@pytest.mark.django_db
def test_non_member_cannot_retrieve(client_for):
    org = OrganizationFactory()
    resp = client_for(UserFactory()).get(detail_url(org))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_member_can_retrieve_admin_can_update(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)

    assert client_for(member).get(detail_url(org)).status_code == 200
    # member (non-admin) cannot patch
    assert client_for(member).patch(detail_url(org), {"name": "New"}).status_code == 403
    # owner (admin) can patch
    resp = client_for(owner).patch(detail_url(org), {"name": "New"})
    assert resp.status_code == 200
    assert resp.data["name"] == "New"
