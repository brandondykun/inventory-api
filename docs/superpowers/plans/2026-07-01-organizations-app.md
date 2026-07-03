# Organizations App (Slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a usable `organizations` Django app — organizations, membership, invites, and billing models — with entitlements wired but Stripe left unimplemented.

**Architecture:** A single `apps/organizations` app holds `Organization`, `Membership`, `Invite`, `Plan`, and `Subscription`. Org creation fires a signal that makes the owner an admin member and attaches a free `Subscription`. Plans are seeded by a data migration. The API is built with plain DRF generics/`APIView` and explicit URL paths (matching the `users` app), scoped by role via permission classes.

**Tech Stack:** Django 5.2, DRF 3.17, Postgres 17, pytest-django, factory-boy. Commands run through the repo scripts: `./scripts/manage.sh <cmd>` and `./scripts/test.sh <pytest args>`.

## Global Constraints

- **Base model:** every model inherits `apps.common.models.BaseModel` (UUID pk + `created_at`/`updated_at`). Do NOT add integer pks or hand-rolled timestamp fields.
- **Error envelope:** raise DRF exceptions (`rest_framework.exceptions.*`) so `apps.common.exceptions.api_exception_handler` wraps them as `{"error": {...}}`. Never hand-build error `Response` bodies.
- **Auth default:** DRF defaults to `IsAuthenticated` + `CookieOrHeaderJWTAuthentication` globally. Every view here additionally scopes by org role.
- **Pagination:** list endpoints inherit `StandardResultsSetPagination` automatically. Do not override.
- **Lint:** ruff, `line-length = 100`, double quotes. Run `uv run ruff check . && uv run ruff format .` at each checkpoint (migrations are excluded from lint).
- **Commits are the user's call:** do NOT run `git commit` automatically. Each task ends at a lint checkpoint; the user reviews and commits when ready. If they later ask for per-task commits, use Conventional Commits prefixes (`feat`, `test`, `chore`, `refactor`) and end the message body with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Tests:** live in `apps/organizations/tests/`, run under `config.settings.test` via `./scripts/test.sh`. TDD: failing test first, minimal code, then pass.
- **Billing is stubbed:** `Subscription` carries Stripe columns but no Stripe calls, webhooks, or checkout exist in this slice.

---

### Task 1: App scaffold, models, migrations, seed plans, factories

**Files:**
- Create: `apps/organizations/__init__.py`
- Create: `apps/organizations/apps.py`
- Create: `apps/organizations/models.py`
- Create: `apps/organizations/migrations/__init__.py`
- Create: `apps/organizations/migrations/0002_seed_plans.py`
- Create: `apps/organizations/tests/__init__.py`
- Create: `apps/organizations/tests/factories.py`
- Create: `apps/organizations/tests/test_models.py`
- Modify: `config/settings/base.py` (add `"apps.organizations"` to `LOCAL_APPS`)

**Interfaces:**
- Produces: `Organization(name, description, owner, created_by, members)`, `Membership(organization, user, role)` with `Role.ADMIN`/`Role.MEMBER`, `Invite(organization, user, role, invited_by, status)` with `Status.PENDING/ACCEPTED/DECLINED`, `Plan(tier, name, max_locations, max_items, max_members, monthly_price_cents, ...)` with `Tier.FREE/PRO/ENTERPRISE`, `Subscription(organization, plan, status, max_*_override, monthly_price_cents_override, stripe_*, current_period_end)` with `Status.ACTIVE/TRIALING/PAST_DUE/CANCELED`.
- Produces: `apps.organizations.tests.factories.OrganizationFactory`.

- [ ] **Step 1: Register the app**

Add to `config/settings/base.py` `LOCAL_APPS` (after `"apps.authentication"`):

```python
LOCAL_APPS = [
    "apps.common",
    "apps.users",
    "apps.authentication",
    "apps.organizations",
]
```

- [ ] **Step 2: Create the package files**

`apps/organizations/__init__.py` — empty.
`apps/organizations/migrations/__init__.py` — empty.
`apps/organizations/tests/__init__.py` — empty.

`apps/organizations/apps.py`:

```python
from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organizations"
```

- [ ] **Step 3: Write the models**

`apps/organizations/models.py`:

```python
"""Organization, membership, invitation, and billing models."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel


class Organization(BaseModel):
    """A tenant that owns inventory, members, and a subscription."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # The single accountable owner. PROTECT so a user who still owns an org
    # can't be deleted — ownership must be transferred first.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_organizations",
    )
    # Audit only: who originally created the org. Never reassigned.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_organizations",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="Membership", related_name="organizations"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Membership(BaseModel):
    """Join row between a user and an organization, carrying their role."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        unique_together = ("organization", "user")

    def __str__(self):
        return f"{self.user} in {self.organization} ({self.role})"


class Invite(BaseModel):
    """An invitation for an existing account to join an organization."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invites"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invites"
    )
    role = models.CharField(
        max_length=20, choices=Membership.Role.choices, default=Membership.Role.MEMBER
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_invites",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    class Meta:
        constraints = [
            # At most one *pending* invite per (org, user). A declined/accepted
            # invite doesn't block a fresh one.
            models.UniqueConstraint(
                fields=["organization", "user"],
                condition=Q(status="pending"),
                name="unique_pending_invite_per_user",
            )
        ]

    def __str__(self):
        return f"Invite: {self.user} -> {self.organization} ({self.status})"


class Plan(BaseModel):
    """A pricing tier. Limits live in data so pricing changes need no deploy.
    A null limit means unlimited."""

    class Tier(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"
        ENTERPRISE = "enterprise", "Enterprise"

    tier = models.CharField(max_length=20, choices=Tier.choices, unique=True)
    name = models.CharField(max_length=100)
    max_locations = models.PositiveIntegerField(null=True, blank=True)  # null = unlimited
    max_items = models.PositiveIntegerField(null=True, blank=True)
    max_members = models.PositiveIntegerField(null=True, blank=True)
    stripe_price_id = models.CharField(max_length=100, blank=True)
    monthly_price_cents = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Subscription(BaseModel):
    """One per organization. Holds entitlement state and (unwired) billing
    provider linkage. Stripe columns exist but nothing writes them yet."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        TRIALING = "trialing", "Trialing"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"

    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )

    # Per-customer overrides for negotiated deals. null = fall back to the plan.
    max_locations_override = models.PositiveIntegerField(null=True, blank=True)
    max_items_override = models.PositiveIntegerField(null=True, blank=True)
    max_members_override = models.PositiveIntegerField(null=True, blank=True)
    # Negotiated monthly price for this specific customer. This is our recorded
    # figure only — once Stripe is wired, Stripe remains the source of truth for
    # what is actually charged (see stripe_subscription_id). null = use the plan.
    monthly_price_cents_override = models.PositiveIntegerField(null=True, blank=True)

    stripe_customer_id = models.CharField(max_length=100, blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.organization} - {self.plan} ({self.status})"
```

- [ ] **Step 4: Generate the schema migration**

Run: `./scripts/manage.sh makemigrations organizations`
Expected: creates `apps/organizations/migrations/0001_initial.py` with all five models.

- [ ] **Step 5: Write the seed-plans data migration**

`apps/organizations/migrations/0002_seed_plans.py`:

```python
from django.db import migrations

PLANS = [
    {
        "tier": "free",
        "name": "Free",
        "max_locations": 2,
        "max_items": 25,
        "max_members": 3,
        "monthly_price_cents": 0,
    },
    {
        "tier": "pro",
        "name": "Pro",
        "max_locations": 25,
        "max_items": 1000,
        "max_members": 25,
        "monthly_price_cents": 2900,
    },
    {
        "tier": "enterprise",
        "name": "Enterprise",
        "max_locations": None,
        "max_items": None,
        "max_members": None,
        "monthly_price_cents": 0,
    },
]


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("organizations", "Plan")
    for data in PLANS:
        Plan.objects.update_or_create(tier=data["tier"], defaults=data)


def unseed_plans(apps, schema_editor):
    Plan = apps.get_model("organizations", "Plan")
    Plan.objects.filter(tier__in=[p["tier"] for p in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [("organizations", "0001_initial")]
    operations = [migrations.RunPython(seed_plans, unseed_plans)]
```

- [ ] **Step 6: Write the factory**

`apps/organizations/tests/factories.py`:

```python
"""Test factories for the organizations app."""

import factory

from apps.organizations.models import Organization
from apps.users.tests.factories import UserFactory


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Org {n}")
    owner = factory.SubFactory(UserFactory)
    created_by = factory.SelfAttribute("owner")
```

- [ ] **Step 7: Write the failing tests**

`apps/organizations/tests/test_models.py`:

```python
import pytest

from apps.organizations.models import Organization, Plan
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_plans_are_seeded():
    tiers = set(Plan.objects.values_list("tier", flat=True))
    assert {"free", "pro", "enterprise"} <= tiers


@pytest.mark.django_db
def test_free_plan_has_member_limit():
    free = Plan.objects.get(tier=Plan.Tier.FREE)
    assert free.max_members == 3


@pytest.mark.django_db
def test_organization_str_and_owner():
    org = OrganizationFactory(name="Acme")
    assert str(org) == "Acme"
    assert org.owner_id is not None
    assert isinstance(org, Organization)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `./scripts/test.sh apps/organizations/tests/test_models.py -v --no-cov`
Expected: 3 passed. (The test DB applies both migrations, so plans are seeded.)

- [ ] **Step 9: Lint checkpoint**

Run: `uv run ruff check apps/organizations && uv run ruff format apps/organizations`
Then stop for review. (Commit at your discretion — see Global Constraints.)

---

### Task 2: Org-creation lifecycle signal

**Files:**
- Create: `apps/organizations/signals.py`
- Modify: `apps/organizations/apps.py` (add `ready()` importing signals)
- Create: `apps/organizations/tests/test_signals.py`

**Interfaces:**
- Consumes: `Organization`, `Membership`, `Plan`, `Subscription` from Task 1.
- Produces: on `Organization` create, an admin `Membership` for `owner` and a `Subscription` on the free `Plan` with status `ACTIVE`. After this task, `OrganizationFactory()` yields an org that already has both.

- [ ] **Step 1: Write the failing test**

`apps/organizations/tests/test_signals.py`:

```python
import pytest

from apps.organizations.models import Membership, Plan, Subscription
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
def test_owner_becomes_admin_member_on_create():
    org = OrganizationFactory()
    membership = Membership.objects.get(organization=org, user=org.owner)
    assert membership.role == Membership.Role.ADMIN


@pytest.mark.django_db
def test_free_subscription_created_on_create():
    org = OrganizationFactory()
    sub = Subscription.objects.get(organization=org)
    assert sub.plan.tier == Plan.Tier.FREE
    assert sub.status == Subscription.Status.ACTIVE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./scripts/test.sh apps/organizations/tests/test_signals.py -v --no-cov`
Expected: FAIL — `Membership.DoesNotExist` / `Subscription.DoesNotExist` (no signal yet).

- [ ] **Step 3: Write the signal**

`apps/organizations/signals.py`:

```python
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
```

- [ ] **Step 4: Wire the signal into the app config**

Replace `apps/organizations/apps.py` with:

```python
from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organizations"

    def ready(self):
        from . import signals  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./scripts/test.sh apps/organizations/tests/test_signals.py -v --no-cov`
Expected: 2 passed.

- [ ] **Step 6: Lint checkpoint**

Run: `uv run ruff check apps/organizations && uv run ruff format apps/organizations`
Then stop for review.

---

### Task 3: Entitlement helpers (`limit_for`, `effective_monthly_price_cents`, `usage`, `can_add`)

**Files:**
- Modify: `apps/organizations/models.py` (add methods to `Subscription` and `Organization`)
- Create: `apps/organizations/tests/test_entitlements.py`

**Interfaces:**
- Consumes: signal from Task 2 (orgs auto-get a free subscription).
- Produces: `Subscription.limit_for(resource) -> int | None`; `Subscription.effective_monthly_price_cents -> int` (property); `Organization.usage(resource) -> int`; `Organization.can_add(resource, n=1) -> bool`. `resource` is one of `"locations" | "items" | "members"`.

- [ ] **Step 1: Write the failing tests**

`apps/organizations/tests/test_entitlements.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./scripts/test.sh apps/organizations/tests/test_entitlements.py -v --no-cov`
Expected: FAIL — `AttributeError: 'Subscription' object has no attribute 'limit_for'`.

- [ ] **Step 3: Add `limit_for` and `effective_monthly_price_cents` to `Subscription`**

In `apps/organizations/models.py`, add these to the `Subscription` class (above `__str__`):

```python
    def limit_for(self, resource):
        """Effective limit for 'locations' | 'items' | 'members'. None =
        unlimited. A per-subscription override wins over the plan's value."""
        override = getattr(self, f"max_{resource}_override")
        if override is not None:
            return override
        return getattr(self.plan, f"max_{resource}")

    @property
    def effective_monthly_price_cents(self):
        """Our recorded monthly price: the negotiated override if set, else the
        plan's list price. Display/record only — Stripe is the source of truth
        for actual charges once billing is wired."""
        if self.monthly_price_cents_override is not None:
            return self.monthly_price_cents_override
        return self.plan.monthly_price_cents
```

- [ ] **Step 4: Add `usage` and `can_add` to `Organization`**

In `apps/organizations/models.py`, add these to the `Organization` class (below `__str__`). Note `usage` computes only the requested resource, so `locations`/`items` stay dormant until the inventory app defines those reverse relations:

```python
    def usage(self, resource):
        """Current count for 'locations' | 'items' | 'members'."""
        if resource == "members":
            return self.memberships.count()
        if resource == "locations":
            return self.units.count()
        if resource == "items":
            return self.items.count()
        raise ValueError(f"Unknown resource: {resource!r}")

    def can_add(self, resource, n=1):
        """Whether the org may add `n` more of a resource under its plan.
        False when billing has lapsed, so an expired org keeps its data but
        can't grow until billing is resolved."""
        try:
            sub = self.subscription
        except Subscription.DoesNotExist:
            return False
        active = {Subscription.Status.ACTIVE, Subscription.Status.TRIALING}
        if sub.status not in active:
            return False
        limit = sub.limit_for(resource)
        return limit is None or self.usage(resource) + n <= limit
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./scripts/test.sh apps/organizations/tests/test_entitlements.py -v --no-cov`
Expected: 6 passed.

- [ ] **Step 6: Lint checkpoint**

Run: `uv run ruff check apps/organizations && uv run ruff format apps/organizations`
Then stop for review.

---

### Task 4: `transfer_ownership`

**Files:**
- Modify: `apps/organizations/models.py` (add `transfer_ownership` to `Organization`, add imports)
- Create: `apps/organizations/tests/test_transfer_ownership.py`

**Interfaces:**
- Produces: `Organization.transfer_ownership(new_owner)` — promotes `new_owner`'s membership to admin and reassigns `owner`. Raises `django.core.exceptions.ValidationError` if `new_owner` isn't a member, or (on a free plan) already owns another free org.

- [ ] **Step 1: Write the failing tests**

`apps/organizations/tests/test_transfer_ownership.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.organizations.models import Membership, Plan
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_transfer_requires_membership():
    org = OrganizationFactory()
    outsider = UserFactory()
    with pytest.raises(ValidationError):
        org.transfer_ownership(outsider)


@pytest.mark.django_db
def test_transfer_promotes_member_to_admin_owner():
    org = OrganizationFactory()
    new_owner = UserFactory()
    Membership.objects.create(
        organization=org, user=new_owner, role=Membership.Role.MEMBER
    )
    org.transfer_ownership(new_owner)
    org.refresh_from_db()
    assert org.owner == new_owner
    membership = Membership.objects.get(organization=org, user=new_owner)
    assert membership.role == Membership.Role.ADMIN


@pytest.mark.django_db
def test_transfer_free_org_blocked_when_recipient_owns_free_org():
    org = OrganizationFactory()
    recipient = UserFactory()
    Membership.objects.create(organization=org, user=recipient)
    OrganizationFactory(owner=recipient)  # recipient already owns a free org
    with pytest.raises(ValidationError):
        org.transfer_ownership(recipient)


@pytest.mark.django_db
def test_transfer_paid_org_ignores_free_org_rule():
    org = OrganizationFactory()
    pro = Plan.objects.get(tier=Plan.Tier.PRO)
    org.subscription.plan = pro
    org.subscription.save(update_fields=["plan"])
    recipient = UserFactory()
    Membership.objects.create(organization=org, user=recipient)
    OrganizationFactory(owner=recipient)  # recipient owns a free org — allowed
    org.transfer_ownership(recipient)
    org.refresh_from_db()
    assert org.owner == recipient
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./scripts/test.sh apps/organizations/tests/test_transfer_ownership.py -v --no-cov`
Expected: FAIL — `AttributeError: 'Organization' object has no attribute 'transfer_ownership'`.

- [ ] **Step 3: Update imports and add the method**

In `apps/organizations/models.py`, update the top imports to include `ValidationError` and `transaction`:

```python
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from apps.common.models import BaseModel
```

Add this method to the `Organization` class (below `can_add`):

```python
    def transfer_ownership(self, new_owner):
        """Hand the org to an existing member, promoting them to admin. Raises
        ValidationError if the recipient isn't a member, or (on a free plan)
        already owns another free organization."""
        with transaction.atomic():
            membership = (
                self.memberships.select_for_update().filter(user=new_owner).first()
            )
            if membership is None:
                raise ValidationError(
                    "New owner must already be a member of the organization."
                )
            if self.subscription.plan.tier == Plan.Tier.FREE and (
                Organization.objects.filter(
                    owner=new_owner, subscription__plan__tier=Plan.Tier.FREE
                )
                .exclude(pk=self.pk)
                .exists()
            ):
                raise ValidationError("Recipient already owns a free organization.")

            if membership.role != Membership.Role.ADMIN:
                membership.role = Membership.Role.ADMIN
                membership.save(update_fields=["role"])
            self.owner = new_owner
            self.save(update_fields=["owner"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./scripts/test.sh apps/organizations/tests/test_transfer_ownership.py -v --no-cov`
Expected: 4 passed.

- [ ] **Step 5: Lint checkpoint**

Run: `uv run ruff check apps/organizations && uv run ruff format apps/organizations`
Then stop for review.

---

### Task 5: Permissions + organization endpoints (list/create/retrieve/update)

**Files:**
- Create: `apps/organizations/permissions.py`
- Create: `apps/organizations/serializers.py`
- Create: `apps/organizations/views.py`
- Create: `apps/organizations/urls.py`
- Modify: `config/urls.py` (mount `apps.organizations.urls` under `api/`)
- Create: `apps/organizations/tests/test_organizations_api.py`

**Interfaces:**
- Produces permission classes: `IsOrgMember`, `IsOrgAdmin`, `IsOrgOwner` (all read the org id from `view.kwargs["org_id"]` or `view.kwargs["pk"]`).
- Produces serializers: `OrganizationSerializer`, `MemberUserSerializer`, `MembershipSerializer`, `MembershipRoleSerializer`, `InviteSerializer`, `InviteCreateSerializer`.
- Produces endpoints: `GET/POST /api/organizations/`, `GET/PATCH /api/organizations/{pk}/`.

- [ ] **Step 1: Write the permission classes**

`apps/organizations/permissions.py`:

```python
"""Org-scoped DRF permission classes. Org id comes from the URL kwargs."""

from rest_framework import permissions

from .models import Membership, Organization


def _org_id(view):
    return view.kwargs.get("org_id") or view.kwargs.get("pk")


class IsOrgMember(permissions.BasePermission):
    """Caller belongs to the org (any role)."""

    def has_permission(self, request, view):
        return Membership.objects.filter(
            organization_id=_org_id(view), user=request.user
        ).exists()


class IsOrgAdmin(permissions.BasePermission):
    """Caller is an admin of the org."""

    def has_permission(self, request, view):
        return Membership.objects.filter(
            organization_id=_org_id(view),
            user=request.user,
            role=Membership.Role.ADMIN,
        ).exists()


class IsOrgOwner(permissions.BasePermission):
    """Caller is the org's owner."""

    def has_permission(self, request, view):
        return Organization.objects.filter(
            pk=_org_id(view), owner=request.user
        ).exists()
```

- [ ] **Step 2: Write the serializers**

`apps/organizations/serializers.py`:

```python
"""Serializers for the organizations app."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Invite, Membership, Organization, Plan

User = get_user_model()


class MemberUserSerializer(serializers.ModelSerializer):
    """Compact read-only user representation for member/invite payloads."""

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name"]


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "description", "owner", "created_at", "updated_at"]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def validate(self, attrs):
        # One free org per owner, enforced on create only. New orgs are always
        # free at creation, so this fully enforces the rule.
        if self.instance is None:
            user = self.context["request"].user
            if Organization.objects.filter(
                owner=user, subscription__plan__tier=Plan.Tier.FREE
            ).exists():
                raise serializers.ValidationError(
                    "You already own a free organization."
                )
        return attrs


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "created_at"]
        read_only_fields = ["id", "user", "created_at"]


class MembershipRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ["role"]


class InviteSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Invite
        fields = [
            "id",
            "organization",
            "user",
            "role",
            "status",
            "invited_by",
            "created_at",
        ]
        read_only_fields = fields


class InviteCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=Membership.Role.choices, default=Membership.Role.MEMBER
    )
```

- [ ] **Step 3: Write the organization views**

`apps/organizations/views.py`:

```python
"""API views for the organizations app."""

from rest_framework import generics, permissions

from .models import Organization
from .permissions import IsOrgAdmin, IsOrgMember
from .serializers import OrganizationSerializer


class OrganizationListCreateView(generics.ListCreateAPIView):
    """List orgs the caller belongs to; create a new org (caller becomes
    owner). The post_save signal attaches the admin membership + free sub."""

    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Organization.objects.filter(
            memberships__user=self.request.user
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, created_by=self.request.user)


class OrganizationDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve (any member) or update name/description (admins only)."""

    serializer_class = OrganizationSerializer
    queryset = Organization.objects.all()

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated(), IsOrgMember()]
        return [permissions.IsAuthenticated(), IsOrgAdmin()]
```

- [ ] **Step 4: Write the URLconf**

`apps/organizations/urls.py`:

```python
"""Organization routes (mounted under /api/)."""

from django.urls import path

from .views import OrganizationDetailView, OrganizationListCreateView

app_name = "organizations"

urlpatterns = [
    path("organizations/", OrganizationListCreateView.as_view(), name="list-create"),
    path(
        "organizations/<uuid:pk>/",
        OrganizationDetailView.as_view(),
        name="detail",
    ),
]
```

- [ ] **Step 5: Mount the URLconf**

In `config/urls.py`, add to `urlpatterns` after the `api/users/` line:

```python
    path("api/", include("apps.organizations.urls")),
```

- [ ] **Step 6: Write the failing tests**

`apps/organizations/tests/test_organizations_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization, Subscription
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory

LIST_URL = "/api/organizations/"


def detail_url(org):
    return f"/api/organizations/{org.id}/"


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_create_org_makes_owner_admin_with_free_subscription(client_for):
    user = UserFactory()
    resp = client_for(user).post(LIST_URL, {"name": "Acme"})
    assert resp.status_code == 201
    org = Organization.objects.get(id=resp.data["id"])
    assert org.owner == user
    assert Membership.objects.get(organization=org, user=user).role == "admin"
    assert Subscription.objects.get(organization=org).plan.tier == "free"


@pytest.mark.django_db
def test_create_second_free_org_rejected(client_for):
    user = UserFactory()
    OrganizationFactory(owner=user)
    resp = client_for(user).post(LIST_URL, {"name": "Second"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_list_only_returns_my_orgs(client_for):
    user = UserFactory()
    mine = OrganizationFactory(owner=user)
    OrganizationFactory()  # someone else's
    resp = client_for(user).get(LIST_URL)
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.data["results"]]
    assert str(mine.id) in ids
    assert len(ids) == 1


@pytest.mark.django_db
def test_non_member_cannot_retrieve(client_for):
    org = OrganizationFactory()
    resp = client_for(UserFactory()).get(detail_url(org))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_member_can_retrieve_admin_can_update(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)

    assert client_for(member).get(detail_url(org)).status_code == 200
    # member (non-admin) cannot patch
    assert client_for(member).patch(
        detail_url(org), {"name": "New"}
    ).status_code == 403
    # owner (admin) can patch
    resp = client_for(owner).patch(detail_url(org), {"name": "New"})
    assert resp.status_code == 200
    assert resp.data["name"] == "New"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `./scripts/test.sh apps/organizations/tests/test_organizations_api.py -v --no-cov`
Expected: 5 passed.

- [ ] **Step 8: Lint checkpoint**

Run: `uv run ruff check apps/organizations && uv run ruff format apps/organizations`
Then stop for review.

---

### Task 6: Transfer-ownership endpoint

**Files:**
- Modify: `apps/organizations/views.py` (add `OrganizationTransferOwnershipView`)
- Modify: `apps/organizations/urls.py` (add route)
- Create: `apps/organizations/tests/test_transfer_api.py`

**Interfaces:**
- Consumes: `Organization.transfer_ownership` (Task 4), `IsOrgOwner` (Task 5).
- Produces: `POST /api/organizations/{pk}/transfer-ownership/` with body `{"new_owner": "<user-uuid>"}`. Owner-only. Returns the updated org.

- [ ] **Step 1: Write the failing tests**

`apps/organizations/tests/test_transfer_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


def url(org):
    return f"/api/organizations/{org.id}/transfer-ownership/"


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_owner_transfers_to_member(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)

    resp = client_for(owner).post(url(org), {"new_owner": str(member.id)})
    assert resp.status_code == 200
    org.refresh_from_db()
    assert org.owner == member


@pytest.mark.django_db
def test_non_owner_cannot_transfer(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    admin = UserFactory()
    Membership.objects.create(
        organization=org, user=admin, role=Membership.Role.ADMIN
    )
    resp = client_for(admin).post(url(org), {"new_owner": str(admin.id)})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_transfer_to_non_member_returns_400(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    outsider = UserFactory()
    resp = client_for(owner).post(url(org), {"new_owner": str(outsider.id)})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./scripts/test.sh apps/organizations/tests/test_transfer_api.py -v --no-cov`
Expected: FAIL — 404 (route doesn't exist yet).

- [ ] **Step 3: Add the view**

In `apps/organizations/views.py`, replace the top import block with the following (adds `User`, `get_object_or_404`, both `ValidationError` aliases, `Response`, `APIView`, and `IsOrgOwner`):

```python
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Organization
from .permissions import IsOrgAdmin, IsOrgMember, IsOrgOwner
from .serializers import OrganizationSerializer

User = get_user_model()
```

Append at the end of the file:

```python
class OrganizationTransferOwnershipView(APIView):
    """Owner-only: hand the org to an existing member."""

    permission_classes = [permissions.IsAuthenticated, IsOrgOwner]

    def post(self, request, pk):
        organization = get_object_or_404(Organization, pk=pk)
        new_owner = get_object_or_404(User, pk=request.data.get("new_owner"))
        try:
            organization.transfer_ownership(new_owner)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages) from exc
        return Response(
            OrganizationSerializer(organization, context={"request": request}).data
        )
```

- [ ] **Step 4: Add the route**

In `apps/organizations/urls.py`, update the import and add the route:

```python
from .views import (
    OrganizationDetailView,
    OrganizationListCreateView,
    OrganizationTransferOwnershipView,
)
```

Add to `urlpatterns`:

```python
    path(
        "organizations/<uuid:pk>/transfer-ownership/",
        OrganizationTransferOwnershipView.as_view(),
        name="transfer-ownership",
    ),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./scripts/test.sh apps/organizations/tests/test_transfer_api.py -v --no-cov`
Expected: 3 passed.

- [ ] **Step 6: Lint checkpoint**

Run: `uv run ruff check apps/organizations && uv run ruff format apps/organizations`
Then stop for review.

---

### Task 7: Member endpoints (list / change role / remove)

**Files:**
- Modify: `apps/organizations/views.py` (add `MemberListView`, `MemberDetailView`)
- Modify: `apps/organizations/urls.py` (add routes)
- Create: `apps/organizations/tests/test_members_api.py`

**Interfaces:**
- Produces: `GET /api/organizations/{org_id}/members/` (member); `PATCH` and `DELETE /api/organizations/{org_id}/members/{user_id}/` (admin). The owner's membership can't be demoted or removed.

- [ ] **Step 1: Write the failing tests**

`apps/organizations/tests/test_members_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


def list_url(org):
    return f"/api/organizations/{org.id}/members/"


def detail_url(org, user):
    return f"/api/organizations/{org.id}/members/{user.id}/"


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_member_can_list_members(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(member).get(list_url(org))
    assert resp.status_code == 200
    assert resp.data["count"] == 2


@pytest.mark.django_db
def test_admin_can_change_member_role(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(owner).patch(detail_url(org, member), {"role": "admin"})
    assert resp.status_code == 200
    assert Membership.objects.get(organization=org, user=member).role == "admin"


@pytest.mark.django_db
def test_non_admin_cannot_change_role(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(member).patch(detail_url(org, member), {"role": "admin"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_admin_can_remove_member(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(owner).delete(detail_url(org, member))
    assert resp.status_code == 204
    assert not Membership.objects.filter(organization=org, user=member).exists()


@pytest.mark.django_db
def test_owner_cannot_be_removed_or_demoted(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    assert client_for(owner).delete(detail_url(org, owner)).status_code == 400
    assert client_for(owner).patch(
        detail_url(org, owner), {"role": "member"}
    ).status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./scripts/test.sh apps/organizations/tests/test_members_api.py -v --no-cov`
Expected: FAIL — 404 (routes don't exist yet).

- [ ] **Step 3: Add the views**

In `apps/organizations/views.py`:

Change the `rest_framework` import to add `status`:

```python
from rest_framework import generics, permissions, status
```

Change the `.models` import line to:

```python
from .models import Membership, Organization
```

Change the `.serializers` import line to:

```python
from .serializers import (
    MembershipRoleSerializer,
    MembershipSerializer,
    OrganizationSerializer,
)
```

Append at the end of the file:

```python
class MemberListView(generics.ListAPIView):
    """List an org's members (any member)."""

    serializer_class = MembershipSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        return Membership.objects.filter(
            organization_id=self.kwargs["org_id"]
        ).select_related("user")


class MemberDetailView(APIView):
    """Change a member's role or remove them (admins only). The owner's
    membership is protected — reassign ownership first."""

    permission_classes = [permissions.IsAuthenticated, IsOrgAdmin]

    def _get(self, org_id, user_id):
        organization = get_object_or_404(Organization, pk=org_id)
        membership = get_object_or_404(
            Membership, organization=organization, user_id=user_id
        )
        return organization, membership

    def patch(self, request, org_id, user_id):
        organization, membership = self._get(org_id, user_id)
        if membership.user_id == organization.owner_id:
            raise DRFValidationError("The owner's role cannot be changed.")
        serializer = MembershipRoleSerializer(
            membership, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MembershipSerializer(membership).data)

    def delete(self, request, org_id, user_id):
        organization, membership = self._get(org_id, user_id)
        if membership.user_id == organization.owner_id:
            raise DRFValidationError("The owner cannot be removed.")
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Add the routes**

In `apps/organizations/urls.py`, update the imports:

```python
from .views import (
    MemberDetailView,
    MemberListView,
    OrganizationDetailView,
    OrganizationListCreateView,
    OrganizationTransferOwnershipView,
)
```

Add to `urlpatterns`:

```python
    path(
        "organizations/<uuid:org_id>/members/",
        MemberListView.as_view(),
        name="member-list",
    ),
    path(
        "organizations/<uuid:org_id>/members/<uuid:user_id>/",
        MemberDetailView.as_view(),
        name="member-detail",
    ),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./scripts/test.sh apps/organizations/tests/test_members_api.py -v --no-cov`
Expected: 5 passed.

- [ ] **Step 6: Lint checkpoint**

Run: `uv run ruff check apps/organizations && uv run ruff format apps/organizations`
Then stop for review.

---

### Task 8: Invite model methods + endpoints

**Files:**
- Modify: `apps/organizations/models.py` (add `accept`/`decline` to `Invite`)
- Modify: `apps/organizations/views.py` (add invite views)
- Modify: `apps/organizations/urls.py` (add routes)
- Create: `apps/organizations/tests/test_invites_api.py`

**Interfaces:**
- Produces: `Invite.accept() -> Membership`, `Invite.decline() -> None`.
- Produces endpoints: `POST /api/organizations/{org_id}/invites/` (admin, body `{"email", "role"}`), `GET /api/organizations/{org_id}/invites/` (admin), `GET /api/invites/` (my pending invites), `POST /api/invites/{pk}/accept/`, `POST /api/invites/{pk}/decline/`.

- [ ] **Step 1: Add `accept`/`decline` to the `Invite` model**

In `apps/organizations/models.py`, add these to the `Invite` class (below `__str__`). `transaction` is already imported (Task 4):

```python
    def accept(self):
        """Create (or reuse) the membership and mark the invite accepted."""
        with transaction.atomic():
            membership, _ = Membership.objects.get_or_create(
                organization=self.organization,
                user=self.user,
                defaults={"role": self.role},
            )
            self.status = self.Status.ACCEPTED
            self.save(update_fields=["status", "updated_at"])
        return membership

    def decline(self):
        self.status = self.Status.DECLINED
        self.save(update_fields=["status", "updated_at"])
```

- [ ] **Step 2: Write the failing tests**

`apps/organizations/tests/test_invites_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Invite, Membership
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory


def org_invites_url(org):
    return f"/api/organizations/{org.id}/invites/"


def accept_url(invite):
    return f"/api/invites/{invite.id}/accept/"


def decline_url(invite):
    return f"/api/invites/{invite.id}/decline/"


MY_INVITES_URL = "/api/invites/"


@pytest.fixture
def client_for():
    def _make(user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    return _make


@pytest.mark.django_db
def test_admin_invites_existing_user(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    invitee = UserFactory()
    resp = client_for(owner).post(
        org_invites_url(org), {"email": invitee.email, "role": "member"}
    )
    assert resp.status_code == 201
    assert Invite.objects.filter(
        organization=org, user=invitee, status="pending"
    ).exists()


@pytest.mark.django_db
def test_invite_unknown_email_rejected(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    resp = client_for(owner).post(
        org_invites_url(org), {"email": "nobody@example.com"}
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_duplicate_pending_invite_rejected(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    invitee = UserFactory()
    Invite.objects.create(organization=org, user=invitee)
    resp = client_for(owner).post(org_invites_url(org), {"email": invitee.email})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_inviting_existing_member_rejected(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(owner).post(org_invites_url(org), {"email": member.email})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_non_admin_cannot_invite(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    member = UserFactory()
    Membership.objects.create(organization=org, user=member)
    resp = client_for(member).post(
        org_invites_url(org), {"email": UserFactory().email}
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_invitee_sees_and_accepts_invite(client_for):
    owner = UserFactory()
    org = OrganizationFactory(owner=owner)
    invitee = UserFactory()
    invite = Invite.objects.create(
        organization=org, user=invitee, invited_by=owner
    )

    listing = client_for(invitee).get(MY_INVITES_URL)
    assert listing.data["count"] == 1

    resp = client_for(invitee).post(accept_url(invite))
    assert resp.status_code == 200
    invite.refresh_from_db()
    assert invite.status == "accepted"
    assert Membership.objects.filter(organization=org, user=invitee).exists()


@pytest.mark.django_db
def test_invitee_declines_invite(client_for):
    org = OrganizationFactory()
    invitee = UserFactory()
    invite = Invite.objects.create(organization=org, user=invitee)
    resp = client_for(invitee).post(decline_url(invite))
    assert resp.status_code == 200
    invite.refresh_from_db()
    assert invite.status == "declined"
    assert not Membership.objects.filter(organization=org, user=invitee).exists()


@pytest.mark.django_db
def test_other_user_cannot_accept_someone_elses_invite(client_for):
    org = OrganizationFactory()
    invitee = UserFactory()
    invite = Invite.objects.create(organization=org, user=invitee)
    resp = client_for(UserFactory()).post(accept_url(invite))
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./scripts/test.sh apps/organizations/tests/test_invites_api.py -v --no-cov`
Expected: FAIL — 404 (invite routes don't exist yet).

- [ ] **Step 4: Add the invite views**

In `apps/organizations/views.py`:

Change the `.models` import to include `Invite`:

```python
from .models import Invite, Membership, Organization
```

Change the `.serializers` import to include the invite serializers:

```python
from .serializers import (
    InviteCreateSerializer,
    InviteSerializer,
    MembershipRoleSerializer,
    MembershipSerializer,
    OrganizationSerializer,
)
```

Append at the end of the file:

```python
class OrgInviteListCreateView(generics.ListCreateAPIView):
    """List an org's invites or create a new one (admins only)."""

    permission_classes = [permissions.IsAuthenticated, IsOrgAdmin]

    def get_queryset(self):
        return Invite.objects.filter(
            organization_id=self.kwargs["org_id"]
        ).select_related("user")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InviteCreateSerializer
        return InviteSerializer

    def create(self, request, *args, **kwargs):
        organization = get_object_or_404(Organization, pk=self.kwargs["org_id"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

        try:
            invitee = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise DRFValidationError(
                {"email": "No account exists for this email."}
            ) from exc
        if Membership.objects.filter(
            organization=organization, user=invitee
        ).exists():
            raise DRFValidationError({"email": "This user is already a member."})
        if Invite.objects.filter(
            organization=organization, user=invitee, status=Invite.Status.PENDING
        ).exists():
            raise DRFValidationError(
                {"email": "A pending invite already exists for this user."}
            )

        invite = Invite.objects.create(
            organization=organization,
            user=invitee,
            role=role,
            invited_by=request.user,
        )
        return Response(
            InviteSerializer(invite).data, status=status.HTTP_201_CREATED
        )


class MyInviteListView(generics.ListAPIView):
    """The caller's own pending invites."""

    serializer_class = InviteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Invite.objects.filter(
            user=self.request.user, status=Invite.Status.PENDING
        ).select_related("organization", "user")


class InviteAcceptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        invite = get_object_or_404(Invite, pk=pk, user=request.user)
        if invite.status != Invite.Status.PENDING:
            raise DRFValidationError("This invite is no longer pending.")
        invite.accept()
        return Response(InviteSerializer(invite).data)


class InviteDeclineView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        invite = get_object_or_404(Invite, pk=pk, user=request.user)
        if invite.status != Invite.Status.PENDING:
            raise DRFValidationError("This invite is no longer pending.")
        invite.decline()
        return Response(InviteSerializer(invite).data)
```

- [ ] **Step 5: Add the routes**

In `apps/organizations/urls.py`, update the imports:

```python
from .views import (
    InviteAcceptView,
    InviteDeclineView,
    MemberDetailView,
    MemberListView,
    MyInviteListView,
    OrganizationDetailView,
    OrganizationListCreateView,
    OrganizationTransferOwnershipView,
    OrgInviteListCreateView,
)
```

Add to `urlpatterns`:

```python
    path(
        "organizations/<uuid:org_id>/invites/",
        OrgInviteListCreateView.as_view(),
        name="org-invite-list-create",
    ),
    path("invites/", MyInviteListView.as_view(), name="my-invite-list"),
    path(
        "invites/<uuid:pk>/accept/",
        InviteAcceptView.as_view(),
        name="invite-accept",
    ),
    path(
        "invites/<uuid:pk>/decline/",
        InviteDeclineView.as_view(),
        name="invite-decline",
    ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./scripts/test.sh apps/organizations/tests/test_invites_api.py -v --no-cov`
Expected: 8 passed.

- [ ] **Step 7: Lint checkpoint**

Run: `uv run ruff check apps/organizations && uv run ruff format apps/organizations`
Then stop for review.

---

### Task 9: Admin registrations + full-suite green

**Files:**
- Create: `apps/organizations/admin.py`
- (No new tests — this task verifies the whole app suite passes together.)

**Interfaces:**
- Consumes: all models. Produces: Unfold-themed admin registrations.

- [ ] **Step 1: Write the admin registrations**

`apps/organizations/admin.py`:

```python
"""Admin registrations for the organizations app (django-unfold themed)."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Invite, Membership, Organization, Plan, Subscription


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ["name", "owner", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Membership)
class MembershipAdmin(ModelAdmin):
    list_display = ["organization", "user", "role"]
    list_filter = ["role"]
    search_fields = ["organization__name", "user__email"]


@admin.register(Invite)
class InviteAdmin(ModelAdmin):
    list_display = ["organization", "user", "role", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["organization__name", "user__email"]


@admin.register(Plan)
class PlanAdmin(ModelAdmin):
    list_display = ["name", "tier", "max_members", "max_locations", "max_items"]


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ["organization", "plan", "status", "current_period_end"]
    list_filter = ["status"]
    search_fields = ["organization__name"]
```

- [ ] **Step 2: Run the full organizations suite (with coverage)**

Run: `./scripts/test.sh apps/organizations -v`
Expected: all tests pass (29 total across the app).

- [ ] **Step 3: Run the entire project test suite (regression check)**

Run: `./scripts/test.sh`
Expected: all tests pass — the new app hasn't broken users/auth.

- [ ] **Step 4: Lint the whole project**

Run: `uv run ruff check . && uv run ruff format .`
Then stop for review.

---

## Self-Review Notes

- **Spec coverage:** two-app split (this app = organizations + billing) ✓ Task 1; BaseModel/UUID alignment ✓ Task 1; drop `join_code` ✓ (absent from model); `Invite` keeps user FK + `invited_by`/`role`/conditional-unique ✓ Task 1/8; Plan seeded via data migration ✓ Task 1; Subscription Stripe columns present but unwired ✓ Task 1; negotiated-price override (`monthly_price_cents_override` + `effective_monthly_price_cents`) ✓ Task 1/3; owner→admin membership + free subscription signal ✓ Task 2; `usage`/`can_add` guard ✓ Task 3; one-free-org on create ✓ Task 5 and transfer ✓ Task 4; endpoints (org CRUD, transfer, members, invites) ✓ Tasks 5–8; members list readable by any member ✓ Task 7; owner not demotable/removable ✓ Task 7; permission scoping ✓ Task 5; testing coverage ✓ each task.
- **Out of scope confirmed absent:** no Stripe calls, no inventory models, no `UnitType`/`UnitOfMeasure` seeding, no email-invite-to-nonexistent-user, no `join_code`.
- **Type consistency:** `Membership.Role`, `Invite.Status`, `Plan.Tier`, `Subscription.Status` referenced consistently; `usage`/`can_add`/`limit_for`/`effective_monthly_price_cents`/`transfer_ownership`/`accept`/`decline` signatures stable across tasks; permission classes read `org_id`/`pk` consistently with the URL kwargs defined in Tasks 5–8.
