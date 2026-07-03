import pytest

from apps.organizations.models import Membership, Plan, Subscription
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_owner_becomes_admin_member_on_create():
    org = OrganizationFactory()
    membership = Membership.objects.get(organization=org, user=org.owner)
    assert membership.role == Membership.Role.ADMIN


@pytest.mark.django_db
def test_free_subscription_created_on_create():
    org = OrganizationFactory()
    sub = Subscription.objects.get(organization=org)
    assert sub.plan.tier == Plan.Tier.FREE
    assert sub.status == Subscription.Status.ACTIVE
