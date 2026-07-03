# Design — `inventory` app, Slice 2b: Par templates

**Date:** 2026-07-03
**Status:** Approved, pending implementation plan

## Context

Slice 2a delivered the inventory catalog (`UnitType`, `UnitOfMeasure`, `Item`)
and the nestable location tree (`InventoryUnit`), with org-scoped CRUD APIs, the
per-org seeding signal, and the `max_subdivisions` entitlement. This spec covers
**Slice 2b: par templates** — the "should-be" definition of what an inventory
unit is supposed to hold.

A par template is a named list of items with target ("par") quantities, owned by
an org and assignable to many units (e.g. one template for a whole fleet of
identical ambulances). 2a deliberately deferred the `InventoryUnit.par_template`
FK to this slice; 2b adds it. Par templates supply the "expected" side that
Slice 2c's submissions/reconciliation and Slice 2d's low-quantity alerts will
read against.

### Where this sits in the inventory decomposition

- **2a — Catalog & locations** (done, merged): `UnitType`, `UnitOfMeasure`,
  `Item`, `InventoryUnit`.
- **2b — Par templates (this spec):** `ParTemplate`, `ParTemplateItem`, the
  `InventoryUnit.par_template` FK, CRUD + assignment.
- **2c — Stock & submissions:** `StockLot`, submissions, reconciliation,
  variance.
- **2d — Alert engine:** expiring-soon / low-quantity detection.

## Goals

- Let an org define **par templates**: a named, describable list of items each
  with a target `par_quantity` and an optional `min_quantity`, in a chosen unit
  of measure.
- **Assign** a template to inventory units (one template per unit; a template
  may serve many units).
- Retire a template without deleting it, via an **`is_active`** soft-disable.
- Full org-scoped CRUD, reusing 2a's `OrgScopedMixin`, permission classes,
  pagination, and error envelope, with cross-org FK validation throughout.
- Harden the existing `Item` / `UnitOfMeasure` delete endpoints against the
  `ProtectedError` that this slice's `PROTECT` foreign keys introduce.

## Non-goals (out of scope for this slice)

- **Stock, submissions, reconciliation, variance** (Slice 2c). Par templates are
  the "should-be" only; nothing here reads or writes actual stock.
- **Alerts** (Slice 2d). `is_active` and `min_quantity` are stored for later
  consumption but drive no alerting here.
- **Fully nested writable templates.** Lines are edited through their own
  sub-resource endpoints, not by posting a `lines` array to the template (see
  API surface). The template detail GET returns lines nested for convenience;
  writes go line-by-line.
- **Entitlement limits on par templates.** Par templates are org configuration,
  not a metered resource — no plan cap is added (unlike locations/items/
  subdivisions).
- **Copying/cloning templates, versioning, or per-unit line overrides.**

## Conventions

Models inherit `apps.common.models.BaseModel` (UUID pk + `created_at`/
`updated_at`). Endpoints are nested under the org and reuse
`apps.inventory.views.OrgScopedMixin` and the org app's `IsOrgMember` (read) /
`IsOrgAdmin` (write) permission classes. Errors flow through
`apps.common.exceptions.api_exception_handler`; lists use
`StandardResultsSetPagination` over an explicitly ordered queryset. Every FK
choice is validated to the URL org in the serializer.

## Data model

### `ParTemplate`

The ideal set of items and counts for a unit (the "should-be"). Owned by the org
and assignable to many units.

- `organization` (FK → Organization, `CASCADE`, `related_name="par_templates"`)
- `name` (`CharField`, max 255)
- `description` (`TextField`, blank)
- `is_active` (`BooleanField`, default `True`)
- `Meta`: `ordering = ["name"]`

### `ParTemplateItem`

One line of a template: an item and its target quantity.

- `template` (FK → ParTemplate, `CASCADE`, `related_name="lines"`)
- `item` (FK → Item, `PROTECT`, `related_name="par_lines"`)
- `par_quantity` (`DecimalField`, `max_digits=10`, `decimal_places=2`)
- `min_quantity` (`DecimalField`, `max_digits=10`, `decimal_places=2`,
  `null=True`, `blank=True`)
- `unit_of_measure` (FK → UnitOfMeasure, `PROTECT`, `related_name="par_lines"`)
- `Meta`: `unique_together = ("template", "item")`, `ordering = ["item__name"]`

`PROTECT` on `item` and `unit_of_measure` means a catalog row that is referenced
by a par line cannot be deleted until the line is removed (see Business rules for
how the API surfaces this).

### `InventoryUnit.par_template` (added to the existing 2a model)

- `par_template` (FK → ParTemplate, `null=True`, `blank=True`, `SET_NULL`,
  `related_name="units"`)

Added by a new inventory migration. Deleting a template detaches it from its
units (SET_NULL) rather than deleting them.

## Business rules

- **One template per unit.** `InventoryUnit.par_template` is a single FK; a
  template may be assigned to many units, but a unit references at most one.
- **`is_active` soft-disable.** An inactive template stays assigned to any unit
  already using it and keeps working, but:
  - `GET /par-templates/` returns **active templates only by default**; pass
    `?is_active=false` to list inactive ones, or `?is_active=all` for both.
  - Assigning an **inactive** template to a unit (on unit create or update) is
    rejected with `400`.
- **Cross-org isolation.** A line's `item` and `unit_of_measure` must belong to
  the same org as the template; a unit's `par_template` must belong to the
  unit's org. Violations return `400`. Line querysets are scoped through the
  template's organization so one org cannot reach another org's template or
  lines.
- **Quantity sanity.** `par_quantity` must be `>= 0`; when `min_quantity` is
  provided it must be `<= par_quantity`. Violations return `400`.
- **Duplicate lines.** `unique_together (template, item)` — a second line for the
  same item in one template returns `400`.
- **`PROTECT` fallout — surfaced cleanly.** Because par lines `PROTECT` `Item`
  and `UnitOfMeasure`, deleting a catalog row that a par line references raises
  `django.db.models.ProtectedError`. The existing `Item` and `UnitOfMeasure`
  **DELETE** endpoints (built in 2a) are updated to catch `ProtectedError` and
  return **`409 Conflict`** with a message naming the blocking reference,
  instead of an unhandled `500`.

## API surface

All endpoints require authentication and are org-scoped. Read = `IsOrgMember`;
write (create/update/delete) = `IsOrgAdmin`. Mounted under the existing `/api/`
inventory include.

### Par templates

- `GET /api/organizations/{org_id}/par-templates/` — list (active by default;
  `?is_active=false|all` to widen).
- `POST /api/organizations/{org_id}/par-templates/` — create the header
  (`name`, `description`, `is_active`).
- `GET /api/organizations/{org_id}/par-templates/{id}/` — retrieve; response
  includes the template header **and its `lines` nested** (read-only).
- `PATCH /api/organizations/{org_id}/par-templates/{id}/` — update header fields
  only (`name`, `description`, `is_active`).
- `DELETE /api/organizations/{org_id}/par-templates/{id}/` — delete; cascades its
  lines and SET_NULLs any unit that pointed at it.

### Par template lines (sub-resource)

- `GET /api/organizations/{org_id}/par-templates/{template_id}/lines/` — list a
  template's lines.
- `POST …/lines/` — add a line (`item`, `par_quantity`, `min_quantity`,
  `unit_of_measure`), with cross-org + quantity + duplicate validation.
- `GET|PATCH|DELETE …/lines/{id}/` — retrieve / update / remove a line.

### Unit assignment (existing 2a endpoints)

- `PATCH /api/organizations/{org_id}/units/{id}/` — `par_template` becomes an
  assignable field on `InventoryUnitSerializer`, validated for same-org and
  `is_active` (assigning an inactive template → `400`). Passing `null` clears the
  assignment.

## Testing

TDD with pytest under `config.settings.test`; tests + factories in
`apps/inventory/tests/`. Coverage:

- **Models/factories** for `ParTemplate` and `ParTemplateItem`.
- **Cross-org rejection:** a line whose `item` or `unit_of_measure` belongs to
  another org → 400; assigning a `par_template` from another org to a unit → 400.
- **`is_active`:** list defaults to active only; `?is_active=false`/`all` widen;
  assigning an inactive template to a unit → 400; existing assignment to a
  now-inactive template still resolves.
- **Quantity rules:** negative `par_quantity` → 400; `min_quantity` >
  `par_quantity` → 400; `min_quantity` null allowed.
- **`unique_together`:** duplicate `(template, item)` line → 400.
- **`PROTECT` → 409:** deleting an `Item` (and a `UnitOfMeasure`) referenced by a
  par line returns 409, not 500; deleting one *not* referenced still returns 204.
- **Permissions:** member can read templates/lines, cannot write; admin can
  write; non-members get 403; cross-org detail access on templates and lines
  returns 404.
- **Nested read:** template detail includes its `lines`; line CRUD is scoped to
  the template and org.
- **Migration:** the `InventoryUnit.par_template` FK migration applies; a unit
  can be assigned and cleared.

## Deferred / follow-up slices

1. **2c — Stock & submissions:** `StockLot`,
   `InventorySubmission`/`InventorySubmissionItem`/`SubmissionLot`, the count
   lifecycle and reconciliation, variance against the par snapshot.
2. **2d — Alert engine:** low-quantity (below par/`min_quantity`) and
   expiring-soon detection, reading `is_active` templates.
3. **Billing slice:** Stripe + enforcement of the location/item caps on writes.
