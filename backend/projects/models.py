# projects/models.py
import uuid
from django.db import models
from django.conf import settings

class Project(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    sector = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class ProjectTeam(models.Model):
    ROLE_PM = "PM"
    ROLE_TM = "TM"
    ROLE_CHOICES = [
        (ROLE_PM, "Project Manager"),
        (ROLE_TM, "Team Member"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="team")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_TM)
    invited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "user")
        verbose_name = "Project Team Member"
        verbose_name_plural = "Project Team Members"

    def __str__(self):
        return f"{self.user} — {self.project} ({self.role})"


class Invite(models.Model):
    """
    Invitation record. Token used for accepting an invite.
    If invited_user is set, invite targeted existing registered user.
    """
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invites")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_invites")
    email = models.EmailField()
    invited_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="received_invites")
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("project", "email")

    def __str__(self):
        return f"Invite {self.email} -> {self.project.name}"
