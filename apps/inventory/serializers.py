"""Serializers for the inventory app."""

from rest_framework import serializers

from .models import InventoryUnit, Item, UnitOfMeasure, UnitType


class UnitTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitType
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ["id", "name", "abbreviation", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = [
            "id",
            "name",
            "description",
            "sku",
            "default_unit_of_measure",
            "tracks_expiration",
            "tracks_serial",
            "expiration_warning_days",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_default_unit_of_measure(self, value):
        if value is not None and str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Unit of measure must belong to this organization.")
        return value

    def validate_parent(self, value):
        if value is not None and str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Parent item must belong to this organization.")
        return value


class InventoryUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryUnit
        fields = [
            "id",
            "name",
            "description",
            "unit_type",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_unit_type(self, value):
        if value is not None and str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Unit type must belong to this organization.")
        return value

    def validate_parent(self, value):
        if value is None:
            return value
        if str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Parent unit must belong to this organization.")
        # Cycle guard for reparenting: the intended parent may not be this unit
        # or one of its descendants.
        instance = self.instance
        if instance is not None:
            if value.id == instance.id:
                raise serializers.ValidationError("A unit cannot be its own parent.")
            ancestor = value
            while ancestor is not None:
                if ancestor.id == instance.id:
                    raise serializers.ValidationError(
                        "A unit cannot be nested under its own descendant."
                    )
                ancestor = ancestor.parent
        return value

    def validate(self, attrs):
        # The subdivisions cap is enforced here at the API layer only (unlike the
        # cycle guard above, which is also enforced in the model's clean()), so
        # direct ORM/admin writes can exceed it.
        # Enforce the per-location subdivisions cap when a parent is set (create)
        # or changed (reparent). "adding" is the size of the subtree moving in:
        # 1 for a brand-new unit, or the moved unit's whole subtree on reparent.
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        if parent is None:
            return attrs
        instance = self.instance
        # Moving within the same root doesn't change that root's count.
        if (
            instance is not None
            and instance.parent_id is not None
            and instance.root.id == parent.root.id
        ):
            return attrs
        adding = instance.subtree_size() if instance is not None else 1
        if not parent.can_add_subdivision(adding=adding):
            raise serializers.ValidationError(
                {"parent": "This location's subdivision limit has been reached."}
            )
        return attrs
