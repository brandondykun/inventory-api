"""Lifecycle signals for the organizations app."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Membership, Organization, Plan, Subscription


@receiver(post_save, sender=Organization)
def seed_organization_owner_and_subscription(sender, instance, created, **kwargs):
    """On creation, make the owner an admin member and attach a free
    subscription so entitlement checks always have something to read.

    Guarded on ``created`` so later saves (e.g. ownership transfer) are no-ops.
    ``get_or_create`` keeps it idempotent if the objects already exist.
    """
    if not created:
        return

    Membership.objects.get_or_create(
        organization=instance,
        user=instance.owner,
        defaults={"role": Membership.Role.ADMIN},
    )
    Subscription.objects.get_or_create(
        organization=instance,
        defaults={
            "plan": Plan.objects.get(tier=Plan.Tier.FREE),
            "status": Subscription.Status.ACTIVE,
        },
    )
