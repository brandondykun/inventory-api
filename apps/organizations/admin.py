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
