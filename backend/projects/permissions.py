# projects/permissions.py
from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import ProjectTeam

class IsProjectPMOrReadOnly(BasePermission):
    """
    PM (project creator) or team member read-only.
    PM can edit/delete (unsafe methods); others only safe methods.
    """

    def has_object_permission(self, request, view, obj):
        # Safe methods (GET/HEAD/OPTIONS) allowed to any authenticated user who can access the object
        if request.method in SAFE_METHODS:
            return True

        # Unsafe methods: allow only if user is the creator (PM)
        return obj.created_by == request.user


class IsProjectPM(BasePermission):
    """
    Only project PM (team role=PM) allowed.
    """

    def has_object_permission(self, request, view, obj):
        try:
            membership = ProjectTeam.objects.get(project=obj, user=request.user)
            return membership.role == ProjectTeam.ROLE_PM
        except ProjectTeam.DoesNotExist:
            return False
