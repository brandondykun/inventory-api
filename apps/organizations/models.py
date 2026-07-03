"""Organization, membership, invitation, and billing models."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
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

    def transfer_ownership(self, new_owner):
        """Hand the org to an existing member, promoting them to admin. Raises
        ValidationError if the recipient isn't a member, or (on a free plan)
        already owns another free organization."""
        with transaction.atomic():
            membership = self.memberships.select_for_update().filter(user=new_owner).first()
            if membership is None:
                raise ValidationError("New owner must already be a member of the organization.")
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
                membership.save(update_fields=["role", "updated_at"])
            self.owner = new_owner
            self.save(update_fields=["owner", "updated_at"])


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
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} in {self.organization} ({self.role})"


class Invite(BaseModel):
    """An invitation for an existing account to join an organization."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invites")
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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

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
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite: {self.user} -> {self.organization} ({self.status})"

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
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

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

    def __str__(self):
        return f"{self.organization} - {self.plan} ({self.status})"
