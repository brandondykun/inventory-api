# Inventory Slice 2c — Stock & Adjustments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live on-hand stock (`StockLot`) and an append-only, audited add/reduce ledger (`StockAdjustment`) to the inventory app, and relax inventory writes to org-member level.

**Architecture:** `StockAdjustment` is the single audited writer; `StockLot` is derived state whose `quantity` is maintained incrementally. Recording an adjustment inserts one ledger row and upserts the one matching `StockLot` inside a single transaction (`select_for_update` on the lot). Endpoints nest under a unit and reach the org through `unit__organization_id`, mirroring how 2b nested par lines under a template.

**Tech Stack:** Django 5.2, Django REST Framework, Postgres 17, pytest / pytest-django, factory_boy, ruff. Docker via `./scripts/*.sh`.

## Global Constraints

- Models inherit `apps.common.models.BaseModel` (UUID pk + `created_at`/`updated_at`). Never add hand-rolled pk/timestamps.
- Every FK value posted through the API is validated to the URL org in the serializer (`str(value.organization_id) != str(self.context["org_id"])` → 400).
- API errors flow through `apps.common.exceptions.api_exception_handler`; assertions on 400 bodies read `resp.data["error"]["detail"]`, NOT `resp.data`.
- Lists use `StandardResultsSetPagination`; paginated responses expose `resp.data["results"]` and `resp.data["count"]`.
- Postgres 17 + Django 5.2 → `UniqueConstraint(..., nulls_distinct=False)` is available and REQUIRED for the lot key.
- **Commit policy (unchanged from 2a/2b): implementers do NOT commit.** Each task ends with the inventory suite + ruff green; all changes are left uncommitted for the user. The controller snapshots each task with `git add -A && git write-tree` (no commits).
- Run tests with `./scripts/test.sh <pytest args>` (args pass straight to pytest). Run migrations with `./scripts/manage.sh makemigrations inventory` / `migrate`. Lint with `ruff check apps/inventory/` and `ruff format apps/inventory/`.

## File Structure

- `apps/inventory/models.py` — **modify**: append `StockLot` and `StockAdjustment`; add `from django.conf import settings`.
- `apps/inventory/migrations/0006_stocklot_stockadjustment.py` — **create** (via `makemigrations`).
- `apps/inventory/tests/factories.py` — **modify**: add `StockLotFactory`, `StockAdjustmentFactory`.
- `apps/inventory/tests/test_stock_models.py` — **create**: model-layer tests.
- `apps/inventory/views.py` — **modify**: relax `OrgScopedMixin.get_permissions`; add `_UnitScopedMixin`, `_apply_adjustment`, stock views; new imports.
- `apps/inventory/serializers.py` — **modify**: add `StockAdjustmentSerializer`, `StockLotSerializer`.
- `apps/inventory/urls.py` — **modify**: add stock-adjustment and stock-lot routes.
- `apps/inventory/admin.py` — **modify**: register `StockLot`, `StockAdjustment`.
- `apps/inventory/tests/test_stock_adjustments_api.py` — **create**: adjustment API tests.
- `apps/inventory/tests/test_stock_lots_api.py` — **create**: stock-lot read API tests.
- `apps/inventory/tests/test_catalog_api.py` — **modify**: flip one member-write assertion.
- `apps/inventory/tests/test_par_templates_api.py` — **modify**: flip one member-write assertion.

---

### Task 1: Models — `StockLot` + `StockAdjustment` + migration

**Files:**
- Modify: `apps/inventory/models.py` (append two models; add settings import)
- Modify: `apps/inventory/tests/factories.py` (add two factories)
- Create: `apps/inventory/tests/test_stock_models.py`
- Create: `apps/inventory/migrations/0006_stocklot_stockadjustment.py` (generated)

**Interfaces:**
- Produces: `StockLot(unit, item, quantity, unit_of_measure, expiration_date, lot_number)` with unique key `(unit, item, expiration_date, lot_number)` (`nulls_distinct=False`); related_names `unit.stock_lots`, `item.stock_lots`, `unit_of_measure.stock_lots`.
- Produces: `StockAdjustment(unit, item, unit_of_measure, adjustment_type, quantity, expiration_date, lot_number, reason, created_by)` with `StockAdjustment.AdjustmentType.ADD == "add"` / `.REMOVE == "remove"`; related_names `*.stock_adjustments`.
- Produces: `StockLotFactory`, `StockAdjustmentFactory`.

- [ ] **Step 1: Write the failing model tests**

Create `apps/inventory/tests/test_stock_models.py`:

```python
"""Model-layer tests for StockLot and StockAdjustment."""

import pytest
from django.db import IntegrityError, transaction

from apps.inventory.models import StockAdjustment, StockLot
from apps.inventory.tests.factories import (
    InventoryUnitFactory,
    ItemFactory,
    StockAdjustmentFactory,
    StockLotFactory,
    UnitOfMeasureFactory,
)


@pytest.mark.django_db
def test_stock_lot_str_and_defaults():
    lot = StockLotFactory(quantity=7)
    assert lot.quantity == 7
    assert lot.expiration_date is None
    assert lot.lot_number == ""
    assert str(lot.item) in str(lot)


@pytest.mark.django_db
def test_null_expiration_lots_collapse_to_one():
    unit = InventoryUnitFactory()
    item = ItemFactory(organization=unit.organization)
    uom = UnitOfMeasureFactory(organization=unit.organization)
    StockLot.objects.create(unit=unit, item=item, unit_of_measure=uom, quantity=1)
    # A second null-date / blank-lot row for the same unit+item is rejected by
    # the nulls_distinct=False unique constraint.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StockLot.objects.create(unit=unit, item=item, unit_of_measure=uom, quantity=2)


@pytest.mark.django_db
def test_distinct_expiration_lots_allowed():
    unit = InventoryUnitFactory()
    item = ItemFactory(organization=unit.organization)
    uom = UnitOfMeasureFactory(organization=unit.organization)
    StockLot.objects.create(
        unit=unit, item=item, unit_of_measure=uom, quantity=1, expiration_date="2027-01-01"
    )
    StockLot.objects.create(
        unit=unit, item=item, unit_of_measure=uom, quantity=1, expiration_date="2027-02-01"
    )
    assert StockLot.objects.filter(unit=unit, item=item).count() == 2


@pytest.mark.django_db
def test_stock_adjustment_defaults():
    adj = StockAdjustmentFactory(quantity=3)
    assert adj.adjustment_type == StockAdjustment.AdjustmentType.ADD
    assert adj.quantity == 3
    assert adj.reason == ""
    assert adj.created_by is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./scripts/test.sh apps/inventory/tests/test_stock_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'StockLot'` (models/factories not defined yet).

- [ ] **Step 3: Add the models**

Add to the top imports of `apps/inventory/models.py` (below `from django.db import models`):

```python
from django.conf import settings
```

Append to `apps/inventory/models.py`:

```python
class StockLot(BaseModel):
    """Live believed on-hand of one item in one unit, for one expiration lot.
    Derived state: ``quantity`` is maintained incrementally by StockAdjustment.
    Read-only via the API."""

    unit = models.ForeignKey(
        InventoryUnit, on_delete=models.CASCADE, related_name="stock_lots"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="stock_lots")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, related_name="stock_lots"
    )
    expiration_date = models.DateField(null=True, blank=True)
    lot_number = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["item__name", "expiration_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "item", "expiration_date", "lot_number"],
                nulls_distinct=False,
                name="uniq_stock_lot",
            )
        ]
        indexes = [
            models.Index(fields=["expiration_date"]),
            models.Index(fields=["unit", "item"]),
        ]

    def __str__(self):
        return f"{self.item}: {self.quantity} {self.unit_of_measure} @ {self.unit}"


class StockAdjustment(BaseModel):
    """Append-only ledger of a single add/reduce to on-hand stock. Applying it
    upserts the matching StockLot. Never edited or deleted via the API."""

    class AdjustmentType(models.TextChoices):
        ADD = "add", "Add"
        REMOVE = "remove", "Remove"

    unit = models.ForeignKey(
        InventoryUnit, on_delete=models.CASCADE, related_name="stock_adjustments"
    )
    item = models.ForeignKey(
        Item, on_delete=models.PROTECT, related_name="stock_adjustments"
    )
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, related_name="stock_adjustments"
    )
    adjustment_type = models.CharField(max_length=10, choices=AdjustmentType.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    expiration_date = models.DateField(null=True, blank=True)
    lot_number = models.CharField(max_length=100, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="stock_adjustments",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["unit", "item"])]

    def __str__(self):
        return f"{self.adjustment_type} {self.quantity} {self.item} @ {self.unit}"
```

- [ ] **Step 4: Add the factories**

In `apps/inventory/tests/factories.py`, add `StockAdjustment`, `StockLot` to the model import block, then append:

```python
class StockLotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StockLot

    unit = factory.SubFactory(InventoryUnitFactory)
    item = factory.SubFactory(
        ItemFactory, organization=factory.SelfAttribute("..unit.organization")
    )
    unit_of_measure = factory.SubFactory(
        UnitOfMeasureFactory, organization=factory.SelfAttribute("..unit.organization")
    )
    quantity = 10


class StockAdjustmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StockAdjustment

    unit = factory.SubFactory(InventoryUnitFactory)
    item = factory.SubFactory(
        ItemFactory, organization=factory.SelfAttribute("..unit.organization")
    )
    unit_of_measure = factory.SubFactory(
        UnitOfMeasureFactory, organization=factory.SelfAttribute("..unit.organization")
    )
    adjustment_type = StockAdjustment.AdjustmentType.ADD
    quantity = 5
```

- [ ] **Step 5: Generate the migration**

Run: `./scripts/manage.sh makemigrations inventory`
Expected: creates `apps/inventory/migrations/0006_stocklot_stockadjustment.py` adding both models, the `uniq_stock_lot` constraint, and the three indexes. Open it and confirm `UniqueConstraint(..., nulls_distinct=False, name="uniq_stock_lot")` is present.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_stock_models.py -v`
Expected: PASS (4 passed). The migration is applied automatically by the test stack.

- [ ] **Step 7: Lint, then run the full inventory suite (no commit)**

Run: `ruff check apps/inventory/ && ruff format apps/inventory/`
Run: `./scripts/test.sh apps/inventory -v`
Expected: ruff clean; whole inventory suite still green. Leave changes uncommitted for review.

---

### Task 2: Relax inventory writes to member-level

**Files:**
- Modify: `apps/inventory/views.py:31-34` (`OrgScopedMixin.get_permissions`) and `:9` (import)
- Modify: `apps/inventory/tests/test_catalog_api.py:48-54`
- Modify: `apps/inventory/tests/test_par_templates_api.py:83-88`

**Interfaces:**
- Produces: `OrgScopedMixin.get_permissions` returns `[IsAuthenticated(), IsOrgMember()]` for ALL methods. Every inventory view (2a/2b/2c) inherits this, so any org member may now create/update/delete. Non-members remain 403; cross-org detail remains 404.

- [ ] **Step 1: Write the failing test (member can now write)**

In `apps/inventory/tests/test_catalog_api.py`, replace `test_read_only_member_cannot_create` (lines 48-54) with:

```python
@pytest.mark.django_db
def test_member_can_create_unit_type(client_for):
    org = OrganizationFactory()
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)  # role defaults to member
    resp = client_for(member).post(ut_list_url(org), {"name": "MemberMade"})
    assert resp.status_code == 201
    assert UnitType.objects.filter(organization=org, name="MemberMade").exists()
```

In `apps/inventory/tests/test_par_templates_api.py`, replace `test_member_reads_admin_writes` (lines 83-88) with:

```python
@pytest.mark.django_db
def test_member_reads_and_writes(client_for):
    org = OrganizationFactory()
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    assert client_for(member).get(list_url(org)).status_code == 200
    assert client_for(member).post(list_url(org), {"name": "X"}).status_code == 201
```

- [ ] **Step 2: Run the two tests to verify they fail**

Run: `./scripts/test.sh apps/inventory/tests/test_catalog_api.py::test_member_can_create_unit_type apps/inventory/tests/test_par_templates_api.py::test_member_reads_and_writes -v`
Expected: FAIL — both member POSTs currently return 403 (admin-only writes).

- [ ] **Step 3: Relax the permission mixin**

In `apps/inventory/views.py`, change the import on line 9 from:

```python
from apps.organizations.permissions import IsOrgAdmin, IsOrgMember
```

to:

```python
from apps.organizations.permissions import IsOrgMember
```

Replace `OrgScopedMixin.get_permissions` (lines 31-34) with:

```python
    def get_permissions(self):
        # v1: any org member may read AND write inventory resources. The method
        # branch is intentionally collapsed; a future slice can re-gate specific
        # actions (e.g. delete) by reinstating an IsOrgAdmin branch here.
        return [permissions.IsAuthenticated(), IsOrgMember()]
```

- [ ] **Step 4: Run the two tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_catalog_api.py::test_member_can_create_unit_type apps/inventory/tests/test_par_templates_api.py::test_member_reads_and_writes -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint and run the full inventory suite (no commit)**

Run: `ruff check apps/inventory/ && ruff format apps/inventory/`
Run: `./scripts/test.sh apps/inventory -v`
Expected: ruff clean (no unused `IsOrgAdmin` import); whole inventory suite green — the non-member (403) and cross-org (404) tests still pass unchanged. Leave uncommitted.

---

### Task 3: `StockAdjustment` resource — serializer, apply logic, API

**Files:**
- Modify: `apps/inventory/serializers.py` (add `StockAdjustmentSerializer`; import `StockAdjustment`)
- Modify: `apps/inventory/views.py` (add imports, `_UnitScopedMixin`, `_apply_adjustment`, two views)
- Modify: `apps/inventory/urls.py` (two routes + imports)
- Create: `apps/inventory/tests/test_stock_adjustments_api.py`

**Interfaces:**
- Consumes: `StockLot`, `StockAdjustment` (Task 1); `OrgScopedMixin` with member-level writes (Task 2).
- Produces: `_UnitScopedMixin(OrgScopedMixin)` with `get_unit()` (404s a foreign/absent unit) and `unit_id` in serializer context.
- Produces: `_apply_adjustment(adjustment)` — upserts the target `StockLot` under `select_for_update`; must be called inside `transaction.atomic()`; raises `serializers.ValidationError` on over-remove / no-lot / uom mismatch.
- Produces routes: `stock-adjustment-list-create`, `stock-adjustment-detail` at `.../units/<unit_id>/adjustments/`.

- [ ] **Step 1: Write the failing API tests**

Create `apps/inventory/tests/test_stock_adjustments_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.inventory.models import StockAdjustment, StockLot
from apps.inventory.tests.factories import (
    InventoryUnitFactory,
    ItemFactory,
    UnitOfMeasureFactory,
)
from apps.organizations.models import Membership
from apps.organizations.tests.factories import OrganizationFactory, UserFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def adj_url(org, unit):
    return f"/api/organizations/{org.id}/units/{unit.id}/adjustments/"


def _setup(org, *, tracks_expiration=False, with_default_uom=True):
    unit = InventoryUnitFactory(organization=org)
    uom = UnitOfMeasureFactory(organization=org)
    item = ItemFactory(
        organization=org,
        tracks_expiration=tracks_expiration,
        default_unit_of_measure=uom if with_default_uom else None,
    )
    return unit, item, uom


@pytest.mark.django_db
def test_add_creates_lot(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org)
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "5"},
    )
    assert resp.status_code == 201
    lot = StockLot.objects.get(unit=unit, item=item)
    assert lot.quantity == 5
    assert lot.unit_of_measure_id == uom.id  # defaulted from the item


@pytest.mark.django_db
def test_add_increments_existing_lot(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org)
    body = {"item": str(item.id), "adjustment_type": "add", "quantity": "5"}
    client_for(org.owner).post(adj_url(org, unit), body)
    client_for(org.owner).post(adj_url(org, unit), body)
    assert StockLot.objects.get(unit=unit, item=item).quantity == 10
    assert StockLot.objects.filter(unit=unit, item=item).count() == 1


@pytest.mark.django_db
def test_add_distinct_expiration_creates_second_lot(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org, tracks_expiration=True)
    client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "5",
         "expiration_date": "2027-01-01"},
    )
    client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "3",
         "expiration_date": "2027-02-01"},
    )
    assert StockLot.objects.filter(unit=unit, item=item).count() == 2


@pytest.mark.django_db
def test_add_expiration_item_requires_date(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org, tracks_expiration=True)
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "5"},
    )
    assert resp.status_code == 400
    assert "expiration_date" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_expiration_date_on_non_expiration_item_rejected(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org, tracks_expiration=False)
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "5",
         "expiration_date": "2027-01-01"},
    )
    assert resp.status_code == 400
    assert "expiration_date" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_uom_missing_and_no_default_rejected(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org, with_default_uom=False)
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "5"},
    )
    assert resp.status_code == 400
    assert "unit_of_measure" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_quantity_must_be_positive(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org)
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "0"},
    )
    assert resp.status_code == 400
    assert "quantity" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_remove_decrements_lot(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org)
    client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "10"},
    )
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "remove", "quantity": "4"},
    )
    assert resp.status_code == 201
    assert StockLot.objects.get(unit=unit, item=item).quantity == 6


@pytest.mark.django_db
def test_remove_to_zero_deletes_lot_but_keeps_ledger(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org)
    client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "5"},
    )
    client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "remove", "quantity": "5"},
    )
    assert not StockLot.objects.filter(unit=unit, item=item).exists()
    assert StockAdjustment.objects.filter(unit=unit, item=item).count() == 2


@pytest.mark.django_db
def test_over_remove_rejected(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org)
    client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "3"},
    )
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "remove", "quantity": "9"},
    )
    assert resp.status_code == 400
    assert "quantity" in resp.data["error"]["detail"]
    assert StockLot.objects.get(unit=unit, item=item).quantity == 3  # unchanged


@pytest.mark.django_db
def test_remove_no_matching_lot_rejected(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org)
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "remove", "quantity": "1"},
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_uom_mismatch_on_existing_lot_rejected(client_for):
    org = OrganizationFactory()
    unit, item, uom = _setup(org)
    other_uom = UnitOfMeasureFactory(organization=org)
    client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "5"},
    )
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "2",
         "unit_of_measure": str(other_uom.id)},
    )
    assert resp.status_code == 400
    assert "unit_of_measure" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_cross_org_item_rejected(client_for):
    org = OrganizationFactory()
    unit, _item, _uom = _setup(org)
    foreign_item = ItemFactory(organization=OrganizationFactory())
    resp = client_for(org.owner).post(
        adj_url(org, unit),
        {"item": str(foreign_item.id), "adjustment_type": "add", "quantity": "5"},
    )
    assert resp.status_code == 400
    assert "item" in resp.data["error"]["detail"]


@pytest.mark.django_db
def test_member_can_record_and_created_by_stamped(client_for):
    org = OrganizationFactory()
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    unit, item, uom = _setup(org)
    resp = client_for(member).post(
        adj_url(org, unit),
        {"item": str(item.id), "adjustment_type": "add", "quantity": "5"},
    )
    assert resp.status_code == 201
    adj = StockAdjustment.objects.get(unit=unit, item=item)
    assert adj.created_by_id == member.id


@pytest.mark.django_db
def test_adjustments_scoped_to_unit_and_org(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    foreign_unit = InventoryUnitFactory(organization=other)
    # A unit belonging to another org is not reachable under this org.
    resp = client_for(org.owner).get(adj_url(org, foreign_unit))
    assert resp.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./scripts/test.sh apps/inventory/tests/test_stock_adjustments_api.py -v`
Expected: FAIL — 404s on `.../adjustments/` (routes/views not defined).

- [ ] **Step 3: Add the serializer**

In `apps/inventory/serializers.py`, add `StockAdjustment` to the `.models` import line, then append:

```python
class StockAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAdjustment
        fields = [
            "id",
            "item",
            "unit_of_measure",
            "adjustment_type",
            "quantity",
            "expiration_date",
            "lot_number",
            "reason",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]
        extra_kwargs = {"unit_of_measure": {"required": False}}

    def validate_item(self, value):
        if str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Item must belong to this organization.")
        return value

    def validate_unit_of_measure(self, value):
        if value is not None and str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Unit of measure must belong to this organization.")
        return value

    def validate(self, attrs):
        item = attrs["item"]
        if attrs["quantity"] <= 0:
            raise serializers.ValidationError({"quantity": "Must be greater than zero."})
        # Default the unit of measure from the item when omitted.
        if attrs.get("unit_of_measure") is None:
            default_uom = item.default_unit_of_measure
            if default_uom is None:
                raise serializers.ValidationError(
                    {"unit_of_measure": "Required; item has no default unit of measure."}
                )
            attrs["unit_of_measure"] = default_uom
        # Expiration rules.
        exp = attrs.get("expiration_date")
        if item.tracks_expiration:
            if attrs["adjustment_type"] == StockAdjustment.AdjustmentType.ADD and exp is None:
                raise serializers.ValidationError(
                    {"expiration_date": "Required when adding an expiration-tracked item."}
                )
        elif exp is not None:
            raise serializers.ValidationError(
                {"expiration_date": "This item does not track expiration."}
            )
        return attrs
```

- [ ] **Step 4: Add the mixin, apply logic, and views**

In `apps/inventory/views.py`, update imports:

```python
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers
```

Add `StockAdjustment`, `StockLot` to the `.models` import and `StockAdjustmentSerializer` to the `.serializers` import.

Add the mixin and apply helper (near `_TemplateScopedMixin`):

```python
class _UnitScopedMixin(OrgScopedMixin):
    """Stock endpoints: scope to one unit that must belong to the URL org."""

    def get_unit(self):
        return get_object_or_404(
            InventoryUnit,
            pk=self.kwargs["unit_id"],
            organization_id=self.get_org_id(),
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["unit_id"] = self.kwargs["unit_id"]
        return ctx


def _apply_adjustment(adjustment):
    """Upsert the StockLot an adjustment targets. MUST run inside a transaction;
    locks the matching lot row to serialize concurrent adjustments. Raises
    serializers.ValidationError (→ 400) on an invalid remove or uom mismatch."""
    lot_key = {
        "unit": adjustment.unit,
        "item": adjustment.item,
        "expiration_date": adjustment.expiration_date,
        "lot_number": adjustment.lot_number,
    }
    lot = StockLot.objects.select_for_update().filter(**lot_key).first()

    if adjustment.adjustment_type == StockAdjustment.AdjustmentType.ADD:
        if lot is None:
            # NOTE: a concurrent ADD of the same not-yet-existing lot is backstopped
            # by the uniq_stock_lot constraint (rare 500); the common contended case
            # (an existing lot) is serialized by select_for_update above.
            StockLot.objects.create(
                unit_of_measure=adjustment.unit_of_measure,
                quantity=adjustment.quantity,
                **lot_key,
            )
            return
        if lot.unit_of_measure_id != adjustment.unit_of_measure_id:
            raise serializers.ValidationError(
                {"unit_of_measure": "Does not match the existing lot's unit of measure."}
            )
        lot.quantity += adjustment.quantity
        lot.save(update_fields=["quantity", "updated_at"])
        return

    # REMOVE
    if lot is None:
        raise serializers.ValidationError({"quantity": "No matching stock lot to reduce."})
    if lot.unit_of_measure_id != adjustment.unit_of_measure_id:
        raise serializers.ValidationError(
            {"unit_of_measure": "Does not match the existing lot's unit of measure."}
        )
    if adjustment.quantity > lot.quantity:
        raise serializers.ValidationError(
            {"quantity": f"Cannot remove {adjustment.quantity}; only {lot.quantity} on hand."}
        )
    lot.quantity -= adjustment.quantity
    if lot.quantity == 0:
        lot.delete()
    else:
        lot.save(update_fields=["quantity", "updated_at"])


class StockAdjustmentListCreateView(_UnitScopedMixin, generics.ListCreateAPIView):
    serializer_class = StockAdjustmentSerializer

    def get_queryset(self):
        qs = StockAdjustment.objects.filter(unit=self.get_unit())
        item = self.request.query_params.get("item")
        if item is not None:
            qs = qs.filter(item_id=item)
        return qs

    def perform_create(self, serializer):
        unit = self.get_unit()
        with transaction.atomic():
            adjustment = serializer.save(unit=unit, created_by=self.request.user)
            _apply_adjustment(adjustment)


class StockAdjustmentDetailView(_UnitScopedMixin, generics.RetrieveAPIView):
    serializer_class = StockAdjustmentSerializer

    def get_queryset(self):
        return StockAdjustment.objects.filter(
            unit_id=self.kwargs["unit_id"],
            unit__organization_id=self.get_org_id(),
        )
```

- [ ] **Step 5: Add the routes**

In `apps/inventory/urls.py`, add `StockAdjustmentDetailView`, `StockAdjustmentListCreateView` to the `.views` import, then add to `urlpatterns`:

```python
    path(
        "organizations/<uuid:org_id>/units/<uuid:unit_id>/adjustments/",
        StockAdjustmentListCreateView.as_view(),
        name="stock-adjustment-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/units/<uuid:unit_id>/adjustments/<uuid:pk>/",
        StockAdjustmentDetailView.as_view(),
        name="stock-adjustment-detail",
    ),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_stock_adjustments_api.py -v`
Expected: PASS (14 passed).

- [ ] **Step 7: Lint and run the full inventory suite (no commit)**

Run: `ruff check apps/inventory/ && ruff format apps/inventory/`
Run: `./scripts/test.sh apps/inventory -v`
Expected: ruff clean; whole suite green. Leave uncommitted.

---

### Task 4: `StockLot` read-only API

**Files:**
- Modify: `apps/inventory/serializers.py` (add `StockLotSerializer`; import `StockLot`)
- Modify: `apps/inventory/views.py` (add `StockLotListView`, `StockLotDetailView`; import serializer)
- Modify: `apps/inventory/urls.py` (two routes + imports)
- Create: `apps/inventory/tests/test_stock_lots_api.py`

**Interfaces:**
- Consumes: `StockLot` (Task 1), `_UnitScopedMixin` (Task 3).
- Produces routes: `stock-lot-list`, `stock-lot-detail` at `.../units/<unit_id>/stock-lots/` (read-only: GET list/retrieve; POST → 405).

- [ ] **Step 1: Write the failing tests**

Create `apps/inventory/tests/test_stock_lots_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.inventory.tests.factories import (
    InventoryUnitFactory,
    ItemFactory,
    StockLotFactory,
    UnitOfMeasureFactory,
)
from apps.organizations.tests.factories import OrganizationFactory


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


def lots_url(org, unit):
    return f"/api/organizations/{org.id}/units/{unit.id}/stock-lots/"


@pytest.mark.django_db
def test_list_stock_lots(client_for):
    org = OrganizationFactory()
    unit = InventoryUnitFactory(organization=org)
    item = ItemFactory(organization=org)
    uom = UnitOfMeasureFactory(organization=org)
    StockLotFactory(unit=unit, item=item, unit_of_measure=uom, quantity=4)
    resp = client_for(org.owner).get(lots_url(org, unit))
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["quantity"] == "4.00"


@pytest.mark.django_db
def test_filter_by_item(client_for):
    org = OrganizationFactory()
    unit = InventoryUnitFactory(organization=org)
    uom = UnitOfMeasureFactory(organization=org)
    item_a = ItemFactory(organization=org)
    item_b = ItemFactory(organization=org)
    StockLotFactory(unit=unit, item=item_a, unit_of_measure=uom)
    StockLotFactory(unit=unit, item=item_b, unit_of_measure=uom)
    resp = client_for(org.owner).get(f"{lots_url(org, unit)}?item={item_a.id}")
    assert resp.status_code == 200
    assert resp.data["count"] == 1


@pytest.mark.django_db
def test_stock_lots_are_read_only(client_for):
    org = OrganizationFactory()
    unit = InventoryUnitFactory(organization=org)
    resp = client_for(org.owner).post(lots_url(org, unit), {})
    assert resp.status_code == 405  # method not allowed — lots change only via adjustments


@pytest.mark.django_db
def test_cross_org_lot_list_404(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    foreign_unit = InventoryUnitFactory(organization=other)
    resp = client_for(org.owner).get(lots_url(org, foreign_unit))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_cross_org_lot_detail_404(client_for):
    org = OrganizationFactory()
    other = OrganizationFactory()
    foreign_unit = InventoryUnitFactory(organization=other)
    foreign_lot = StockLotFactory(
        unit=foreign_unit,
        item=ItemFactory(organization=other),
        unit_of_measure=UnitOfMeasureFactory(organization=other),
    )
    resp = client_for(org.owner).get(f"{lots_url(org, foreign_unit)}{foreign_lot.id}/")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./scripts/test.sh apps/inventory/tests/test_stock_lots_api.py -v`
Expected: FAIL — 404 on `.../stock-lots/` (routes/views not defined).

- [ ] **Step 3: Add the serializer**

In `apps/inventory/serializers.py`, add `StockLot` to the `.models` import, then append:

```python
class StockLotSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLot
        fields = [
            "id",
            "item",
            "quantity",
            "unit_of_measure",
            "expiration_date",
            "lot_number",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
```

- [ ] **Step 4: Add the views**

In `apps/inventory/views.py`, add `StockLotSerializer` to the `.serializers` import, then add:

```python
class StockLotListView(_UnitScopedMixin, generics.ListAPIView):
    serializer_class = StockLotSerializer

    def get_queryset(self):
        qs = StockLot.objects.filter(unit=self.get_unit())
        item = self.request.query_params.get("item")
        if item is not None:
            qs = qs.filter(item_id=item)
        return qs


class StockLotDetailView(_UnitScopedMixin, generics.RetrieveAPIView):
    serializer_class = StockLotSerializer

    def get_queryset(self):
        return StockLot.objects.filter(
            unit_id=self.kwargs["unit_id"],
            unit__organization_id=self.get_org_id(),
        )
```

- [ ] **Step 5: Add the routes**

In `apps/inventory/urls.py`, add `StockLotDetailView`, `StockLotListView` to the `.views` import, then add to `urlpatterns`:

```python
    path(
        "organizations/<uuid:org_id>/units/<uuid:unit_id>/stock-lots/",
        StockLotListView.as_view(),
        name="stock-lot-list",
    ),
    path(
        "organizations/<uuid:org_id>/units/<uuid:unit_id>/stock-lots/<uuid:pk>/",
        StockLotDetailView.as_view(),
        name="stock-lot-detail",
    ),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./scripts/test.sh apps/inventory/tests/test_stock_lots_api.py -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Lint and run the full inventory suite (no commit)**

Run: `ruff check apps/inventory/ && ruff format apps/inventory/`
Run: `./scripts/test.sh apps/inventory -v`
Expected: ruff clean; whole suite green. Leave uncommitted.

---

### Task 5: Admin registration + full-suite verification

**Files:**
- Modify: `apps/inventory/admin.py` (register `StockLot`, `StockAdjustment`)

**Interfaces:**
- Consumes: `StockLot`, `StockAdjustment` (Task 1).

- [ ] **Step 1: Register the models in admin**

In `apps/inventory/admin.py`, add `StockAdjustment`, `StockLot` to the `.models` import, then append:

```python
@admin.register(StockLot)
class StockLotAdmin(admin.ModelAdmin):
    list_display = ["item", "unit", "quantity", "unit_of_measure", "expiration_date"]
    list_filter = ["expiration_date"]
    search_fields = ["item__name", "unit__name", "lot_number"]
    raw_id_fields = ["unit", "item", "unit_of_measure"]


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ["item", "unit", "adjustment_type", "quantity", "created_by", "created_at"]
    list_filter = ["adjustment_type"]
    search_fields = ["item__name", "unit__name", "lot_number", "reason"]
    raw_id_fields = ["unit", "item", "unit_of_measure", "created_by"]
```

- [ ] **Step 2: Verify admin imports load (system check)**

Run: `./scripts/manage.sh check`
Expected: `System check identified no issues`.

- [ ] **Step 3: Lint**

Run: `ruff check apps/inventory/ && ruff format apps/inventory/`
Expected: clean.

- [ ] **Step 4: Run the FULL project test suite**

Run: `./scripts/test.sh`
Expected: all tests pass, 0 warnings. Confirm the new stock tests are included and the flipped 2a/2b permission tests pass. Report the pass count and coverage. Leave ALL changes uncommitted for the user to review and commit.

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- `StockLot` / `StockAdjustment` models, unique key, indexes → Task 1.
- Member-level inventory writes + updated 2a/2b tests → Task 2.
- Ledger apply logic (ADD/REMOVE, zero-delete, over-remove, uom match), transactional `select_for_update`, `_UnitScopedMixin`, cross-org validation, expiration/uom rules, adjustment API → Task 3.
- `StockLot` read-only API (list/detail, item filter, no direct writes) → Task 4.
- Admin + full verification → Task 5.
- `PROTECT → 409`: no new code needed — the existing `ProtectedDeleteMixin` on Item/UoM detail views already covers the new PROTECT references; covered by the existing `test_protected_delete.py` running green in Task 5's full suite. (No new 409 test is mandated by the spec beyond confirming existing behavior holds.)

**2. Placeholder scan** — no TBD/TODO; every code step shows complete code; every run step shows the exact command and expected result.

**3. Type consistency** — `_apply_adjustment`, `_UnitScopedMixin.get_unit`, `StockAdjustment.AdjustmentType.ADD/REMOVE`, related_names (`stock_lots`, `stock_adjustments`), route names, and serializer context keys (`org_id`, `unit_id`) are used identically across tasks. `StockLotSerializer` quantity asserts `"4.00"` (DecimalField serializes to a 2-dp string).

One gap noted and accepted: concurrent ADD of a not-yet-existing identical lot is backstopped by the DB unique constraint (rare 500), not retried in-app — documented in `_apply_adjustment` and in the spec's concurrency note. Deferred as out-of-scope hardening.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-03-inventory-stock-adjustments.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, two-stage review between tasks, fast iteration (this is how 2a/2b were run).
2. **Inline Execution** — execute tasks in this session with checkpoints for review.

Which approach?
