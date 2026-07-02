# Design — `organizations` app (Slice 1)

**Date:** 2026-07-01
**Status:** Approved, pending implementation plan

## Context

We are building out the inventory application on top of the existing DRF base
API (`apps/common`, `apps/users`, `apps/authentication`). A set of domain models
was drafted covering organizations, membership, billing, and inventory. This
spec covers the **first build slice only**: the `organizations` app, end-to-end,
with billing modeled but Stripe left unwired.

### App decomposition (decided)

The drafted models split into two apps:

- **`organizations`** — `Organization`, `Membership`, `Invite`, `Plan`,
  `Subscription`. Billing (`Plan`/`Subscription`) lives here rather than in its
  own app because it is mutually referential with `Organization` (the org's
  entitlement methods read its subscription), and splitting two models out now
  would only invite circular-import friction.
- **`inventory`** — everything else (`UnitType`, `UnitOfMeasure`, `Item`,
  `ParTemplate`/`ParTemplateItem`, `InventoryUnit`, `StockLot`,
  `InventorySubmission`/`InventorySubmissionItem`, `SubmissionLot`). Built in a
  later slice.

`inventory` depends on `organizations` (everything is org-scoped), so
`organizations` is built first.

## Goals

Deliver a usable organizations foundation:

- Create an organization; become its owner and first admin.
- Invite existing users into an org by account; they accept or decline in-app.
- Manage members and roles.
- Transfer ownership.
- Every org has a `Subscription` (free plan by default) so entitlement checks
  always have something to read — but no real payment integration yet.

## Non-goals (out of scope for this slice)

- Stripe: checkout, webhooks, subscription status/period sync, plan
  upgrades/downgrades. The Stripe columns exist on `Subscription` but are unwired.
- Anything inventory: units, items, par templates, submissions, stock lots, and
  the per-org seeding of `UnitType`/`UnitOfMeasure`.
- Email-based invites to people without accounts. Invitees must already have an
  account (see Join flow).
- A shared `join_code` join path (dropped; see below).

## Conventions

All new models inherit `apps.common.models.BaseModel` (UUID primary key +
`created_at`/`updated_at`), consistent with the `User` model and the rest of the
repo. This replaces the integer PKs and hand-rolled `created_at` fields in the
original draft. All API errors flow through the existing
`api_exception_handler` envelope; list endpoints use
`StandardResultsSetPagination`.

## Data model

### `Organization`

- Fields: `name`, `description`, `owner` (FK → user, `PROTECT`),
  `created_by` (FK → user, `SET_NULL`, nullable), `members`
  (M2M → user through `Membership`).
- **Drop `join_code`** — invites are the single join path in this slice.
- Methods `usage(resource)`, `can_add(resource, n=1)`, `transfer_ownership(...)`
  are retained from the draft, with these adjustments:
  - `can_add()` is guarded so that a missing subscription returns `False`
    instead of raising `RelatedObjectDoesNotExist`. (In practice one is always
    auto-created; the guard is defensive.)
  - `usage()` keeps the `locations`/`items`/`members` resource map. Only
    `members` is live in this slice; `locations`/`items` reference inventory
    reverse relations that begin resolving once the `inventory` app ships.

### `Membership`

- Fields: `organization` (FK), `user` (FK), `role` (`admin` | `member`, default
  `member`). `created_at` from `BaseModel` doubles as the "joined at" time.
- `unique_together = (organization, user)`.

### `Invite`

- Invitee **must already have an account**. Kept as a direct FK to `user` (not
  an email). Fields:
  - `organization` (FK)
  - `user` (FK → user; the invitee)
  - `role` (`admin` | `member`; the role granted on accept, default `member`)
  - `invited_by` (FK → user, `SET_NULL`, nullable)
  - `status` (`pending` | `accepted` | `declined`, default `pending`)
- **Conditional unique constraint:** at most one `pending` invite per
  (`organization`, `user`). A previously declined/accepted invite does not block
  a fresh one.
- `accept()` creates the `Membership` (idempotent w.r.t. existing membership)
  and marks the invite `accepted`. `decline()` marks it `declined`.

### `Plan`

- Unchanged from the draft (`tier` unique, `name`, `max_locations`,
  `max_items`, `max_members`, `stripe_price_id`, `monthly_price_cents`,
  `is_active`). Seeded via a data migration (Free / Pro / Enterprise) so pricing
  lives in data, not code.

### `Subscription`

- Unchanged fields from the draft, including the Stripe columns
  (`stripe_customer_id`, `stripe_subscription_id`, `current_period_end`) which
  are present but **unwired** in this slice.
- One per organization (`OneToOne`). Auto-created on the Free plan with status
  `ACTIVE` when an org is created.
- `limit_for(resource)` retained (per-subscription override wins over plan).

## Lifecycle / signals

On `Organization` creation (`post_save`, guarded on `created`):

1. Create the owner's `Membership` with role `admin` (fixes the draft gap where
   the owner was not automatically a member).
2. Create a `Subscription` on the Free plan, status `ACTIVE`.

The Free plan row must exist before a subscription can be created; the data
migration that seeds `Plan` rows is a prerequisite. `UnitType`/`UnitOfMeasure`
seeding is **not** part of this app — it moves to the `inventory` app and fires
from there on org creation.

## Business rules

- **One free org per owner.** A user may *own* at most one Free-plan
  organization. Enforced on:
  - **Creation** — creating a second free org is rejected.
  - **Transfer** — `transfer_ownership` rejects handing a free org to someone
    who already owns a free org (existing draft behavior, retained).
- **Membership is free and unlimited for the individual.** Being a *member* of
  an org never costs the user anything and is not subject to the free-org limit.
  Payment is entirely at the organization level, borne by the owner.
- **Taking over a paid org** via transfer carries no free-org check; the new
  owner assumes that org's billing. (Existing `transfer_ownership` only applies
  the free-org check when `plan.tier == FREE`.)

## API surface

All endpoints require authentication and are scoped to orgs the requesting user
belongs to. Roles: `admin` (manage org/members/invites/transfer) and `member`
(read). The owner is always an admin; only the owner may transfer ownership.

### Organizations

- `POST /api/organizations/` — create. Creator becomes owner + admin membership;
  a free subscription is auto-created. Enforces one-free-org-per-owner.
- `GET /api/organizations/` — list orgs the caller belongs to.
- `GET /api/organizations/{id}/` — retrieve (member).
- `PATCH /api/organizations/{id}/` — update `name`/`description` (admin).
- `POST /api/organizations/{id}/transfer-ownership/` — owner only.

### Members

- `GET /api/organizations/{id}/members/` — list (member).
- `PATCH /api/organizations/{id}/members/{user_id}/` — change role (admin).
- `DELETE /api/organizations/{id}/members/{user_id}/` — remove (admin; the owner
  cannot be removed).

### Invites

- `POST /api/organizations/{id}/invites/` — admin invites an existing user by
  email lookup; a non-existent account is a validation error. Creates a pending
  invite.
- `GET /api/organizations/{id}/invites/` — list the org's invites (admin).
- `GET /api/invites/` — invites addressed to the caller.
- `POST /api/invites/{id}/accept/` — invitee accepts → membership created.
- `POST /api/invites/{id}/decline/` — invitee declines.

## Testing

TDD with pytest under `config.settings.test`; tests in
`apps/organizations/tests/`. Coverage:

- Lifecycle signals: owner admin membership + free subscription created on org
  creation.
- One-free-org guard on creation.
- Invite accept/decline → membership creation; conditional-unique pending invite.
- Role-based permission checks across endpoints (member vs admin vs owner).
- `transfer_ownership`: recipient-must-be-member, free-org block, admin
  promotion of the recipient.

## Deferred / follow-up slices

1. Real billing: Stripe checkout + webhook sync of subscription status/period,
   plan upgrades/downgrades, entitlement enforcement on writes.
2. `inventory` app: the remaining models, per-org `UnitType`/`UnitOfMeasure`
   seeding on org creation, par templates, submissions, stock reconciliation,
   and the low-quantity / expiring-soon alert engine.
