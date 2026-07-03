"""Serializers for the inventory app."""

from rest_framework import serializers

from .models import InventoryUnit, Item, ParTemplate, ParTemplateItem, UnitOfMeasure, UnitType


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
            "par_template",
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

    def validate_par_template(self, value):
        if value is None:
            return value
        if str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Par template must belong to this organization.")
        if not value.is_active:
            raise serializers.ValidationError("Cannot assign an inactive par template.")
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


class ParTemplateItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParTemplateItem
        fields = [
            "id",
            "item",
            "par_quantity",
            "min_quantity",
            "unit_of_measure",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_item(self, value):
        if str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Item must belong to this organization.")
        return value

    def validate_unit_of_measure(self, value):
        if str(value.organization_id) != str(self.context["org_id"]):
            raise serializers.ValidationError("Unit of measure must belong to this organization.")
        return value

    def validate(self, attrs):
        par = attrs.get("par_quantity", getattr(self.instance, "par_quantity", None))
        min_q = attrs.get("min_quantity", getattr(self.instance, "min_quantity", None))
        if par is not None and par < 0:
            raise serializers.ValidationError({"par_quantity": "Must be zero or greater."})
        if min_q is not None and min_q < 0:
            raise serializers.ValidationError({"min_quantity": "Must be zero or greater."})
        if par is not None and min_q is not None and min_q > par:
            raise serializers.ValidationError({"min_quantity": "Cannot exceed par_quantity."})
        # Duplicate (template, item) — template comes from the URL, not the body.
        item = attrs.get("item", getattr(self.instance, "item", None))
        template_id = self.context.get("template_id")
        if item is not None and template_id is not None:
            qs = ParTemplateItem.objects.filter(template_id=template_id, item=item)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"item": "This item is already on the template."})
        return attrs


class ParTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParTemplate
        fields = ["id", "name", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ParTemplateDetailSerializer(ParTemplateSerializer):
    lines = ParTemplateItemSerializer(many=True, read_only=True)

    class Meta(ParTemplateSerializer.Meta):
        fields = ParTemplateSerializer.Meta.fields + ["lines"]
