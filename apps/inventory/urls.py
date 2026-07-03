"""Inventory routes (mounted under /api/, nested per organization)."""

from django.urls import path

from .views import (
    InventoryUnitDetailView,
    InventoryUnitListCreateView,
    ItemDetailView,
    ItemListCreateView,
    ParTemplateDetailView,
    ParTemplateLineDetailView,
    ParTemplateLineListCreateView,
    ParTemplateListCreateView,
    UnitOfMeasureDetailView,
    UnitOfMeasureListCreateView,
    UnitTypeDetailView,
    UnitTypeListCreateView,
)

app_name = "inventory"

urlpatterns = [
    path(
        "organizations/<uuid:org_id>/unit-types/",
        UnitTypeListCreateView.as_view(),
        name="unit-type-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/unit-types/<uuid:pk>/",
        UnitTypeDetailView.as_view(),
        name="unit-type-detail",
    ),
    path(
        "organizations/<uuid:org_id>/units-of-measure/",
        UnitOfMeasureListCreateView.as_view(),
        name="uom-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/units-of-measure/<uuid:pk>/",
        UnitOfMeasureDetailView.as_view(),
        name="uom-detail",
    ),
    path(
        "organizations/<uuid:org_id>/items/",
        ItemListCreateView.as_view(),
        name="item-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/items/<uuid:pk>/",
        ItemDetailView.as_view(),
        name="item-detail",
    ),
    path(
        "organizations/<uuid:org_id>/units/",
        InventoryUnitListCreateView.as_view(),
        name="unit-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/units/<uuid:pk>/",
        InventoryUnitDetailView.as_view(),
        name="unit-detail",
    ),
    path(
        "organizations/<uuid:org_id>/par-templates/",
        ParTemplateListCreateView.as_view(),
        name="par-template-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/par-templates/<uuid:pk>/",
        ParTemplateDetailView.as_view(),
        name="par-template-detail",
    ),
    path(
        "organizations/<uuid:org_id>/par-templates/<uuid:template_id>/lines/",
        ParTemplateLineListCreateView.as_view(),
        name="par-line-list-create",
    ),
    path(
        "organizations/<uuid:org_id>/par-templates/<uuid:template_id>/lines/<uuid:pk>/",
        ParTemplateLineDetailView.as_view(),
        name="par-line-detail",
    ),
]
