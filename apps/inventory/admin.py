"""Django admin registrations for the inventory app."""

from django.contrib import admin

from .models import (
    InventoryUnit,
    Item,
    ParTemplate,
    ParTemplateItem,
    UnitOfMeasure,
    UnitType,
)


@admin.register(UnitType)
class UnitTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "organization"]
    list_filter = ["organization"]
    search_fields = ["name"]


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ["name", "abbreviation", "organization"]
    list_filter = ["organization"]
    search_fields = ["name", "abbreviation"]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "sku", "tracks_expiration"]
    list_filter = ["organization", "tracks_expiration", "tracks_serial"]
    search_fields = ["name", "sku"]
    raw_id_fields = ["default_unit_of_measure", "parent"]


@admin.register(InventoryUnit)
class InventoryUnitAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "unit_type", "parent"]
    list_filter = ["organization", "unit_type"]
    search_fields = ["name"]
    raw_id_fields = ["parent"]


class ParTemplateItemInline(admin.TabularInline):
    model = ParTemplateItem
    extra = 0
    raw_id_fields = ["item", "unit_of_measure"]


@admin.register(ParTemplate)
class ParTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "is_active"]
    list_filter = ["organization", "is_active"]
    search_fields = ["name"]
    inlines = [ParTemplateItemInline]
