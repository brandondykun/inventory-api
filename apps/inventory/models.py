"""Models for the inventory app: catalog (unit types, units of measure, items)
and the physical location tree (inventory units)."""

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import BaseModel
from apps.organizations.models import Organization, Subscription


class UnitType(BaseModel):
    """Category of location (vehicle, room, storage cage...). Seeded per org and
    freely editable — orgs may rename, delete, or add their own."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="unit_types"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class UnitOfMeasure(BaseModel):
    """How quantities are counted (individual, box, bag...). Seeded per org and
    freely editable."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="units_of_measure"
    )
    name = models.CharField(max_length=50)
    abbreviation = models.CharField(max_length=10, blank=True)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Item(BaseModel):
    """Catalog definition of something that can be inventoried (the "what").
    Physical stock and expiration live on StockLot (a later slice), not here."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    sku = models.CharField(max_length=100, blank=True)
    default_unit_of_measure = models.ForeignKey(
        UnitOfMeasure,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="items",
    )
    tracks_expiration = models.BooleanField(default=False)
    tracks_serial = models.BooleanField(default=False)
    # Days before expiry to start warning; falls back to an org default when
    # null (consumed by the alert engine in a later slice).
    expiration_warning_days = models.PositiveIntegerField(null=True, blank=True)
    # Optional grouping/containment, e.g. a kit/bag that contains other items.
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InventoryUnit(BaseModel):
    """A place that holds inventory: a vehicle, room, cage, pantry, etc. May be
    nested via ``parent`` to arbitrary depth so a location can be subdivided
    (an ambulance into cabinets; a storage room by cabinet). Any unit — parent
    or child — may hold stock in a later slice."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="units")
    unit_type = models.ForeignKey(
        UnitType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="units",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    par_template = models.ForeignKey(
        "ParTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="units",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def root(self):
        """The top-level ancestor (itself if it has no parent)."""
        node = self
        while node.parent_id is not None:
            node = node.parent
        return node

    def _descendant_count(self):
        """Number of units anywhere beneath this one."""
        total = 0
        for child in self.children.all():
            total += 1 + child._descendant_count()
        return total

    def subtree_size(self):
        """Number of units in this unit's subtree, including itself."""
        return 1 + self._descendant_count()

    def can_add_subdivision(self, adding=1):
        """Whether ``adding`` more sub-units may be placed beneath this unit's
        top-level root under the org's plan. ``self`` is the intended parent.

        Counts the whole subtree under the root, so nesting depth doesn't matter.
        Returns False when the org has no subscription; True when the plan's
        subdivisions limit is null (unlimited).
        """
        try:
            sub = self.organization.subscription
        except Subscription.DoesNotExist:
            return False
        limit = sub.limit_for("subdivisions")
        if limit is None:
            return True
        return self.root._descendant_count() + adding <= limit

    def clean(self):
        """Reject parent assignments that would create a cycle (a unit being
        its own ancestor)."""
        if self.parent_id is None:
            return
        if self.parent_id == self.id:
            raise ValidationError({"parent": "A unit cannot be its own parent."})
        ancestor = self.parent
        while ancestor is not None:
            if ancestor.id == self.id:
                raise ValidationError(
                    {"parent": "A unit cannot be nested under its own descendant."}
                )
            ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class ParTemplate(BaseModel):
    """The ideal set of items and counts for a unit (the "should-be"). Owned by
    the org and assignable to many units (e.g. a whole fleet)."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="par_templates"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ParTemplateItem(BaseModel):
    """One line of a par template: an item and its target quantity."""

    template = models.ForeignKey(ParTemplate, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="par_lines")
    par_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    min_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, related_name="par_lines"
    )

    class Meta:
        unique_together = ("template", "item")
        ordering = ["item__name"]

    def __str__(self):
        return f"{self.item}: {self.par_quantity} {self.unit_of_measure}"
