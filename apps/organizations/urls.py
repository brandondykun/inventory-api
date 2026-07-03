"""Organization routes (mounted under /api/)."""

from django.urls import path

from .views import (
    InviteAcceptView,
    InviteDeclineView,
    MemberDetailView,
    MemberListView,
    MyInviteListView,
    OrganizationDetailView,
    OrganizationListCreateView,
    OrganizationTransferOwnershipView,
    OrgInviteListCreateView,
)

app_name = "organizations"

urlpatterns = [
    path("organizations/", OrganizationListCreateView.as_view(), name="list-create"),
    path(
        "organizations/<uuid:pk>/",
        OrganizationDetailView.as_view(),
        name="detail",
    ),
    path(
        "organizations/<uuid:pk>/transfer-ownership/",
        OrganizationTransferOwnershipView.as_view(),
        name="transfer-ownership",
    ),
    path(
        "organizations/<uuid:org_id>/members/",
        MemberListView.as_view(),
        name="member-list",
    ),
    path(
        "organizations/<uuid:org_id>/members/<uuid:user_id>/",
        MemberDetailView.as_view(),
        name="member-detail",
    ),
    path(
        "organizations/<uuid:org_id>/invites/",
        OrgInviteListCreateView.as_view(),
        name="org-invite-list-create",
    ),
    path("invites/", MyInviteListView.as_view(), name="my-invite-list"),
    path(
        "invites/<uuid:pk>/accept/",
        InviteAcceptView.as_view(),
        name="invite-accept",
    ),
    path(
        "invites/<uuid:pk>/decline/",
        InviteDeclineView.as_view(),
        name="invite-decline",
    ),
]
