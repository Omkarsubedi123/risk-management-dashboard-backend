# projects/urls.py
from django.urls import path
from .views import (
    ProjectListCreateView, ProjectDetailView, ProjectMembersView,
    RemoveMemberView, InviteCreateView, InviteAcceptView
)

urlpatterns = [
    path("", ProjectListCreateView.as_view(), name="project-list-create"),
    path("<int:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("<int:pk>/members/", ProjectMembersView.as_view(), name="project-members"),
    path("<int:pk>/members/<int:member_id>/remove/", RemoveMemberView.as_view(), name="remove-member"),
    path("<int:pk>/invite/", InviteCreateView.as_view(), name="project-invite"),
    path("invite/accept/", InviteAcceptView.as_view(), name="invite-accept"),
]
