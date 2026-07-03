"""Inventory routes (mounted under /api/, nested per organization)."""

from django.urls import path

from .views import (
    InventoryUnitDetailView,
    InventoryUnitListCreateView,
    ItemDetailView,
    ItemListCreateView,
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
]
