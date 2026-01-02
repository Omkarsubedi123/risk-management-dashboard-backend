from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import ProjectTeam


class IsProjectPMOrReadOnly(BasePermission):
    """
    - Project Manager (PM) can perform all actions
    - Team members can READ only (safe methods)
    """

    def has_object_permission(self, request, view, obj):
        # Allow safe methods to project creator or team members
        if request.method in SAFE_METHODS:
            return (
                obj.created_by == request.user or
                ProjectTeam.objects.filter(project=obj, user=request.user).exists()
            )

        # Unsafe methods → only PM allowed
        if obj.created_by == request.user:
            return True

        return ProjectTeam.objects.filter(
            project=obj,
            user=request.user,
            role=ProjectTeam.ROLE_PM
        ).exists()


class IsProjectPM(BasePermission):
    """
    Only Project Managers are allowed.
    (Creator OR team role = PM)
    """

    def has_object_permission(self, request, view, obj):
        # Creator is always PM
        if obj.created_by == request.user:
            return True

        # Check PM role in team
        return ProjectTeam.objects.filter(
            project=obj,
            user=request.user,
            role=ProjectTeam.ROLE_PM
        ).exists()
