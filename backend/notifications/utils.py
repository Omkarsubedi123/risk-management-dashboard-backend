from .models import Notification


def _role(user):
    return (getattr(user, "role", "") or "").upper().strip()


def url_risk_for(user, risk_id: int) -> str:
    # TM has separate risk details route
    return f"/tm/risks/{risk_id}" if _role(user) == "TM" else f"/risks/{risk_id}"


def url_project_for(user, project_id: int) -> str:
    # TM has separate project detail route
    return f"/tm/projects/{project_id}" if _role(user) == "TM" else f"/projects/{project_id}"


def url_projects_home_for(user) -> str:
    # Where to send user for "project list"
    return "/tm/projects" if _role(user) == "TM" else "/projects"


def url_manage_team(project_id: int) -> str:
    # Only PM has manage team route in your frontend
    return f"/projects/{project_id}/team"


def create_notification(user, title, message, redirect_url=None):
    """
    Backward compatible helper.
    Existing calls without redirect_url still work.
    """
    if not user:
        return None

    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        redirect_url=(redirect_url or "").strip(),
    )