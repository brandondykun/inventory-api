# Design — `inventory` app, Slice 2a: Catalog & locations

**Date:** 2026-07-02
**Status:** Approved, pending implementation plan

## Context

Slice 1 delivered the `organizations` app (orgs, membership, invites, billing
modeled but unwired). This spec covers the **first slice of the `inventory`
app**: the catalog (`UnitType`, `UnitOfMeasure`, `Item`) and the physical
location tree (`InventoryUnit`, now with sub-units), plus the per-org seeding of
default unit types / units of measure that the org spec explicitly reserved for
this app.

The `organizations` app already reaches into `inventory` through two reverse
relations used by its entitlement plumbing:

- `Organization.usage("locations")` reads `self.units` → `InventoryUnit`.
- `Organization.usage("items")` reads `self.items` → `Item`.

This slice fills both hooks.

### App decomposition (the whole `inventory` app)

`inventory` is too large for one spec. It is built in four slices, each with its
own spec → plan → implementation cycle:

- **2a — Catalog & locations (this spec):** `UnitType`, `UnitOfMeasure`, `Item`
  (self-nesting), `InventoryUnit` (sub-unit nesting + subdivisions limit), the
  per-org seeding signal, the org-app entitlement extension, CRUD APIs,
  permissions, tests.
- **2b — Par templates:** `ParTemplate`, `ParTemplateItem`, the
  `InventoryUnit.par_template` FK (added by migration here), assignment + CRUD.
- **2c — Stock & submissions:** `StockLot`,
  `InventorySubmission`/`InventorySubmissionItem`/`SubmissionLot`, the count
  lifecycle (`in_progress → completed`) and reconciliation into `StockLot`,
  variance.
- **2d — Alert engine:** expiring-soon + low-quantity (below par/min) detection,
  an `Alert` model, a Celery-beat sweep (the repo already runs `worker`/`beat`
  containers), notifications/API.

`inventory` depends on `organizations`; nothing depends on `inventory` yet.

## Goals

- Give each org an editable catalog: **unit types** (categories of location:
  vehicle, room, cage…), **units of measure** (individual, box, bag…), and
  **items** (the "what" that gets inventoried).
- Model **physical locations** as `InventoryUnit`, which may be **nested**: an
  ambulance (a vehicle unit) subdivided into cabinets; a storage room subdivided
  by cabinet. Any unit — parent or child — can hold stock in later slices.
- **Seed** every new org with its own editable copies of the default unit types
  and units of measure on creation.
- Extend the entitlement model so **subdivisions are metered**: top-level units
  count against the plan's `max_locations`; sub-units count against a new
  per-location `max_subdivisions` cap (Free = 5).
- Full org-scoped CRUD APIs for all four models, reusing the org app's
  permission classes and error/pagination conventions.

## Non-goals (out of scope for this slice)

- **Stock and counting:** `StockLot`, submissions, reconciliation, variance
  (Slice 2c).
- **Par templates:** `ParTemplate`/`ParTemplateItem` and the
  `InventoryUnit.par_template` FK (Slice 2b).
- **Alerts:** expiring-soon / low-quantity detection and the alert engine
  (Slice 2d).
- **Location/item limit enforcement on writes:** modeled via `usage()`/
  `limit_for()`/`can_add()` but not enforced here — enforcement of the
  `locations` and `items` caps remains deferred to the billing slice, per the
  org spec. **Exception:** the new `subdivisions` cap **is** hard-enforced at
  sub-unit creation/reparent in this slice (see Business rules).
- **Serial-number tracking behavior:** `Item.tracks_serial` is stored as a flag
  but drives no logic yet.

## Conventions

All new models inherit `apps.common.models.BaseModel` (UUID primary key +
`created_at`/`updated_at`), consistent with the `User` and `organizations`
models. This replaces the integer PKs and hand-rolled `created_at`/`updated_at`
fields in the original pre-org-app draft of these models.

All API errors flow through the existing `api_exception_handler` envelope; list
endpoints use `StandardResultsSetPagination` over an explicitly ordered
queryset. Endpoints are nested under the org and reuse the org app's
`IsOrgMember` / `IsOrgAdmin` permission classes (which resolve the org from
`view.kwargs["org_id"]`).

## Data model

### `UnitType`

Category of location (vehicle, room, storage cage…). Each org gets its own
editable copies of the defaults at creation, so orgs can rename, delete, or add
freely.

- `organization` (FK → Organization, `CASCADE`, `related_name="unit_types"`)
- `name` (`CharField`, max 100)
- `description` (`TextField`, blank)
- `Meta`: `unique_together = ("organization", "name")`, `ordering = ["name"]`

### `UnitOfMeasure`

How quantities are counted: individual, box, bag, pallet, etc. Org-scoped and
editable like `UnitType`.

- `organization` (FK → Organization, `CASCADE`, `related_name="units_of_measure"`)
- `name` (`CharField`, max 50)
- `abbreviation` (`CharField`, max 10, blank)
- `Meta`: `unique_together = ("organization", "name")`, `ordering = ["name"]`

### `Item`

Catalog definition of something that can be inventoried (the "what"). Physical
stock and expiration live on `StockLot` (Slice 2c), not here.

- `organization` (FK → Organization, `CASCADE`, `related_name="items"`)
- `name` (`CharField`, max 255)
- `description` (`TextField`, blank)
- `sku` (`CharField`, max 100, blank)
- `default_unit_of_measure` (FK → UnitOfMeasure, `null=True`, `blank=True`,
  `SET_NULL`, `related_name="items"`)
- `tracks_expiration` (`BooleanField`, default `False`)
- `tracks_serial` (`BooleanField`, default `False`) — stored only; no behavior
  this slice
- `expiration_warning_days` (`PositiveIntegerField`, `null=True`, `blank=True`)
  — days before expiry to start warning; falls back to an org default when null
  (consumed by Slice 2d)
- `parent` (self-FK, `null=True`, `blank=True`, `SET_NULL`,
  `related_name="children"`) — optional grouping/containment, e.g. a kit/bag
  that contains other items
- `Meta`: `ordering = ["name"]`

### `InventoryUnit`

A place that holds inventory: a vehicle, room, cage, pantry, etc. **May be
nested** to arbitrary depth via `parent`, so a location can be subdivided (an
ambulance into cabinets; a storage room by cabinet). Any unit — parent or
child — may hold stock (in Slice 2c); the parent is both a container and a
grouping, and subtree roll-ups sum descendants.

- `organization` (FK → Organization, `CASCADE`, `related_name="units"`)
- `unit_type` (FK → UnitType, `null=True`, `blank=True`, `SET_NULL`,
  `related_name="units"`)
- `parent` (self-FK, `null=True`, `blank=True`, **`CASCADE`**,
  `related_name="children"`) — deleting a unit deletes its sub-units (and, in
  later slices, their stock); matches "decommission the ambulance." `SET_NULL`
  was rejected because it would promote orphaned sub-units to top-level, where
  they would begin counting against `max_locations`.
- `name` (`CharField`, max 255)
- `description` (`TextField`, blank)
- `Meta`: `ordering = ["name"]`

Deferred to Slice 2b (added by migration there): `par_template` (FK →
ParTemplate, `null=True`, `SET_NULL`). Omitted here so 2a is self-contained.

Helpers:

- `root` — walk up `parent` to the top-level ancestor (`parent IS NULL`). Used
  for subdivision counting.
- `clean()` / `save()` **cycle guard** — reject setting `parent` such that the
  unit becomes its own ancestor (self-parenting or reparenting under a
  descendant). Raises `ValidationError`; surfaced as `400`.

## Org-app entitlement changes (`apps/organizations`)

This slice extends the org app's already-modeled entitlement system.

- **`Plan`**: add `max_subdivisions` (`PositiveIntegerField`, `null=True`,
  `blank=True`; null = unlimited). A schema migration adds the column; a data
  migration seeds **Free = 5**, Pro / Enterprise = unlimited (null).
- **`Subscription`**: add `max_subdivisions_override` (`PositiveIntegerField`,
  `null=True`, `blank=True`). No change to `limit_for()` — its existing
  `getattr(self, f"max_{resource}_override")` / `getattr(self.plan,
  f"max_{resource}")` pattern already resolves `limit_for("subdivisions")`.
- **`Organization.usage("locations")`**: change `self.units.count()` →
  `self.units.filter(parent__isnull=True).count()` — only top-level units count
  as "locations."
- **Per-location subdivisions check**: subdivisions are metered per top-level
  root, not org-wide, so they do not fit the org-global `usage()` map. Add a
  helper — `InventoryUnit.can_add_subdivision(root)` (or an equivalent org
  method) — that counts existing descendants of `root` and compares against
  `subscription.limit_for("subdivisions")` (null = unlimited). This is the one
  entitlement cap **enforced on writes** in this slice.

The existing `usage()`/`limit_for()`/`can_add()` for `locations` and `items`
remain modeled-only; their enforcement on writes stays deferred to the billing
slice.

## Lifecycle / signals

`seed_organization_defaults` moves out of the original draft and into
`apps/inventory/signals.py`, registered in `InventoryConfig.ready()`:

- `post_save` on `sender=Organization`, guarded on `created` (a save to an
  existing org is a no-op).
- Bulk-creates the org's own editable `UnitType` and `UnitOfMeasure` rows from
  module-level `DEFAULT_UNIT_TYPES` / `DEFAULT_UNITS_OF_MEASURE` constants.
- Coexists with the org app's own `post_save` receiver (owner membership + free
  subscription). The two receivers are independent and order-agnostic.

Default seed data (editable per org after creation):

```
DEFAULT_UNIT_TYPES = [
    ("Vehicle", "A vehicle that carries inventory"),
    ("Room", "A room within a building"),
    ("Storage room", "A dedicated storage room"),
    ("Storage cage", "A secured storage cage"),
]
DEFAULT_UNITS_OF_MEASURE = [
    ("Individual", "ea"), ("Box", "bx"), ("Bag", "bag"), ("Pallet", "plt"),
]
```

## Business rules

- **Top-level units are "locations."** `usage("locations")` counts only units
  with `parent IS NULL`. Sub-units do not consume the `max_locations` cap.
- **Subdivisions are metered per location.** For a given top-level root, the
  total number of descendant units (the whole subtree, at any depth) is capped
  at `limit_for("subdivisions")` — **Free = 5**, unlimited when null. Enforced
  at sub-unit **creation** and **reparent**; the 6th sub-unit under a Free-plan
  location is rejected with `400`.
- **No cycles.** A unit cannot be its own ancestor. Self-parenting or
  reparenting a unit under one of its descendants is rejected with `400`.
- **Cascade on delete.** Deleting a unit deletes its sub-units (`parent`
  `on_delete=CASCADE`). Deleting an org cascades to all its catalog and units.
- **Everything is org-scoped.** Every model carries `organization`; every
  queryset and FK choice is filtered to the caller's org. No cross-org
  references (e.g. an `Item.default_unit_of_measure` from another org) are
  possible, enforced in serializer validation.

## API surface

All endpoints require authentication and are scoped to an org the caller belongs
to. Read = `IsOrgMember`; write (create/update/delete) = `IsOrgAdmin`. All
querysets are filtered to `org_id` from the URL. Mounted under the existing
`/api/` include alongside the org routes.

### Unit types

- `GET /api/organizations/{org_id}/unit-types/` — list (member)
- `POST /api/organizations/{org_id}/unit-types/` — create (admin)
- `GET|PATCH|DELETE /api/organizations/{org_id}/unit-types/{id}/` — retrieve
  (member) / update / delete (admin)

### Units of measure

- `GET|POST /api/organizations/{org_id}/units-of-measure/`
- `GET|PATCH|DELETE /api/organizations/{org_id}/units-of-measure/{id}/`

### Items

- `GET|POST /api/organizations/{org_id}/items/` — list filterable by `parent`,
  `tracks_expiration`
- `GET|PATCH|DELETE /api/organizations/{org_id}/items/{id}/`

### Inventory units

- `GET|POST /api/organizations/{org_id}/units/` — list filterable by `parent`,
  `unit_type`; supports reading the nested tree (children serialized under each
  parent, or a `parent` filter for one level)
- `GET|PATCH|DELETE /api/organizations/{org_id}/units/{id}/`

Validation errors (duplicate name within org, cross-org FK, cycle, subdivisions
cap exceeded) return `400` through the standard error envelope.

## Testing

TDD with pytest under `config.settings.test`; tests + factories in
`apps/inventory/tests/`. Coverage:

- **Models/factories** for all four models.
- **Seeding signal:** creating an org bulk-creates its default `UnitType` and
  `UnitOfMeasure` rows; a save to an existing org is a no-op.
- **Uniqueness:** `unique_together (organization, name)` on `UnitType` /
  `UnitOfMeasure`; the same name is allowed across different orgs.
- **Nesting:** cycle guard rejects self-parenting and reparenting under a
  descendant; `root` resolves the top-level ancestor; `on_delete=CASCADE`
  removes sub-units when a parent is deleted.
- **Entitlements:** `usage("locations")` counts top-level units only;
  subdivisions cap enforced on Free (6th sub-unit under a location → `400`) and
  unlimited when the limit is null; Free plan seeded with `max_subdivisions=5`.
- **Permissions:** member can read, cannot write; admin can write; non-members
  get no access.
- **Org-scoping:** no cross-org read/write leakage; FKs
  (`default_unit_of_measure`, `unit_type`, `parent`) must belong to the same
  org.

## Deferred / follow-up slices

1. **2b — Par templates:** `ParTemplate`, `ParTemplateItem`, the
   `InventoryUnit.par_template` FK, assignment + CRUD.
2. **2c — Stock & submissions:** `StockLot`, submissions, reconciliation,
   variance.
3. **2d — Alert engine:** expiring-soon / low-quantity detection, `Alert` model,
   Celery-beat sweep, notifications.
4. **Billing slice (from the org spec):** enforce the `locations` and `items`
   caps on writes, Stripe checkout + webhook sync, plan upgrades/downgrades.
