"""Lifecycle signals for the inventory app.

Gives every new organization its own editable copies of the default unit types
and units of measure. Defaults are copied as per-org rows (not shared globally)
so an org can rename, delete, or extend the lists without affecting anyone else.
Edit the canonical lists here.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.organizations.models import Organization

from .models import UnitOfMeasure, UnitType

DEFAULT_UNIT_TYPES = [
    ("Vehicle", "A vehicle that carries inventory"),
    ("Room", "A room within a building"),
    ("Storage room", "A dedicated storage room"),
    ("Storage cage", "A secured storage cage"),
]

DEFAULT_UNITS_OF_MEASURE = [
    ("Individual", "ea"),
    ("Box", "bx"),
    ("Bag", "bag"),
    ("Pallet", "plt"),
]


@receiver(post_save, sender=Organization)
def seed_organization_defaults(sender, instance, created, **kwargs):
    """On org creation, bulk-create its default unit types and units of measure.

    Guarded on ``created`` so saves to an existing org are a no-op. Coexists with
    the organizations app's own post_save receiver (owner membership + free
    subscription); the two are independent and order-agnostic.
    """
    if not created:
        return

    UnitType.objects.bulk_create(
        [
            UnitType(organization=instance, name=name, description=description)
            for name, description in DEFAULT_UNIT_TYPES
        ]
    )
    UnitOfMeasure.objects.bulk_create(
        [
            UnitOfMeasure(organization=instance, name=name, abbreviation=abbreviation)
            for name, abbreviation in DEFAULT_UNITS_OF_MEASURE
        ]
    )
