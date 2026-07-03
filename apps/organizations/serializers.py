"""Serializers for the organizations app."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Invite, Membership, Organization, Plan

User = get_user_model()


class MemberUserSerializer(serializers.ModelSerializer):
    """Compact read-only user representation for member/invite payloads."""

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name"]


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "description", "owner", "created_at", "updated_at"]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def validate(self, attrs):
        # One free org per owner, enforced on create only. New orgs are always
        # free at creation, so this fully enforces the rule.
        if self.instance is None:
            user = self.context["request"].user
            if Organization.objects.filter(
                owner=user, subscription__plan__tier=Plan.Tier.FREE
            ).exists():
                raise serializers.ValidationError("You already own a free organization.")
        return attrs


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "created_at"]
        read_only_fields = ["id", "user", "created_at"]


class MembershipRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ["role"]


class InviteSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Invite
        fields = [
            "id",
            "organization",
            "user",
            "role",
            "status",
            "invited_by",
            "created_at",
        ]
        read_only_fields = fields


class InviteCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Membership.Role.choices, default=Membership.Role.MEMBER)


class TransferOwnershipSerializer(serializers.Serializer):
    new_owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
