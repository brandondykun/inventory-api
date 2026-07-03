# Design — `inventory` app, Slice 2c: Stock & adjustments

**Date:** 2026-07-03
**Status:** Approved, pending implementation plan

## Context

Slices 2a and 2b delivered the inventory *definitions*: the catalog
(`UnitType`, `UnitOfMeasure`, `Item`), the nestable location tree
(`InventoryUnit`), and par templates (`ParTemplate`, `ParTemplateItem`, the
`InventoryUnit.par_template` FK) — all org-scoped, with cross-org FK validation,
the seeding signal, and the `ProtectedError → 409` handling on catalog deletes.

This spec covers **Slice 2c: stock & adjustments** — the first *operational*,
write-heavy layer. It introduces the live "what is actually on hand" state
(`StockLot`) and the single audited way that state changes (`StockAdjustment`):
quick **add** (receiving) and **reduce** (consumption) actions that any member
can record in the field.

### Scope split (updated decomposition)

The original roadmap lumped "stock & submissions" into one slice. During
brainstorming we split it, because the quick add/reduce workflow is the core
feature, it fully populates the live state on its own, and it is the only thing
the alert engine actually needs:

- **2a — Catalog & locations** (done, merged): `UnitType`, `UnitOfMeasure`,
  `Item`, `InventoryUnit`.
- **2b — Par templates** (done): `ParTemplate`, `ParTemplateItem`,
  `InventoryUnit.par_template`.
- **2c — Stock & adjustments (this spec):** `StockLot` (live on-hand),
  `StockAdjustment` (audited add/reduce ledger), read/write APIs, and a
  permission relaxation to member-level inventory writes.
- **2c2 — Submissions & reconciliation** (deferred): `InventorySubmission`,
  `InventorySubmissionItem`, `SubmissionLot`, the count lifecycle, wholesale
  reconciliation into `StockLot`, and variance against the par snapshot.
- **2d — Alert engine** (deferred): low-quantity and expiring-soon detection,
  reading `StockLot`.

## Goals

- Store the **live believed on-hand** stock of each item in each unit, grouped
  by expiration lot (`StockLot`), as a queryable, indexed read surface for 2d.
- Let any org member record a **stock adjustment** — a typed **ADD**
  (receiving) or **REMOVE** (consumption) of a quantity — that mutates on-hand
  stock and leaves a permanent audit record (who, when, why).
- Support the two shapes of "reduce" the domain needs:
  - **Non-expiration items:** a single on-hand quantity that goes up/down.
  - **Expiration items:** multiple lots; the user names the specific lot the
    adjustment hits, and receiving a new batch creates a new lot.
- **Relax inventory writes to member-level** across the whole inventory app so a
  team can build out and operate its inventory without an admin bottleneck.
- Reuse 2a/2b conventions throughout: `BaseModel`, org-scoped nested routes,
  cross-org FK validation, the error envelope, `StandardResultsSetPagination`,
  and the existing `ProtectedError → 409` handling.

## Non-goals (out of scope for this slice)

- **Submissions, counts, reconciliation, variance** (Slice 2c2). This slice has
  no count lifecycle; stock is populated and changed only via adjustments.
- **Alerts** (Slice 2d). `StockLot` is indexed for the expiration sweep and the
  per-unit rollup, but nothing here reads those for alerting.
- **Unit conversion.** An adjustment's `unit_of_measure` must match the lot it
  touches; the app never converts between units.
- **Editing or deleting an adjustment.** The ledger is append-only; a mistake is
  corrected by posting a compensating adjustment (see Business rules).
- **Direct `StockLot` writes.** `StockLot` is derived state; it has no
  create/update/delete endpoints. It changes only as a side effect of an
  adjustment.
- **Entitlement limits on stock.** Stock is not a metered resource; no plan cap
  is added.
- **FEFO / automatic lot selection, serial-number tracking, cost/valuation,
  transfers between units.**

## Conventions

Models inherit `apps.common.models.BaseModel` (UUID pk + `created_at`/
`updated_at`). Stock endpoints are nested under the **unit**
(`.../units/{unit_id}/...`), mirroring how 2b nested par lines under the
template. Org is reached **through the unit** (`unit__organization_id`) — like
`ParTemplateItem` reaches it through `template__organization_id` — so no
denormalized `organization` FK is added to the stock models. Errors flow through
`apps.common.exceptions.api_exception_handler`; lists use
`StandardResultsSetPagination` over an explicitly ordered queryset. Every FK
choice is validated to the URL org in the serializer.

## Core model — ledger + derived balance

`StockAdjustment` is the **single audited writer**; `StockLot` is **derived
state**. A lot's `quantity` is the running result of its adjustments, maintained
**incrementally**: recording an adjustment inserts one ledger row *and* updates
the one affected `StockLot` row in the same transaction. Reading on-hand is a
single indexed row lookup that never scans history. "StockLot = sum of its
adjustments" is an invariant the system maintains, not a computation performed
on read — which is exactly why adjustments are append-only (an editable ledger
could drift from the stored balance). This is the ledger + running-balance
pattern; history grows unboundedly but is only queried when explicitly
requested.

## Data model

### `StockLot`

The live believed on-hand of one item in one unit, for one expiration lot.
Read-only via the API.

- `unit` (FK → InventoryUnit, `CASCADE`, `related_name="stock_lots"`)
- `item` (FK → Item, `PROTECT`, `related_name="stock_lots"`)
- `quantity` (`DecimalField`, `max_digits=10`, `decimal_places=2`) — always
  `> 0`; a lot driven to zero is deleted.
- `unit_of_measure` (FK → UnitOfMeasure, `PROTECT`,
  `related_name="stock_lots"`)
- `expiration_date` (`DateField`, `null=True`, `blank=True`) — `null` =
  non-perishable.
- `lot_number` (`CharField`, max 100, `blank=True`)
- `Meta`:
  - `constraints`: `UniqueConstraint(fields=["unit", "item",
    "expiration_date", "lot_number"], nulls_distinct=False,
    name="uniq_stock_lot")` — one canonical row per logical lot. With
    `nulls_distinct=False` (Postgres 17 / Django 5.2), a non-expiration item
    (null date, blank lot) collapses to a single lot instead of allowing
    duplicate null-keyed rows.
  - `indexes`: `Index(fields=["expiration_date"])` (2d nightly expiration
    sweep) and `Index(fields=["unit", "item"])` (2d per-unit low-quantity
    rollup).
  - `ordering = ["item__name", "expiration_date"]`

Dropped from the pre-org-app draft: `last_counted_at` (a count concept → 2c2)
and the hand-rolled `updated_at` (`BaseModel` supplies `created_at`/
`updated_at`).

### `StockAdjustment`

An append-only ledger of every add/reduce. Create + list + retrieve only.

- `unit` (FK → InventoryUnit, `CASCADE`, `related_name="stock_adjustments"`)
- `item` (FK → Item, `PROTECT`, `related_name="stock_adjustments"`)
- `unit_of_measure` (FK → UnitOfMeasure, `PROTECT`,
  `related_name="stock_adjustments"`)
- `adjustment_type` (`CharField` + `TextChoices`: `ADD = "add"`,
  `REMOVE = "remove"`)
- `quantity` (`DecimalField`, `max_digits=10`, `decimal_places=2`) — a positive
  magnitude, not signed; direction comes from `adjustment_type`.
- `expiration_date` (`DateField`, `null=True`, `blank=True`) — identifies the
  target lot.
- `lot_number` (`CharField`, max 100, `blank=True`) — identifies the target lot.
- `reason` (`CharField`, max 255, `blank=True`) — audit note.
- `created_by` (FK → `settings.AUTH_USER_MODEL`, `SET_NULL`, `null=True`,
  `related_name="stock_adjustments"`) — who recorded it; `created_at` is when.
- `Meta`: `ordering = ["-created_at"]`; `indexes`:
  `Index(fields=["unit", "item"])` (history lookups).

There is **no FK from `StockAdjustment` to `StockLot`**. They share the logical
key `(unit, item, expiration_date, lot_number)`, so deleting a zeroed lot never
orphans ledger history.

`PROTECT` on `item`/`unit_of_measure` (on both models) means a catalog row that
has stock or adjustment history cannot be deleted until those are gone — this
compounds 2b's `PROTECT` fallout and is surfaced by the same existing handler
(see Business rules).

## Business rules

### Applying an adjustment (transactional)

Recording an adjustment runs inside a DB transaction, taking a
`select_for_update` lock on the matching `StockLot` (keyed by `unit`, `item`,
`expiration_date`, `lot_number`) to serialize concurrent adjustments:

- **ADD:** if no matching lot exists, create it with the adjustment's
  `quantity` and `unit_of_measure`; otherwise `quantity += adjustment.quantity`.
- **REMOVE:** the lot must exist with `quantity >= adjustment.quantity`
  (otherwise `400`); then `quantity -= adjustment.quantity`, and if the result
  is `0`, delete the lot row.

The ledger row is always inserted (even for a REMOVE that deletes the lot),
preserving the full audit trail.

### Validation

- **Cross-org isolation.** `item` and `unit_of_measure` must belong to the URL
  org (validated against `context["org_id"]`). Adjustment querysets are scoped
  through `unit__organization_id`, and the parent unit is resolved with
  `get_object_or_404(InventoryUnit, pk=unit_id, organization_id=org_id)`, so one
  org cannot reach another org's unit, stock, or history.
- **Quantity.** `quantity` must be `> 0`.
- **Unit of measure.** Optional in the request; defaults to the item's
  `default_unit_of_measure` when omitted. If none is provided and the item has
  no default, `400`. On an ADD to an existing lot, or any REMOVE, it must match
  the target lot's `unit_of_measure` (no conversion) → `400` on mismatch.
- **Expiration handling.**
  - Item with `tracks_expiration=True`: `expiration_date` is **required on ADD**
    (you cannot receive a perishable with no date); on REMOVE the caller must
    name the specific lot (`expiration_date` [+ `lot_number`]) — a REMOVE that
    resolves to no lot returns `400`.
  - Item with `tracks_expiration=False`: `expiration_date` must be empty; the
    single (null-date, blank-lot) lot is used.

### Append-only ledger

Adjustments cannot be edited or deleted through the API. A correction is a new,
opposite adjustment (e.g. an `ADD` of 3 with `reason="miscount correction"`).
This keeps the stored `StockLot.quantity` and the audit trail permanently
consistent.

### `PROTECT` fallout — already surfaced

Because `StockLot`/`StockAdjustment` `PROTECT` `Item` and `UnitOfMeasure`,
deleting a catalog row that has stock or adjustment history raises
`django.db.models.ProtectedError`. The existing `ProtectedDeleteMixin` on the
`Item` and `UnitOfMeasure` **DELETE** endpoints (built in 2a, extended in 2b)
already catches this and returns `409 Conflict`; this slice adds no new delete
handling, only new `PROTECT` references that it covers. Deleting a **unit**
CASCADEs its stock lots and adjustment history.

## Permission change — member-level inventory writes

For v1, **any org member (not just admins) may create, update, and delete all
inventory resources** — catalog, locations, par templates, and the new
stock/adjustments — so a team can build and run its inventory without an admin
bottleneck. Admin/owner roles still govern *organization* management (members,
invites, ownership, and future billing); nothing there changes.

Implementation: `apps.inventory.views.OrgScopedMixin.get_permissions` currently
returns `IsOrgAdmin` for unsafe methods; the write branch changes to
`IsOrgMember` (reads already require `IsOrgMember`). The method-branch structure
is retained so a future slice can re-gate specific actions with a one-line
change. Because every inventory view builds on this mixin, the relaxation covers
2a, 2b, and 2c uniformly.

This is a deliberate relaxation of behavior 2a/2b shipped, so the affected
existing permission tests are updated as part of this slice — e.g.
`test_member_read_admin_write` assertions flip from member-write → `403` to
member-write → `200/201`, and equivalent admin-only assertions across the 2a/2b
API test suites.

## API surface

All endpoints require authentication, are org-scoped, and are mounted under the
existing `/api/` inventory include. Read and write both require `IsOrgMember`
(per the permission change above). New nested routes live under a unit.

A new `_UnitScopedMixin(OrgScopedMixin)` (mirroring 2b's `_TemplateScopedMixin`)
resolves the parent unit via
`get_object_or_404(InventoryUnit, pk=self.kwargs["unit_id"],
organization_id=self.get_org_id())`, adds `unit_id` to the serializer context,
and scopes querysets by `unit_id=...` + `unit__organization_id=...`.

### Stock lots (read-only)

- `GET /api/organizations/{org_id}/units/{unit_id}/stock-lots/` — list the
  unit's current on-hand lots; optional `?item={item_id}` filter.
- `GET /api/organizations/{org_id}/units/{unit_id}/stock-lots/{id}/` — retrieve
  one lot.

### Stock adjustments (append-only)

- `GET /api/organizations/{org_id}/units/{unit_id}/adjustments/` — list the
  unit's adjustment history (newest first); optional `?item={item_id}` filter.
- `POST /api/organizations/{org_id}/units/{unit_id}/adjustments/` — record an
  add/reduce (`item`, `adjustment_type`, `quantity`, optional
  `unit_of_measure`, `expiration_date`, `lot_number`, `reason`). Applies the
  adjustment transactionally and returns `201`. `created_by` is stamped from
  `request.user`; `unit` from the URL.
- `GET /api/organizations/{org_id}/units/{unit_id}/adjustments/{id}/` — retrieve
  one adjustment.

Views: `StockLotListView`/`StockLotDetailView` (`ListAPIView`/`RetrieveAPIView`)
and `StockAdjustmentListCreateView`/`StockAdjustmentDetailView`
(`ListCreateAPIView`/`RetrieveAPIView` — no update/destroy).

## Migration

One new inventory migration (`0006`) adds `StockLot` and `StockAdjustment`
(including the unique constraint and the three indexes). No changes to 2a/2b
tables. Follows the existing sequential migration chain.

## Admin

Register `StockLot` and `StockAdjustment` with `@admin.register`, matching the
existing pattern: `list_display`, `list_filter`, `search_fields`, and
`raw_id_fields` for FKs. `StockLot` is effectively read-derived; adjustments are
the ledger — admin exposure is for support/inspection.

## Testing

TDD with pytest under `config.settings.test`; tests + factories in
`apps/inventory/tests/`. Coverage:

- **Models/factories** for `StockLot` and `StockAdjustment`, including the
  `nulls_distinct=False` unique constraint (a second null-date/blank-lot lot for
  the same unit+item is rejected).
- **ADD behavior:** first ADD creates a lot; a second ADD to the same
  (item, expiration_date, lot_number) increments it; receiving a *new*
  expiration lot creates a distinct lot.
- **REMOVE behavior:** decrements the named lot; a REMOVE that zeroes a lot
  deletes the row (ledger row survives); over-reduce (`quantity` > on-hand) →
  400; REMOVE naming a non-existent lot → 400.
- **Expiration rules:** ADD for a `tracks_expiration` item without
  `expiration_date` → 400; providing `expiration_date` for a non-expiration item
  → 400; non-expiration add/reduce works on the single collapsed lot.
- **Unit of measure:** defaults from the item when omitted; missing default +
  none provided → 400; mismatched UoM against an existing lot → 400.
- **Cross-org isolation:** an adjustment whose `item`/`unit_of_measure` belongs
  to another org → 400; the unit, its stock lots, and its adjustments are
  unreachable from another org (404 on foreign unit_id / detail).
- **Ledger invariant:** after a sequence of adds/removes, `StockLot.quantity`
  equals the net of the adjustments; adjustments expose no update/delete route.
- **Concurrency (light):** two adjustments against the same lot serialize
  correctly (documented; `select_for_update` path exercised).
- **`PROTECT` → 409:** deleting an `Item` (and a `UnitOfMeasure`) referenced by a
  stock lot or an adjustment returns 409, not 500.
- **Permissions (relaxed):** a plain member can now create/update/delete
  inventory resources (stock adjustments *and* 2a/2b catalog/par endpoints);
  non-members still get 403; cross-org detail access returns 404. Existing 2a/2b
  permission tests are updated to reflect member-level writes.

## Deferred / follow-up slices

1. **2c2 — Submissions & reconciliation:** `InventorySubmission`,
   `InventorySubmissionItem`, `SubmissionLot`; the `in_progress → completed`
   count lifecycle; wholesale reconciliation of a counted item's lots into
   `StockLot`; `expected_quantity` snapshotted from the unit's par; variance.
   Reintroduces `StockLot.last_counted_at`.
2. **2d — Alert engine:** low-quantity (unit on-hand below a par line's
   `min_quantity`/`par_quantity` from the assigned active template) and
   expiring-soon (`StockLot.expiration_date` within `Item.
   expiration_warning_days`, org default fallback) detection, over the two
   `StockLot` indexes; likely an `Alert` model + Celery-beat sweep.
3. **Billing slice:** Stripe + enforcement of the location/item caps on writes.
