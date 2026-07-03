"""Org-scoped DRF permission classes. Org id comes from the URL kwargs."""

from rest_framework import permissions

from .models import Membership, Organization


def _org_id(view):
    return view.kwargs.get("org_id") or view.kwargs.get("pk")


class IsOrgMember(permissions.BasePermission):
    """Caller belongs to the org (any role)."""

    def has_permission(self, request, view):
        return Membership.objects.filter(organization_id=_org_id(view), user=request.user).exists()


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
        return Organization.objects.filter(pk=_org_id(view), owner=request.user).exists()
