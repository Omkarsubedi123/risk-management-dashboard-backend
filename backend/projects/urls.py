from django.urls import path
from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectMembersView,
    RemoveMemberView,
    InviteCreateView,
    InviteAcceptView,
    MyProjectsView,
    ProjectTeamListView,
    AdminPMListView,
    AdminProjectsByPMView,
    AdminTransferOwnershipView,
)

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list-create"),
    path("<int:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<int:pk>/members/", ProjectMembersView.as_view(), name="project-members"),
    path("<int:pk>/members/<int:member_id>/remove/", RemoveMemberView.as_view(), name="remove-member"),
    path("<int:pk>/invite/", InviteCreateView.as_view(), name="project-invite"),
    path("invite/accept/", InviteAcceptView.as_view(), name="invite-accept"),
    path("my/", MyProjectsView.as_view(), name="my-projects"),
    path("<int:pk>/team/", ProjectTeamListView.as_view(), name="project-team"),

    # Admin
    path("admin/pms/", AdminPMListView.as_view(), name="admin-pm-list"),
    path("admin/pms/<int:pm_id>/projects/", AdminProjectsByPMView.as_view(), name="admin-projects-by-pm"),
    path("admin/transfer-ownership/", AdminTransferOwnershipView.as_view(), name="admin-transfer-ownership"),
]