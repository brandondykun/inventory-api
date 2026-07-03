import pytest

from apps.organizations.models import Membership, Subscription
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_limit_for_uses_plan_value_then_override():
    org = OrganizationFactory()
    sub = org.subscription
    assert sub.limit_for("members") == 3  # free plan value
    sub.max_members_override = 10
    sub.save(update_fields=["max_members_override"])
    assert sub.limit_for("members") == 10


@pytest.mark.django_db
def test_effective_price_uses_plan_then_override():
    org = OrganizationFactory()
    sub = org.subscription
    assert sub.effective_monthly_price_cents == 0  # free plan price
    sub.monthly_price_cents_override = 1500
    sub.save(update_fields=["monthly_price_cents_override"])
    assert sub.effective_monthly_price_cents == 1500


@pytest.mark.django_db
def test_usage_counts_members():
    org = OrganizationFactory()  # owner membership already exists -> 1
    assert org.usage("members") == 1
    Membership.objects.create(organization=org, user=UserFactory())
    assert org.usage("members") == 2


@pytest.mark.django_db
def test_can_add_members_respects_limit():
    org = OrganizationFactory()  # free: max_members=3, already 1 (owner)
    assert org.can_add("members") is True
    Membership.objects.create(organization=org, user=UserFactory())
    Membership.objects.create(organization=org, user=UserFactory())  # now 3
    assert org.can_add("members") is False


@pytest.mark.django_db
def test_can_add_false_when_no_subscription():
    org = OrganizationFactory()
    org.subscription.delete()
    org.refresh_from_db()
    assert org.can_add("members") is False


@pytest.mark.django_db
def test_can_add_false_when_subscription_inactive():
    org = OrganizationFactory()
    org.subscription.status = Subscription.Status.CANCELED
    org.subscription.save(update_fields=["status"])
    assert org.can_add("members") is False
