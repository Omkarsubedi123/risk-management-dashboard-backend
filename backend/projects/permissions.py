from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Project, ProjectTeam


class IsProjectPMOrReadOnly(BasePermission):
    """
    - Project creator/PM can do all actions
    - Team members can read only
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return (
                obj.created_by == request.user or
                ProjectTeam.objects.filter(project=obj, user=request.user).exists()
            )

        if obj.created_by == request.user:
            return True

        return ProjectTeam.objects.filter(
            project=obj,
            user=request.user,
            role=ProjectTeam.ROLE_PM
        ).exists()


class IsProjectPM(BasePermission):
    """
    Only PM of the project can perform the action.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user

        if isinstance(obj, Project):
            return obj.created_by == user

        if isinstance(obj, ProjectTeam):
            return obj.project.created_by == user

        return ProjectTeam.objects.filter(
            project=obj,
            user=user,
            role=ProjectTeam.ROLE_PM
        ).exists()