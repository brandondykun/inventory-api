import pytest
from django.core.exceptions import ValidationError

from apps.organizations.models import Membership, Plan
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_transfer_requires_membership():
    org = OrganizationFactory()
    outsider = UserFactory()
    with pytest.raises(ValidationError):
        org.transfer_ownership(outsider)


@pytest.mark.django_db
def test_transfer_promotes_member_to_admin_owner():
    org = OrganizationFactory()
    new_owner = UserFactory()
    Membership.objects.create(organization=org, user=new_owner, role=Membership.Role.MEMBER)
    org.transfer_ownership(new_owner)
    org.refresh_from_db()
    assert org.owner == new_owner
    membership = Membership.objects.get(organization=org, user=new_owner)
    assert membership.role == Membership.Role.ADMIN


@pytest.mark.django_db
def test_transfer_free_org_blocked_when_recipient_owns_free_org():
    org = OrganizationFactory()
    recipient = UserFactory()
    Membership.objects.create(organization=org, user=recipient)
    OrganizationFactory(owner=recipient)  # recipient already owns a free org
    with pytest.raises(ValidationError):
        org.transfer_ownership(recipient)


@pytest.mark.django_db
def test_transfer_paid_org_ignores_free_org_rule():
    org = OrganizationFactory()
    pro = Plan.objects.get(tier=Plan.Tier.PRO)
    org.subscription.plan = pro
    org.subscription.save(update_fields=["plan"])
    recipient = UserFactory()
    Membership.objects.create(organization=org, user=recipient)
    OrganizationFactory(owner=recipient)  # recipient owns a free org — allowed
    org.transfer_ownership(recipient)
    org.refresh_from_db()
    assert org.owner == recipient
