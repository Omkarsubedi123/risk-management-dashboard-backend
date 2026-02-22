from rest_framework.permissions import BasePermission

try:
    from projects.models import ProjectTeam
except Exception:
    ProjectTeam = None


class CanAccessRiskChat(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, risk):
        user = request.user
        role = getattr(user, "role", None)

        # PM owns project
        if role == "PM":
            return risk.project.created_by == user

        # TM: must be involved
        involved = (risk.created_by == user) or (risk.assigned_to == user)

        # Optional: allow project team members too
        if ProjectTeam is not None:
            try:
                in_team = ProjectTeam.objects.filter(project=risk.project, user=user).exists()
                return involved or in_team
            except Exception:
                return involved

        return involved