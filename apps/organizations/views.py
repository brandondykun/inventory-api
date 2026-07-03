"""API views for the organizations app."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invite, Membership, Organization, Plan
from .permissions import IsOrgAdmin, IsOrgMember, IsOrgOwner
from .serializers import (
    InviteCreateSerializer,
    InviteSerializer,
    MembershipRoleSerializer,
    MembershipSerializer,
    OrganizationSerializer,
    TransferOwnershipSerializer,
)

User = get_user_model()


class OrganizationListCreateView(generics.ListCreateAPIView):
    """List orgs the caller belongs to; create a new org (caller becomes
    owner). The post_save signal attaches the admin membership + free sub."""

    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Organization.objects.filter(memberships__user=self.request.user).distinct()

    def perform_create(self, serializer):
        with transaction.atomic():
            # Lock this user's row so concurrent org creations serialize,
            # closing the one-free-org race the serializer check can't (the
            # invariant spans Organization->Subscription->Plan, so no single DB
            # constraint enforces it).
            User.objects.select_for_update().get(pk=self.request.user.pk)
            if Organization.objects.filter(
                owner=self.request.user, subscription__plan__tier=Plan.Tier.FREE
            ).exists():
                raise DRFValidationError("You already own a free organization.")
            serializer.save(owner=self.request.user, created_by=self.request.user)


class OrganizationDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve (any member) or update name/description (admins only)."""

    serializer_class = OrganizationSerializer
    queryset = Organization.objects.all()

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated(), IsOrgMember()]
        return [permissions.IsAuthenticated(), IsOrgAdmin()]


class OrganizationTransferOwnershipView(APIView):
    """Owner-only: hand the org to an existing member."""

    permission_classes = [permissions.IsAuthenticated, IsOrgOwner]

    def post(self, request, pk):
        organization = get_object_or_404(Organization, pk=pk)
        serializer = TransferOwnershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_owner = serializer.validated_data["new_owner"]
        try:
            organization.transfer_ownership(new_owner)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages) from exc
        return Response(OrganizationSerializer(organization, context={"request": request}).data)


class MemberListView(generics.ListAPIView):
    """List an org's members (any member)."""

    serializer_class = MembershipSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get_queryset(self):
        return Membership.objects.filter(organization_id=self.kwargs["org_id"]).select_related(
            "user"
        )


class MemberDetailView(APIView):
    """Change a member's role or remove them (admins only). The owner's
    membership is protected — reassign ownership first."""

    permission_classes = [permissions.IsAuthenticated, IsOrgAdmin]

    def _get(self, org_id, user_id):
        organization = get_object_or_404(Organization, pk=org_id)
        membership = get_object_or_404(Membership, organization=organization, user_id=user_id)
        return organization, membership

    def patch(self, request, org_id, user_id):
        organization, membership = self._get(org_id, user_id)
        if membership.user_id == organization.owner_id:
            raise DRFValidationError("The owner's role cannot be changed.")
        serializer = MembershipRoleSerializer(membership, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MembershipSerializer(membership).data)

    def delete(self, request, org_id, user_id):
        organization, membership = self._get(org_id, user_id)
        if membership.user_id == organization.owner_id:
            raise DRFValidationError("The owner cannot be removed.")
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrgInviteListCreateView(generics.ListCreateAPIView):
    """List an org's invites or create a new one (admins only)."""

    permission_classes = [permissions.IsAuthenticated, IsOrgAdmin]

    def get_queryset(self):
        return Invite.objects.filter(organization_id=self.kwargs["org_id"]).select_related("user")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InviteCreateSerializer
        return InviteSerializer

    def create(self, request, *args, **kwargs):
        organization = get_object_or_404(Organization, pk=self.kwargs["org_id"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

        invitee = User.objects.filter(email__iexact=email).first()
        if invitee is None:
            raise DRFValidationError({"email": "No account exists for this email."})
        if Membership.objects.filter(organization=organization, user=invitee).exists():
            raise DRFValidationError({"email": "This user is already a member."})
        if Invite.objects.filter(
            organization=organization, user=invitee, status=Invite.Status.PENDING
        ).exists():
            raise DRFValidationError({"email": "A pending invite already exists for this user."})

        try:
            invite = Invite.objects.create(
                organization=organization,
                user=invitee,
                role=role,
                invited_by=request.user,
            )
        except IntegrityError as exc:
            raise DRFValidationError(
                {"email": "A pending invite already exists for this user."}
            ) from exc
        return Response(InviteSerializer(invite).data, status=status.HTTP_201_CREATED)


class MyInviteListView(generics.ListAPIView):
    """The caller's own pending invites."""

    serializer_class = InviteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Invite.objects.filter(
            user=self.request.user, status=Invite.Status.PENDING
        ).select_related("organization", "user")


class InviteAcceptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        invite = get_object_or_404(Invite, pk=pk, user=request.user)
        if invite.status != Invite.Status.PENDING:
            raise DRFValidationError("This invite is no longer pending.")
        invite.accept()
        return Response(InviteSerializer(invite).data)


class InviteDeclineView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        invite = get_object_or_404(Invite, pk=pk, user=request.user)
        if invite.status != Invite.Status.PENDING:
            raise DRFValidationError("This invite is no longer pending.")
        invite.decline()
        return Response(InviteSerializer(invite).data)
