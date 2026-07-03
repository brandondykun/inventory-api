import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Invite, Membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


def org_invites_url(org):
    return f"/api/organizations/{org.id}/invites/"


def accept_url(invite):
    return f"/api/invites/{invite.id}/accept/"


def decline_url(invite):
    return f"/api/invites/{invite.id}/decline/"


MY_INVITES_URL = "/api/invites/"


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_admin_invites_existing_user(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    invitee = UserFactory()
    resp = client_for(owner).post(org_invites_url(org), {"email": invitee.email, "role": "member"})
    assert resp.status_code == 201
    assert Invite.objects.filter(organization=org, user=invitee, status="pending").exists()


@pytest.mark.django_db
def test_invite_unknown_email_rejected(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    resp = client_for(owner).post(org_invites_url(org), {"email": "nobody@example.com"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_duplicate_pending_invite_rejected(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    invitee = UserFactory()
    Invite.objects.create(organization=org, user=invitee)
    resp = client_for(owner).post(org_invites_url(org), {"email": invitee.email})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_inviting_existing_member_rejected(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(owner).post(org_invites_url(org), {"email": member.email})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_non_admin_cannot_invite(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(member).post(org_invites_url(org), {"email": UserFactory().email})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_invitee_sees_and_accepts_invite(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    invitee = UserFactory()
    invite = Invite.objects.create(organization=org, user=invitee, invited_by=owner)

    listing = client_for(invitee).get(MY_INVITES_URL)
    assert listing.data["count"] == 1

    resp = client_for(invitee).post(accept_url(invite))
    assert resp.status_code == 200
    invite.refresh_from_db()
    assert invite.status == "accepted"
    assert Membership.objects.filter(organization=org, user=invitee).exists()


@pytest.mark.django_db
def test_invitee_declines_invite(client_for):
    org = OrganizationFactory()
    invitee = UserFactory()
    invite = Invite.objects.create(organization=org, user=invitee)
    resp = client_for(invitee).post(decline_url(invite))
    assert resp.status_code == 200
    invite.refresh_from_db()
    assert invite.status == "declined"
    assert not Membership.objects.filter(organization=org, user=invitee).exists()


@pytest.mark.django_db
def test_other_user_cannot_accept_someone_elses_invite(client_for):
    org = OrganizationFactory()
    invitee = UserFactory()
    invite = Invite.objects.create(organization=org, user=invitee)
    resp = client_for(UserFactory()).post(accept_url(invite))
    assert resp.status_code == 404
