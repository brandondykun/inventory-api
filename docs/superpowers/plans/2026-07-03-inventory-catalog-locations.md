# Inventory App — Slice 2a: Catalog & Locations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `inventory` app's catalog (`UnitType`, `UnitOfMeasure`, `Item`) and nested physical-location tree (`InventoryUnit`), with per-org default seeding and a metered per-location subdivisions cap, exposed via org-scoped CRUD APIs.

**Architecture:** A new `apps/inventory` Django app whose models inherit `apps.common.models.BaseModel` (UUID pk + timestamps). It reuses the `organizations` app's permission classes and error/pagination conventions, and fills the `Organization.usage("locations")` / `usage("items")` hooks the org app already declared. A `post_save` receiver seeds each new org's editable default unit types / units of measure. The org app's entitlement model gains a `max_subdivisions` dimension; top-level units meter against `max_locations`, sub-units against a per-location `max_subdivisions` cap (Free = 5), enforced at write time.

**Tech Stack:** Django, Django REST Framework, pytest + pytest-django, factory_boy, PostgreSQL, Docker Compose, ruff.

## Global Constraints

- All new models inherit `apps.common.models.BaseModel` (UUID pk, `created_at`, `updated_at`). No integer pks, no hand-rolled timestamp fields.
- All list endpoints paginate an **explicitly ordered** queryset (every model defines `Meta.ordering`) to avoid `UnorderedObjectListWarning` and non-deterministic paging.
- API errors flow through the existing `apps.common.exceptions.api_exception_handler` envelope; lists use `apps.common.pagination.StandardResultsSetPagination` (configured globally).
- Endpoints are nested under the org and reuse `apps.organizations.permissions.IsOrgMember` (read) / `IsOrgAdmin` (write), which resolve the org from `view.kwargs["org_id"]`.
- Everything is org-scoped: every queryset is filtered to the URL's `org_id`; every FK choice (`unit_type`, `default_unit_of_measure`, `parent`) must belong to the same org, validated in the serializer.
- Tests run via `./scripts/test.sh <pytest args>` (test stack, `config.settings.test`). Migrations are generated via `./scripts/manage.sh makemigrations <app>`.
- Lint/format before each commit: `uv run ruff check apps/inventory apps/organizations && uv run ruff format apps/inventory apps/organizations`.
- Commit **only the app-code/spec changes listed in each task's final step is prepared for the user; DO NOT run `git commit` for app code — stage nothing and let the user commit** (repo rule). The plan's "Commit" steps below describe the intended commit for the user; the worker should surface the diff, not commit it. (Spec/plan docs may be committed by the agent.)
- Every new `Organization` created in a test triggers **two** `post_save` receivers: the org app's (owner membership + free subscription) and this app's seeding receiver (4 default unit types + 4 default units of measure). Test assertions must scope counts by `organization` rather than asserting global table counts.

---

### Task 1: Scaffold the `inventory` app + catalog models (`UnitType`, `UnitOfMeasure`)

**Files:**
- Create: `apps/inventory/__init__.py`
- Create: `apps/inventory/apps.py`
- Create: `apps/inventory/models.py`
- Create: `apps/inventory/tests/__init__.py`
- Create: `apps/inventory/tests/factories.py`
- Create: `apps/inventory/tests/test_models.py`
- Modify: `config/settings/base.py:77-82` (add `apps.inventory` to `LOCAL_APPS`)
- Create (generated): `apps/inventory/migrations/0001_initial.py` (+ `migrations/__init__.py`)

**Interfaces:**
- Produces: `apps.inventory.models.UnitType(organization, name, description)` and `apps.inventory.models.UnitOfMeasure(organization, name, abbreviation)`, both with `unique_together=("organization", "name")` and `ordering=["name"]`. Reverse relations: `Organization.unit_types`, `Organization.units_of_measure`.
- Produces test factories `UnitTypeFactory`, `UnitOfMeasureFactory` in `apps.inventory.tests.factories`.

- [ ] **Step 1: Register the app in settings**

Modify `config/settings/base.py` `LOCAL_APPS` (currently ends at `"apps.organizations",`):

```python
LOCAL_APPS = [
    "apps.common",
    "apps.users",
    "apps.authentication",
    "apps.organizations",
    "apps.inventory",
]
```

(Match the exact existing entries; only add the final `"apps.inventory",` line.)

- [ ] **Step 2: Create the app package + config**

`apps/inventory/__init__.py` — empty file.

`apps/inventory/apps.py`:

```python
from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inventory"

    def ready(self):
        from . import signals  # noqa: F401
```

Note: `signals` is imported in `ready()` now but the module is not created until Task 4. To keep Tasks 1–3 runnable, create a placeholder `apps/inventory/signals.py` containing only a module docstring for now:

```python
"""Lifecycle signals for the inventory app. (Populated in Task 4.)"""
```

- [ ] **Step 3: Write the catalog models**

`apps/inventory/models.py`:

```python
"""Models for the inventory app: catalog (unit types, units of measure, items)
and the physical location tree (inventory units)."""

from django.db import models

from apps.common.models import BaseModel
from apps.organizations.models import Organization


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
```

- [ ] **Step 4: Create test factories**

`apps/inventory/tests/__init__.py` — empty file.

`apps/inventory/tests/factories.py`:

```python
"""Test factories for the inventory app."""

import factory

from apps.inventory.models import UnitOfMeasure, UnitType
from apps.organizations.tests.factories import OrganizationFactory


class UnitTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UnitType

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Unit Type {n}")


class UnitOfMeasureFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UnitOfMeasure

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Unit {n}")
    abbreviation = "ea"
```

- [ ] **Step 5: Write the failing model tests**

`apps/inventory/tests/test_models.py`:

```python
import pytest
from django.db import IntegrityError

from apps.inventory.models import UnitOfMeasure, UnitType
from apps.inventory.tests.factories import UnitOfMeasureFactory, UnitTypeFactory
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_unit_type_name_unique_per_org_but_reusable_across_orgs():
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    UnitType.objects.create(organization=org_a, name="Vehicle")
    # Same name in a different org is fine.
    UnitType.objects.create(organization=org_b, name="Vehicle")
    # Duplicate within the same org is rejected.
    with pytest.raises(IntegrityError):
        UnitType.objects.create(organization=org_a, name="Vehicle")


@pytest.mark.django_db
def test_unit_of_measure_name_unique_per_org():
    org = OrganizationFactory()
    UnitOfMeasure.objects.create(organization=org, name="Box", abbreviation="bx")
    with pytest.raises(IntegrityError):
        UnitOfMeasure.objects.create(organization=org, name="Box")


@pytest.mark.django_db
def test_str_returns_name():
    ut = UnitTypeFactory(name="Room")
    uom = UnitOfMeasureFactory(name="Pallet")
    assert str(ut) == "Room"
    assert str(uom) == "Pallet"
```

- [ ] **Step 6: Generate the migration**

Run: `./scripts/manage.sh makemigrations inventory --name initial`
Expected: creates `apps/inventory/migrations/0001_initial.py` with `UnitType` and `UnitOfMeasure`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_models.py -v`
Expected: 3 passed. (The test DB is built from migrations, so Step 6 must be done first.)

- [ ] **Step 8: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit (leave for the user to run):

```bash
git add apps/inventory config/settings/base.py
git commit -m "feat: scaffold inventory app with unit type and unit of measure models"
```

---

### Task 2: `Item` model

**Files:**
- Modify: `apps/inventory/models.py` (add `Item`)
- Modify: `apps/inventory/tests/factories.py` (add `ItemFactory`)
- Modify: `apps/inventory/tests/test_models.py` (add Item tests)
- Create (generated): `apps/inventory/migrations/0002_item.py`

**Interfaces:**
- Consumes: `UnitOfMeasure` (Task 1).
- Produces: `apps.inventory.models.Item(organization, name, description, sku, default_unit_of_measure, tracks_expiration, tracks_serial, expiration_warning_days, parent)`. Reverse relations: `Organization.items`, `UnitOfMeasure.items`, `Item.children`. `ordering=["name"]`.
- Produces: `ItemFactory`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/inventory/tests/test_models.py`:

```python
from apps.inventory.models import Item  # add to existing imports at top


@pytest.mark.django_db
def test_item_defaults_and_flags():
    org = OrganizationFactory()
    item = Item.objects.create(organization=org, name="Bandage")
    assert item.tracks_expiration is False
    assert item.tracks_serial is False
    assert item.expiration_warning_days is None
    assert item.parent is None
    assert str(item) == "Bandage"


@pytest.mark.django_db
def test_item_default_uom_set_null_on_uom_delete():
    org = OrganizationFactory()
    uom = UnitOfMeasure.objects.create(organization=org, name="Each", abbreviation="ea")
    item = Item.objects.create(
        organization=org, name="Syringe", default_unit_of_measure=uom
    )
    uom.delete()
    item.refresh_from_db()
    assert item.default_unit_of_measure is None


@pytest.mark.django_db
def test_item_parent_grouping_set_null_on_parent_delete():
    org = OrganizationFactory()
    kit = Item.objects.create(organization=org, name="Trauma Kit")
    child = Item.objects.create(organization=org, name="Gauze", parent=kit)
    assert list(kit.children.all()) == [child]
    kit.delete()
    child.refresh_from_db()
    assert child.parent is None
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_models.py -k item -v`
Expected: FAIL with `ImportError: cannot import name 'Item'`.

- [ ] **Step 3: Add the `Item` model**

Append to `apps/inventory/models.py` (after `UnitOfMeasure`):

```python
class Item(BaseModel):
    """Catalog definition of something that can be inventoried (the "what").
    Physical stock and expiration live on StockLot (a later slice), not here."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="items"
    )
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
```

- [ ] **Step 4: Add the factory**

Append to `apps/inventory/tests/factories.py`:

```python
from apps.inventory.models import Item  # add to existing model imports


class ItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Item

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Item {n}")
```

- [ ] **Step 5: Generate the migration**

Run: `./scripts/manage.sh makemigrations inventory --name item`
Expected: creates `apps/inventory/migrations/0002_item.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_models.py -v`
Expected: all model tests pass (6 total).

- [ ] **Step 7: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: add inventory Item catalog model"
```

---

### Task 3: `InventoryUnit` model with nesting, cycle guard, and tree helpers

**Files:**
- Modify: `apps/inventory/models.py` (add `InventoryUnit`)
- Modify: `apps/inventory/tests/factories.py` (add `InventoryUnitFactory`)
- Create: `apps/inventory/tests/test_units.py`
- Create (generated): `apps/inventory/migrations/0003_inventoryunit.py`

**Interfaces:**
- Consumes: `UnitType` (Task 1).
- Produces: `apps.inventory.models.InventoryUnit(organization, unit_type, parent, name, description)`; reverse relations `Organization.units`, `UnitType.units`, `InventoryUnit.children`. `parent` uses `on_delete=CASCADE`. `ordering=["name"]`.
- Produces methods: `InventoryUnit.root` (property → top-level ancestor), `InventoryUnit.subtree_size()` (int, nodes including self), `InventoryUnit._descendant_count()` (int, nodes below self), `InventoryUnit.clean()` (raises `django.core.exceptions.ValidationError` on cycles), and `save()` which calls `clean()`.
- Produces: `InventoryUnitFactory`.

- [ ] **Step 1: Write the failing tests**

`apps/inventory/tests/test_units.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.inventory.models import InventoryUnit
from apps.inventory.tests.factories import InventoryUnitFactory
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_root_resolves_top_level_ancestor():
    org = OrganizationFactory()
    ambulance = InventoryUnit.objects.create(organization=org, name="Medic 1")
    cabinet = InventoryUnit.objects.create(
        organization=org, name="Cabinet A", parent=ambulance
    )
    drawer = InventoryUnit.objects.create(
        organization=org, name="Drawer 1", parent=cabinet
    )
    assert drawer.root == ambulance
    assert ambulance.root == ambulance


@pytest.mark.django_db
def test_subtree_and_descendant_counts():
    org = OrganizationFactory()
    ambulance = InventoryUnit.objects.create(organization=org, name="Medic 1")
    cab_a = InventoryUnit.objects.create(organization=org, name="Cab A", parent=ambulance)
    InventoryUnit.objects.create(organization=org, name="Cab B", parent=ambulance)
    InventoryUnit.objects.create(organization=org, name="Drawer", parent=cab_a)
    assert ambulance._descendant_count() == 3
    assert ambulance.subtree_size() == 4


@pytest.mark.django_db
def test_cannot_be_its_own_parent():
    org = OrganizationFactory()
    unit = InventoryUnit.objects.create(organization=org, name="Room")
    unit.parent = unit
    with pytest.raises(ValidationError):
        unit.save()


@pytest.mark.django_db
def test_cannot_nest_under_own_descendant():
    org = OrganizationFactory()
    parent = InventoryUnit.objects.create(organization=org, name="Room")
    child = InventoryUnit.objects.create(organization=org, name="Cabinet", parent=parent)
    parent.parent = child  # would create a cycle
    with pytest.raises(ValidationError):
        parent.save()


@pytest.mark.django_db
def test_delete_cascades_to_subunits():
    org = OrganizationFactory()
    ambulance = InventoryUnit.objects.create(organization=org, name="Medic 1")
    InventoryUnit.objects.create(organization=org, name="Cabinet", parent=ambulance)
    ambulance.delete()
    assert InventoryUnit.objects.filter(organization=org).count() == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_units.py -v`
Expected: FAIL with `ImportError: cannot import name 'InventoryUnit'`.

- [ ] **Step 3: Add the `InventoryUnit` model**

Add imports at the top of `apps/inventory/models.py`:

```python
from django.core.exceptions import ValidationError
```

Append to `apps/inventory/models.py`:

```python
class InventoryUnit(BaseModel):
    """A place that holds inventory: a vehicle, room, cage, pantry, etc. May be
    nested via ``parent`` to arbitrary depth so a location can be subdivided
    (an ambulance into cabinets; a storage room by cabinet). Any unit — parent
    or child — may hold stock in a later slice."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="units"
    )
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
```

- [ ] **Step 4: Add the factory**

Append to `apps/inventory/tests/factories.py`:

```python
from apps.inventory.models import InventoryUnit  # add to existing model imports


class InventoryUnitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InventoryUnit

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Unit {n}")
```

- [ ] **Step 5: Generate the migration**

Run: `./scripts/manage.sh makemigrations inventory --name inventoryunit`
Expected: creates `apps/inventory/migrations/0003_inventoryunit.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_units.py -v`
Expected: 5 passed.

- [ ] **Step 7: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: add nestable InventoryUnit model with cycle guard"
```

---

### Task 4: Per-org default seeding signal

**Files:**
- Modify: `apps/inventory/signals.py` (replace the placeholder)
- Create: `apps/inventory/tests/test_signals.py`

**Interfaces:**
- Consumes: `UnitType`, `UnitOfMeasure` (Task 1); `apps.organizations.models.Organization`.
- Produces: module constants `DEFAULT_UNIT_TYPES: list[tuple[str, str]]`, `DEFAULT_UNITS_OF_MEASURE: list[tuple[str, str]]`, and a `post_save` receiver `seed_organization_defaults(sender, instance, created, **kwargs)` registered via `InventoryConfig.ready()` (already imports `signals`).

- [ ] **Step 1: Write the failing tests**

`apps/inventory/tests/test_signals.py`:

```python
import pytest

from apps.inventory.models import UnitOfMeasure, UnitType
from apps.inventory.signals import DEFAULT_UNIT_TYPES, DEFAULT_UNITS_OF_MEASURE
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_new_org_is_seeded_with_defaults():
    org = OrganizationFactory()
    assert UnitType.objects.filter(organization=org).count() == len(DEFAULT_UNIT_TYPES)
    assert UnitOfMeasure.objects.filter(organization=org).count() == len(
        DEFAULT_UNITS_OF_MEASURE
    )
    names = set(UnitType.objects.filter(organization=org).values_list("name", flat=True))
    assert "Vehicle" in names


@pytest.mark.django_db
def test_seeding_is_scoped_per_org():
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    # Each org gets its own independent copies.
    assert UnitType.objects.filter(organization=org_a).count() == len(DEFAULT_UNIT_TYPES)
    assert UnitType.objects.filter(organization=org_b).count() == len(DEFAULT_UNIT_TYPES)


@pytest.mark.django_db
def test_saving_existing_org_does_not_reseed():
    org = OrganizationFactory()
    before = UnitType.objects.filter(organization=org).count()
    org.name = "Renamed"
    org.save()
    assert UnitType.objects.filter(organization=org).count() == before
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_signals.py -v`
Expected: FAIL — either `ImportError` for `DEFAULT_UNIT_TYPES` or seeded counts are 0.

- [ ] **Step 3: Implement the seeding signal**

Replace `apps/inventory/signals.py` entirely:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_signals.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the whole inventory suite (regression check)**

Run: `./scripts/test.sh apps/inventory -v`
Expected: all inventory tests pass. (Confirms the seeding signal didn't break the model tests — those that create orgs now also seed rows, but assertions are org-scoped.)

- [ ] **Step 6: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: seed new organizations with default unit types and measures"
```

---

### Task 5: Extend the entitlement model with `max_subdivisions` + fix `usage("locations")`

**Files:**
- Modify: `apps/organizations/models.py` (add `Plan.max_subdivisions`, `Subscription.max_subdivisions_override`; change `Organization.usage("locations")`)
- Create (generated): `apps/organizations/migrations/0004_add_max_subdivisions.py`
- Create (manual): `apps/organizations/migrations/0005_seed_free_max_subdivisions.py`
- Create: `apps/inventory/tests/test_entitlements.py`

**Interfaces:**
- Consumes: `InventoryUnit` (Task 3), `Subscription.limit_for` (existing).
- Produces: `Plan.max_subdivisions` (`PositiveIntegerField`, null = unlimited), `Subscription.max_subdivisions_override` (`PositiveIntegerField`, nullable). `Subscription.limit_for("subdivisions")` resolves automatically via the existing `getattr(f"max_{resource}...")` pattern. `Organization.usage("locations")` now counts only top-level units (`parent IS NULL`).

- [ ] **Step 1: Write the failing tests**

`apps/inventory/tests/test_entitlements.py`:

```python
import pytest

from apps.inventory.models import InventoryUnit
from apps.organizations.models import Plan, Subscription
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_free_plan_seeded_with_max_subdivisions_five():
    free = Plan.objects.get(tier=Plan.Tier.FREE)
    assert free.max_subdivisions == 5


@pytest.mark.django_db
def test_limit_for_subdivisions_reads_plan_then_override():
    org = OrganizationFactory()
    sub = org.subscription
    assert sub.limit_for("subdivisions") == 5
    sub.max_subdivisions_override = 20
    sub.save()
    assert sub.limit_for("subdivisions") == 20


@pytest.mark.django_db
def test_usage_locations_counts_top_level_units_only():
    org = OrganizationFactory()
    top = InventoryUnit.objects.create(organization=org, name="Ambulance")
    InventoryUnit.objects.create(organization=org, name="Cabinet", parent=top)
    InventoryUnit.objects.create(organization=org, name="Room")
    # Two top-level units; the cabinet (a sub-unit) does not count.
    assert org.usage("locations") == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_entitlements.py -v`
Expected: FAIL — `max_subdivisions` attribute does not exist / `usage("locations")` counts 3.

- [ ] **Step 3: Add the model fields**

In `apps/organizations/models.py`, in `class Plan`, add after `max_members`:

```python
    max_subdivisions = models.PositiveIntegerField(null=True, blank=True)  # null = unlimited
```

In `class Subscription`, add after `max_members_override`:

```python
    max_subdivisions_override = models.PositiveIntegerField(null=True, blank=True)
```

Change `Organization.usage`'s `locations` branch:

```python
        if resource == "locations":
            return self.units.filter(parent__isnull=True).count()
```

Also update the `limit_for` docstring resource list from `'locations' | 'items' | 'members'` to `'locations' | 'items' | 'members' | 'subdivisions'` (documentation only).

- [ ] **Step 4: Generate the schema migration**

Run: `./scripts/manage.sh makemigrations organizations --name add_max_subdivisions`
Expected: creates `apps/organizations/migrations/0004_add_max_subdivisions.py` adding both fields.

- [ ] **Step 5: Create the data migration seeding Free = 5**

Run: `./scripts/manage.sh makemigrations organizations --empty --name seed_free_max_subdivisions`

Then replace the generated `apps/organizations/migrations/0005_seed_free_max_subdivisions.py` body with:

```python
from django.db import migrations

# Per-location subdivision caps by tier. null = unlimited.
SUBDIVISION_LIMITS = {
    "free": 5,
    "pro": None,
    "enterprise": None,
}


def seed_max_subdivisions(apps, schema_editor):
    Plan = apps.get_model("organizations", "Plan")
    for tier, limit in SUBDIVISION_LIMITS.items():
        Plan.objects.filter(tier=tier).update(max_subdivisions=limit)


def unseed_max_subdivisions(apps, schema_editor):
    Plan = apps.get_model("organizations", "Plan")
    Plan.objects.update(max_subdivisions=None)


class Migration(migrations.Migration):
    dependencies = [("organizations", "0004_add_max_subdivisions")]
    operations = [migrations.RunPython(seed_max_subdivisions, unseed_max_subdivisions)]
```

(Confirm the `dependencies` entry matches the actual filename produced in Step 4; adjust if Django numbered it differently.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_entitlements.py -v`
Expected: 3 passed.

- [ ] **Step 7: Regression — org suite still green**

Run: `./scripts/test.sh apps/organizations -v`
Expected: all existing org tests still pass (the `usage("locations")` change is not covered by org tests; the new fields are additive).

- [ ] **Step 8: Lint + prepare commit**

Run: `uv run ruff check apps/organizations apps/inventory && uv run ruff format apps/organizations apps/inventory`

Intended commit:

```bash
git add apps/organizations apps/inventory
git commit -m "feat: add per-location max_subdivisions entitlement (Free = 5)"
```

---

### Task 6: `InventoryUnit.can_add_subdivision` — the subdivisions cap check

**Files:**
- Modify: `apps/inventory/models.py` (add `can_add_subdivision`)
- Modify: `apps/inventory/tests/test_units.py` (add cap tests)

**Interfaces:**
- Consumes: `Subscription.limit_for("subdivisions")` (Task 5), `InventoryUnit.root` / `_descendant_count` (Task 3).
- Produces: `InventoryUnit.can_add_subdivision(self, adding=1) -> bool` — whether `adding` more sub-units may be placed anywhere beneath `self`'s top-level root, under the org's plan. `self` is the intended parent. Returns `False` if the org has no subscription; `True` when the limit is null (unlimited).

- [ ] **Step 1: Write the failing tests**

Append to `apps/inventory/tests/test_units.py`:

```python
from apps.organizations.models import Plan  # add near existing imports


@pytest.mark.django_db
def test_can_add_subdivision_respects_free_limit():
    org = OrganizationFactory()  # free plan → max_subdivisions = 5
    root = InventoryUnit.objects.create(organization=org, name="Ambulance")
    # Add 5 sub-units; the 6th should be disallowed.
    for i in range(5):
        assert root.can_add_subdivision() is True
        InventoryUnit.objects.create(organization=org, name=f"Cab {i}", parent=root)
    assert root.can_add_subdivision() is False


@pytest.mark.django_db
def test_can_add_subdivision_counts_whole_subtree():
    org = OrganizationFactory()
    root = InventoryUnit.objects.create(organization=org, name="Ambulance")
    cab = InventoryUnit.objects.create(organization=org, name="Cab", parent=root)
    # Nested sub-units count against the same root.
    for i in range(4):
        InventoryUnit.objects.create(organization=org, name=f"Drawer {i}", parent=cab)
    # root subtree now has 5 descendants → at the limit.
    assert cab.can_add_subdivision() is False
    assert root.can_add_subdivision() is False


@pytest.mark.django_db
def test_can_add_subdivision_unlimited_when_limit_null():
    org = OrganizationFactory()
    sub = org.subscription
    sub.plan = Plan.objects.get(tier=Plan.Tier.ENTERPRISE)  # max_subdivisions = None
    sub.save()
    root = InventoryUnit.objects.create(organization=org, name="Warehouse")
    for i in range(10):
        InventoryUnit.objects.create(organization=org, name=f"Aisle {i}", parent=root)
    assert root.can_add_subdivision() is True
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_units.py -k subdivision -v`
Expected: FAIL with `AttributeError: 'InventoryUnit' object has no attribute 'can_add_subdivision'`.

- [ ] **Step 3: Implement the check**

Add the import at the top of `apps/inventory/models.py`:

```python
from apps.organizations.models import Organization, Subscription
```

(Replace the existing `from apps.organizations.models import Organization` line with the combined import.)

Add to `InventoryUnit`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_units.py -v`
Expected: all unit tests pass (8 total).

- [ ] **Step 5: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: add subdivisions cap check to InventoryUnit"
```

---

### Task 7: Catalog CRUD API (`UnitType`, `UnitOfMeasure`)

**Files:**
- Create: `apps/inventory/serializers.py`
- Create: `apps/inventory/views.py`
- Create: `apps/inventory/urls.py`
- Modify: `config/urls.py` (mount `apps.inventory.urls` under `api/`)
- Create: `apps/inventory/tests/test_catalog_api.py`

**Interfaces:**
- Consumes: `IsOrgMember`, `IsOrgAdmin` from `apps.organizations.permissions`.
- Produces: base mixin `apps.inventory.views.OrgScopedMixin` (provides `get_org_id`, `get_permissions`, `get_serializer_context`, `perform_create`); serializers `UnitTypeSerializer`, `UnitOfMeasureSerializer`; views `UnitTypeListCreateView`/`UnitTypeDetailView`, `UnitOfMeasureListCreateView`/`UnitOfMeasureDetailView`; routes under `/api/organizations/<uuid:org_id>/unit-types/` and `/units-of-measure/`.

- [ ] **Step 1: Write the failing API tests**

`apps/inventory/tests/test_catalog_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.inventory.models import UnitOfMeasure, UnitType
from apps.organizations.models import Membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def ut_list_url(org):
    return f"/api/organizations/{org.id}/unit-types/"


@pytest.mark.django_db
def test_member_can_list_seeded_unit_types(client_for):
    org = OrganizationFactory()
    resp = client_for(org.owner).get(ut_list_url(org))
    assert resp.status_code == 200
    # The 4 seeded defaults, scoped to this org.
    assert resp.data["count"] == 4


@pytest.mark.django_db
def test_admin_can_create_unit_type(client_for):
    org = OrganizationFactory()
    resp = client_for(org.owner).post(ut_list_url(org), {"name": "Trailer"})
    assert resp.status_code == 201
    assert UnitType.objects.filter(organization=org, name="Trailer").exists()


@pytest.mark.django_db
def test_non_member_forbidden(client_for):
    org = OrganizationFactory()
    resp = client_for(UserFactory()).get(ut_list_url(org))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_read_only_member_cannot_create(client_for):
    org = OrganizationFactory()
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)  # role defaults to member
    resp = client_for(member).post(ut_list_url(org), {"name": "Nope"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_cannot_read_another_orgs_unit_types(client_for):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    # org_a's owner is not a member of org_b.
    resp = client_for(org_a.owner).get(ut_list_url(org_b))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_unit_of_measure(client_for):
    org = OrganizationFactory()
    url = f"/api/organizations/{org.id}/units-of-measure/"
    resp = client_for(org.owner).post(url, {"name": "Case", "abbreviation": "cs"})
    assert resp.status_code == 201
    assert UnitOfMeasure.objects.filter(organization=org, name="Case").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_catalog_api.py -v`
Expected: FAIL — routes 404 / import errors (views not defined).

- [ ] **Step 3: Write the serializers**

`apps/inventory/serializers.py`:

```python
"""Serializers for the inventory app."""

from rest_framework import serializers

from .models import InventoryUnit, Item, UnitOfMeasure, UnitType


class UnitTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitType
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ["id", "name", "abbreviation", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
```

- [ ] **Step 4: Write the org-scoped view mixin + catalog views**

`apps/inventory/views.py`:

```python
"""API views for the inventory app. All endpoints are nested under an
organization and scoped to it; reads require org membership, writes require
org admin."""

from rest_framework import generics, permissions

from apps.organizations.permissions import IsOrgAdmin, IsOrgMember

from .models import UnitOfMeasure, UnitType
from .serializers import UnitOfMeasureSerializer, UnitTypeSerializer


class OrgScopedMixin:
    """Shared behavior for org-nested endpoints: membership-gated reads,
    admin-gated writes, org filtering, and stamping the org on create."""

    def get_org_id(self):
        return self.kwargs["org_id"]

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated(), IsOrgMember()]
        return [permissions.IsAuthenticated(), IsOrgAdmin()]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org_id"] = self.get_org_id()
        return ctx

    def perform_create(self, serializer):
        serializer.save(organization_id=self.get_org_id())


class UnitTypeListCreateView(OrgScopedMixin, generics.ListCreateAPIView):
    serializer_class = UnitTypeSerializer

    def get_queryset(self):
        return UnitType.objects.filter(organization_id=self.get_org_id())


class UnitTypeDetailView(OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UnitTypeSerializer

    def get_queryset(self):
        return UnitType.objects.filter(organization_id=self.get_org_id())


class UnitOfMeasureListCreateView(OrgScopedMixin, generics.ListCreateAPIView):
    serializer_class = UnitOfMeasureSerializer

    def get_queryset(self):
        return UnitOfMeasure.objects.filter(organization_id=self.get_org_id())


class UnitOfMeasureDetailView(OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UnitOfMeasureSerializer

    def get_queryset(self):
        return UnitOfMeasure.objects.filter(organization_id=self.get_org_id())
```

- [ ] **Step 5: Write the URLs and mount them**

`apps/inventory/urls.py`:

```python
"""Inventory routes (mounted under /api/, nested per organization)."""

from django.urls import path

from .views import (
    UnitOfMeasureDetailView,
    UnitOfMeasureListCreateView,
    UnitTypeDetailView,
    UnitTypeListCreateView,
)

app_name = "inventory"

urlpatterns = [
    path(
        "organizations/<uuid:org_id>/unit-types/",
        UnitTypeListCreateView.as_view(),
        name="unit-type-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/unit-types/<uuid:pk>/",
        UnitTypeDetailView.as_view(),
        name="unit-type-detail",
    ),
    path(
        "organizations/<uuid:org_id>/units-of-measure/",
        UnitOfMeasureListCreateView.as_view(),
        name="uom-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/units-of-measure/<uuid:pk>/",
        UnitOfMeasureDetailView.as_view(),
        name="uom-detail",
    ),
]
```

In `config/urls.py`, add after the organizations include (`path("api/", include("apps.organizations.urls")),`):

```python
    path("api/", include("apps.inventory.urls")),
```

(Django resolves includes in order; requests that don't match an org route fall through to the inventory include, so both can share the `api/` prefix.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_catalog_api.py -v`
Expected: 6 passed.

- [ ] **Step 7: Lint + prepare commit**

Run: `uv run ruff check apps/inventory config && uv run ruff format apps/inventory config`

Intended commit:

```bash
git add apps/inventory config/urls.py
git commit -m "feat: add org-scoped CRUD API for unit types and units of measure"
```

---

### Task 8: `Item` CRUD API with cross-org FK validation

**Files:**
- Modify: `apps/inventory/serializers.py` (add `ItemSerializer`)
- Modify: `apps/inventory/views.py` (add Item views)
- Modify: `apps/inventory/urls.py` (add Item routes)
- Create: `apps/inventory/tests/test_items_api.py`

**Interfaces:**
- Consumes: `OrgScopedMixin` (Task 7), `Item` (Task 2), `UnitOfMeasure` (Task 1).
- Produces: `ItemSerializer` (validates `default_unit_of_measure` and `parent` belong to the URL org); `ItemListCreateView`/`ItemDetailView`; routes under `/api/organizations/<uuid:org_id>/items/`.

- [ ] **Step 1: Write the failing tests**

`apps/inventory/tests/test_items_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.inventory.models import Item, UnitOfMeasure
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def items_url(org):
    return f"/api/organizations/{org.id}/items/"


@pytest.mark.django_db
def test_admin_creates_item_with_default_uom(client_for):
    org = OrganizationFactory()
    uom = UnitOfMeasure.objects.filter(organization=org).first()
    resp = client_for(org.owner).post(
        items_url(org),
        {"name": "Saline", "default_unit_of_measure": str(uom.id)},
    )
    assert resp.status_code == 201
    item = Item.objects.get(id=resp.data["id"])
    assert item.organization == org
    assert item.default_unit_of_measure == uom


@pytest.mark.django_db
def test_cannot_use_another_orgs_uom_as_default(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    foreign_uom = UnitOfMeasure.objects.filter(organization=other).first()
    resp = client_for(org.owner).post(
        items_url(org),
        {"name": "Saline", "default_unit_of_measure": str(foreign_uom.id)},
    )
    assert resp.status_code == 400
    assert "default_unit_of_measure" in resp.data


@pytest.mark.django_db
def test_cannot_parent_item_to_another_orgs_item(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    foreign_item = Item.objects.create(organization=other, name="Foreign Kit")
    resp = client_for(org.owner).post(
        items_url(org),
        {"name": "Gauze", "parent": str(foreign_item.id)},
    )
    assert resp.status_code == 400
    assert "parent" in resp.data


@pytest.mark.django_db
def test_list_scoped_to_org(client_for):
    org = OrganizationFactory()
    Item.objects.create(organization=org, name="Mine")
    Item.objects.create(organization=OrganizationFactory(), name="Theirs")
    resp = client_for(org.owner).get(items_url(org))
    assert resp.status_code == 200
    names = [row["name"] for row in resp.data["results"]]
    assert names == ["Mine"]
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_items_api.py -v`
Expected: FAIL — item routes 404 / `ItemSerializer` not defined.

- [ ] **Step 3: Add `ItemSerializer` with cross-org validation**

Append to `apps/inventory/serializers.py`:

```python
class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = [
            "id",
            "name",
            "description",
            "sku",
            "default_unit_of_measure",
            "tracks_expiration",
            "tracks_serial",
            "expiration_warning_days",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_default_unit_of_measure(self, value):
        if value is not None and str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError(
                "Unit of measure must belong to this organization."
            )
        return value

    def validate_parent(self, value):
        if value is not None and str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Parent item must belong to this organization.")
        return value
```

- [ ] **Step 4: Add the Item views**

In `apps/inventory/views.py`, extend the model/serializer imports:

```python
from .models import InventoryUnit, Item, UnitOfMeasure, UnitType  # noqa: F401 (InventoryUnit used in Task 9)
from .serializers import (
    ItemSerializer,
    UnitOfMeasureSerializer,
    UnitTypeSerializer,
)
```

(Adjust the existing import lines to these; `InventoryUnit` is imported ahead of Task 9 — if the linter flags it as unused now, add it in Task 9 instead. Simplest: import only `Item` here and add `InventoryUnit` in Task 9.)

Append the views:

```python
class ItemListCreateView(OrgScopedMixin, generics.ListCreateAPIView):
    serializer_class = ItemSerializer

    def get_queryset(self):
        qs = Item.objects.filter(organization_id=self.get_org_id())
        parent = self.request.query_params.get("parent")
        if parent is not None:
            qs = qs.filter(parent_id=parent)
        tracks_expiration = self.request.query_params.get("tracks_expiration")
        if tracks_expiration is not None:
            qs = qs.filter(tracks_expiration=tracks_expiration.lower() == "true")
        return qs


class ItemDetailView(OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ItemSerializer

    def get_queryset(self):
        return Item.objects.filter(organization_id=self.get_org_id())
```

- [ ] **Step 5: Add the Item routes**

Add to `apps/inventory/urls.py` imports and `urlpatterns`:

```python
    path(
        "organizations/<uuid:org_id>/items/",
        ItemListCreateView.as_view(),
        name="item-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/items/<uuid:pk>/",
        ItemDetailView.as_view(),
        name="item-detail",
    ),
```

(Import `ItemListCreateView`, `ItemDetailView` from `.views`.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_items_api.py -v`
Expected: 4 passed.

- [ ] **Step 7: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: add Item CRUD API with org-scoped FK validation"
```

---

### Task 9: `InventoryUnit` CRUD API with nesting + subdivisions enforcement

**Files:**
- Modify: `apps/inventory/serializers.py` (add `InventoryUnitSerializer`)
- Modify: `apps/inventory/views.py` (add InventoryUnit views + `InventoryUnit` import)
- Modify: `apps/inventory/urls.py` (add unit routes)
- Create: `apps/inventory/tests/test_units_api.py`

**Interfaces:**
- Consumes: `OrgScopedMixin` (Task 7), `InventoryUnit` (Task 3), `InventoryUnit.can_add_subdivision`/`subtree_size`/`root` (Tasks 3, 6).
- Produces: `InventoryUnitSerializer` (validates `unit_type` and `parent` belong to the org; enforces the cycle guard and the subdivisions cap on create/reparent); `InventoryUnitListCreateView`/`InventoryUnitDetailView`; routes under `/api/organizations/<uuid:org_id>/units/`.

- [ ] **Step 1: Write the failing tests**

`apps/inventory/tests/test_units_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.inventory.models import InventoryUnit
from apps.organizations.models import Plan
from apps.organizations.tests.factories import OrganizationFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def units_url(org):
    return f"/api/organizations/{org.id}/units/"


@pytest.mark.django_db
def test_create_top_level_unit(client_for):
    org = OrganizationFactory()
    resp = client_for(org.owner).post(units_url(org), {"name": "Ambulance"})
    assert resp.status_code == 201
    assert InventoryUnit.objects.get(id=resp.data["id"]).parent_id is None


@pytest.mark.django_db
def test_create_sub_unit(client_for):
    org = OrganizationFactory()
    parent = InventoryUnit.objects.create(organization=org, name="Ambulance")
    resp = client_for(org.owner).post(
        units_url(org), {"name": "Cabinet", "parent": str(parent.id)}
    )
    assert resp.status_code == 201
    assert InventoryUnit.objects.get(id=resp.data["id"]).parent_id == parent.id


@pytest.mark.django_db
def test_subdivisions_cap_enforced_on_free(client_for):
    org = OrganizationFactory()  # free → max_subdivisions = 5
    parent = InventoryUnit.objects.create(organization=org, name="Ambulance")
    for i in range(5):
        InventoryUnit.objects.create(organization=org, name=f"Cab {i}", parent=parent)
    resp = client_for(org.owner).post(
        units_url(org), {"name": "Cab 6", "parent": str(parent.id)}
    )
    assert resp.status_code == 400
    assert "parent" in resp.data


@pytest.mark.django_db
def test_subdivisions_unlimited_on_enterprise(client_for):
    org = OrganizationFactory()
    sub = org.subscription
    sub.plan = Plan.objects.get(tier=Plan.Tier.ENTERPRISE)
    sub.save()
    parent = InventoryUnit.objects.create(organization=org, name="Warehouse")
    for i in range(6):
        resp = client_for(org.owner).post(
            units_url(org), {"name": f"Aisle {i}", "parent": str(parent.id)}
        )
        assert resp.status_code == 201


@pytest.mark.django_db
def test_cannot_parent_to_another_orgs_unit(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    foreign = InventoryUnit.objects.create(organization=other, name="Foreign")
    resp = client_for(org.owner).post(
        units_url(org), {"name": "Cabinet", "parent": str(foreign.id)}
    )
    assert resp.status_code == 400
    assert "parent" in resp.data


@pytest.mark.django_db
def test_reparent_under_own_descendant_rejected(client_for):
    org = OrganizationFactory()
    parent = InventoryUnit.objects.create(organization=org, name="Room")
    child = InventoryUnit.objects.create(organization=org, name="Cabinet", parent=parent)
    resp = client_for(org.owner).patch(
        f"{units_url(org)}{parent.id}/", {"parent": str(child.id)}
    )
    assert resp.status_code == 400
    assert "parent" in resp.data
```

- [ ] **Step 2: Run to verify failure**

Run: `./scripts/test.sh apps/inventory/tests/test_units_api.py -v`
Expected: FAIL — unit routes 404 / `InventoryUnitSerializer` not defined.

- [ ] **Step 3: Add `InventoryUnitSerializer`**

Append to `apps/inventory/serializers.py`:

```python
from django.core.exceptions import ValidationError as DjangoValidationError  # top of file


class InventoryUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryUnit
        fields = [
            "id",
            "name",
            "description",
            "unit_type",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_unit_type(self, value):
        if value is not None and str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Unit type must belong to this organization.")
        return value

    def validate_parent(self, value):
        if value is None:
            return value
        if str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Parent unit must belong to this organization.")
        # Cycle guard for reparenting: the intended parent may not be this unit
        # or one of its descendants.
        instance = self.instance
        if instance is not None:
            if value.id == instance.id:
                raise serializers.ValidationError("A unit cannot be its own parent.")
            ancestor = value
            while ancestor is not None:
                if ancestor.id == instance.id:
                    raise serializers.ValidationError(
                        "A unit cannot be nested under its own descendant."
                    )
                ancestor = ancestor.parent
        return value

    def validate(self, attrs):
        # Enforce the per-location subdivisions cap when a parent is set (create)
        # or changed (reparent). "adding" is the size of the subtree moving in:
        # 1 for a brand-new unit, or the moved unit's whole subtree on reparent.
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        if parent is None:
            return attrs
        instance = self.instance
        # Moving within the same root doesn't change that root's count.
        if instance is not None and instance.parent_id is not None:
            if instance.root.id == parent.root.id:
                return attrs
        adding = instance.subtree_size() if instance is not None else 1
        if not parent.can_add_subdivision(adding=adding):
            raise serializers.ValidationError(
                {"parent": "This location's subdivision limit has been reached."}
            )
        return attrs
```

- [ ] **Step 4: Add the InventoryUnit views**

In `apps/inventory/views.py`, add `InventoryUnit` to the model imports and `InventoryUnitSerializer` to the serializer imports, then append:

```python
class InventoryUnitListCreateView(OrgScopedMixin, generics.ListCreateAPIView):
    serializer_class = InventoryUnitSerializer

    def get_queryset(self):
        qs = InventoryUnit.objects.filter(organization_id=self.get_org_id())
        parent = self.request.query_params.get("parent")
        if parent is not None:
            qs = qs.filter(parent_id=parent)
        unit_type = self.request.query_params.get("unit_type")
        if unit_type is not None:
            qs = qs.filter(unit_type_id=unit_type)
        return qs


class InventoryUnitDetailView(OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InventoryUnitSerializer

    def get_queryset(self):
        return InventoryUnit.objects.filter(organization_id=self.get_org_id())
```

- [ ] **Step 5: Add the unit routes**

Add to `apps/inventory/urls.py`:

```python
    path(
        "organizations/<uuid:org_id>/units/",
        InventoryUnitListCreateView.as_view(),
        name="unit-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/units/<uuid:pk>/",
        InventoryUnitDetailView.as_view(),
        name="unit-detail",
    ),
```

(Import the two views.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_units_api.py -v`
Expected: 6 passed.

- [ ] **Step 7: Lint + prepare commit**

Run: `uv run ruff check apps/inventory && uv run ruff format apps/inventory`

Intended commit:

```bash
git add apps/inventory
git commit -m "feat: add InventoryUnit CRUD API with nesting and subdivisions enforcement"
```

---

### Task 10: Django admin registration + full-suite verification

**Files:**
- Create: `apps/inventory/admin.py`
- (No new tests; this task ends with a green full suite.)

**Interfaces:**
- Consumes: all four models.
- Produces: admin registrations for `UnitType`, `UnitOfMeasure`, `Item`, `InventoryUnit`.

- [ ] **Step 1: Register the models in admin**

`apps/inventory/admin.py`:

```python
"""Django admin registrations for the inventory app."""

from django.contrib import admin

from .models import InventoryUnit, Item, UnitOfMeasure, UnitType


@admin.register(UnitType)
class UnitTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "organization"]
    list_filter = ["organization"]
    search_fields = ["name"]


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ["name", "abbreviation", "organization"]
    list_filter = ["organization"]
    search_fields = ["name", "abbreviation"]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "sku", "tracks_expiration"]
    list_filter = ["organization", "tracks_expiration", "tracks_serial"]
    search_fields = ["name", "sku"]
    raw_id_fields = ["default_unit_of_measure", "parent"]


@admin.register(InventoryUnit)
class InventoryUnitAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "unit_type", "parent"]
    list_filter = ["organization", "unit_type"]
    search_fields = ["name"]
    raw_id_fields = ["parent"]
```

- [ ] **Step 2: Run the full test suite**

Run: `./scripts/test.sh`
Expected: the entire project suite passes (existing 88 org/user/auth tests + all new inventory tests), no warnings (no `UnorderedObjectListWarning`).

- [ ] **Step 3: Lint the whole touched surface**

Run: `uv run ruff check apps/inventory apps/organizations config && uv run ruff format apps/inventory apps/organizations config`
Expected: no issues.

- [ ] **Step 4: Update the SDD progress file**

Update `.superpowers/sdd/progress.md` to record Slice 2a completion (tasks, test counts, files) following the existing format used for Slice 1.

- [ ] **Step 5: Prepare commit**

Intended commit:

```bash
git add apps/inventory .superpowers/sdd/progress.md
git commit -m "feat: register inventory models in Django admin"
```

---

## Self-Review

**Spec coverage** (each spec section → task):
- `UnitType`, `UnitOfMeasure` models → Task 1. `Item` (self-nesting, flags, `expiration_warning_days`) → Task 2. `InventoryUnit` (nesting, CASCADE, cycle guard, `root`) → Task 3.
- Per-org seeding signal (`DEFAULT_UNIT_TYPES`/`DEFAULT_UNITS_OF_MEASURE`, coexists with org signal) → Task 4.
- Org-app entitlement changes (`Plan.max_subdivisions`, `Subscription.max_subdivisions_override`, `usage("locations")` top-level only, Free = 5 data migration) → Task 5. Per-location subdivisions check → Task 6, enforced at write → Task 9.
- API surface (unit-types, units-of-measure, items, units; `IsOrgMember`/`IsOrgAdmin`; nested under org; error envelope + pagination) → Tasks 7–9. Cross-org FK validation → Tasks 8, 9. Cycle guard at API → Task 9.
- Testing coverage (uniqueness, nesting/cycle, cascade, seeding, entitlements, permissions, org-scoping) → distributed across Tasks 1–9. Admin → Task 10.
- Deferred items (`par_template` FK, StockLot, submissions, alerts, location/item enforcement) → correctly absent from this plan.

**Placeholder scan:** No TBD/TODO; every step has concrete code or an exact command. The Task 8 import note about `InventoryUnit` is a real instruction (import it in Task 9), not a deferred placeholder.

**Type consistency:** `get_org_id()`, `OrgScopedMixin`, `can_add_subdivision(adding=1)`, `subtree_size()`, `_descendant_count()`, `root`, `limit_for("subdivisions")` are named identically everywhere they appear. Serializer context key `org_id` is set in `OrgScopedMixin.get_serializer_context` and read in every `validate_*`. Reverse relations (`unit_types`, `units_of_measure`, `items`, `units`, `children`) match between models, signal, and `usage()`.

**One known limitation (documented):** the subdivisions cap counts the destination root's subtree; a reparent that moves a unit between two roots is checked against the destination but its source is not decremented in the same transaction — acceptable because full entitlement enforcement is a deferred billing-slice concern, and the create path (the common case) is exact.
