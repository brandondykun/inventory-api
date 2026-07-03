"""API views for the inventory app. All endpoints are nested under an
organization and scoped to it; reads require org membership, writes require
org admin."""

from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from apps.organizations.permissions import IsOrgAdmin, IsOrgMember

from .exceptions import Conflict
from .models import InventoryUnit, Item, ParTemplate, ParTemplateItem, UnitOfMeasure, UnitType
from .serializers import (
    InventoryUnitSerializer,
    ItemSerializer,
    ParTemplateDetailSerializer,
    ParTemplateItemSerializer,
    ParTemplateSerializer,
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


class ProtectedDeleteMixin:
    """Turn a DB-level ProtectedError on delete into a clean 409 instead of a
    500. Used where a catalog row may be referenced by PROTECT foreign keys
    (e.g. par template lines)."""

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as exc:
            raise Conflict(
                "Cannot delete: this record is still referenced by other records "
                "(e.g. par template lines). Remove those references first."
            ) from exc


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


class UnitOfMeasureDetailView(
    ProtectedDeleteMixin, OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView
):
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


class ItemDetailView(ProtectedDeleteMixin, OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView):
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


class ParTemplateListCreateView(OrgScopedMixin, generics.ListCreateAPIView):
    serializer_class = ParTemplateSerializer

    def get_queryset(self):
        qs = ParTemplate.objects.filter(organization_id=self.get_org_id())
        is_active = self.request.query_params.get("is_active")
        if is_active is None:
            return qs.filter(is_active=True)
        if is_active.lower() == "all":
            return qs
        return qs.filter(is_active=is_active.lower() == "true")


class ParTemplateDetailView(OrgScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ParTemplateDetailSerializer

    def get_queryset(self):
        return ParTemplate.objects.filter(organization_id=self.get_org_id())


class _TemplateScopedMixin(OrgScopedMixin):
    """Line endpoints: scope to one template that must belong to the URL org."""

    serializer_class = ParTemplateItemSerializer

    def get_template(self):
        return get_object_or_404(
            ParTemplate,
            pk=self.kwargs["template_id"],
            organization_id=self.get_org_id(),
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["template_id"] = self.kwargs["template_id"]
        return ctx


class ParTemplateLineListCreateView(_TemplateScopedMixin, generics.ListCreateAPIView):
    def get_queryset(self):
        return ParTemplateItem.objects.filter(template=self.get_template())

    def perform_create(self, serializer):
        serializer.save(template=self.get_template())


class ParTemplateLineDetailView(_TemplateScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    def get_queryset(self):
        return ParTemplateItem.objects.filter(
            template_id=self.kwargs["template_id"],
            template__organization_id=self.get_org_id(),
        )
