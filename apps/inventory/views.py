"""API views for the inventory app. All endpoints are nested under an
organization and scoped to it; reads require org membership, writes require
org admin."""

from rest_framework import generics, permissions

from apps.organizations.permissions import IsOrgAdmin, IsOrgMember

from .models import InventoryUnit, Item, UnitOfMeasure, UnitType
from .serializers import (
    InventoryUnitSerializer,
    ItemSerializer,
    UnitOfMeasureSerializer,
    UnitTypeSerializer,
)


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
