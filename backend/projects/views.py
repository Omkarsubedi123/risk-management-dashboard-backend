from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model

from notifications.utils import (
    create_notification,
    url_project_for,
    url_projects_home_for,
    url_manage_team,
)

from .models import Project, ProjectTeam, Invite
from .serializers import (
    ProjectSerializer,
    InviteSerializer,
    ProjectTeamSerializer,
)
from .permissions import IsProjectPMOrReadOnly, IsProjectPM
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

User = get_user_model()

# =========================
# PROJECT VIEWS
# =========================

class ProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", None)

        if role == "PM":
            return Project.objects.filter(created_by=user).order_by("-created_at")

        return Project.objects.filter(team__user=user).order_by("-created_at")

    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user)
        ProjectTeam.objects.get_or_create(
            project=project,
            user=self.request.user,
            defaults={"role": ProjectTeam.ROLE_PM},
        )

        create_notification(
            self.request.user,
            "Project Created",
            f"Project '{project.name}' was created successfully.",
            redirect_url=url_project_for(self.request.user, project.id),
        )


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsProjectPMOrReadOnly,
    ]

    def perform_update(self, serializer):
        project = serializer.save()
        create_notification(
            self.request.user,
            "Project Updated",
            f"Project '{project.name}' was updated.",
            redirect_url=url_project_for(self.request.user, project.id),
        )

    def perform_destroy(self, instance):
        project_name = instance.name
        instance.delete()
        create_notification(
            self.request.user,
            "Project Deleted",
            f"Project '{project_name}' was deleted.",
            redirect_url=url_projects_home_for(self.request.user),
        )


class ProjectMembersView(generics.ListAPIView):
    serializer_class = ProjectTeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project = get_object_or_404(Project, pk=self.kwargs.get("pk"))
        user = self.request.user

        if project.created_by == user or project.team.filter(user=user).exists():
            return ProjectTeam.objects.filter(project=project)

        return ProjectTeam.objects.none()


class RemoveMemberView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, IsProjectPM]
    lookup_url_kwarg = "member_id"
    queryset = ProjectTeam.objects.all()

    def perform_destroy(self, instance):
        if instance.role == ProjectTeam.ROLE_PM:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Cannot remove the Project Manager from the project.")

        removed_user = instance.user
        project = instance.project
        project_name = project.name

        Invite.objects.filter(
            project=project,
            email__iexact=removed_user.email,
        ).delete()

        # Removed user is typically TM -> send them to their projects list
        create_notification(
            removed_user,
            "Removed from Project",
            f"You were removed from the project '{project_name}'.",
            redirect_url=url_projects_home_for(removed_user),
        )

        # PM -> send to manage team page
        create_notification(
            self.request.user,
            "Member Removed",
            f"You removed {removed_user.email} from '{project_name}'.",
            redirect_url=url_manage_team(project.id),
        )

        instance.delete()


class InviteCreateView(generics.GenericAPIView):
    serializer_class = InviteSerializer
    permission_classes = [permissions.IsAuthenticated, IsProjectPM]

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        self.check_object_permissions(request, project)

        email = request.data.get("email", "").lower().strip()
        role = ProjectTeam.ROLE_TM

        if not email:
            return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        # membership check first (truth)
        if ProjectTeam.objects.filter(project=project, user__email__iexact=email).exists():
            return Response({"detail": "User is already a member of this project."}, status=status.HTTP_200_OK)

        invited_user = User.objects.filter(email__iexact=email).first()
        existing_invite = Invite.objects.filter(project=project, email__iexact=email).first()

        # pending invite blocks
        if existing_invite and not existing_invite.accepted:
            return Response({"detail": "Invitation already sent."}, status=status.HTTP_200_OK)

        # stale accepted invite cleanup (user was removed earlier)
        if existing_invite and existing_invite.accepted:
            existing_invite.delete()
            existing_invite = None

        # Create new invite now
        invite = Invite.objects.create(
            project=project,
            email=email,
            invited_by=request.user,
            invited_user=invited_user,
            role=role,
        )

        # AUTO-ACCEPT IF USER EXISTS
        if invited_user:
            ProjectTeam.objects.update_or_create(
                project=project,
                user=invited_user,
                defaults={"role": ProjectTeam.ROLE_TM},
            )

            invite.accepted = True
            invite.accepted_at = timezone.now()
            invite.save(update_fields=["accepted", "accepted_at", "invited_user"])

            create_notification(
                invited_user,
                "Added to Project",
                f"You were added to the project '{project.name}'.",
                redirect_url=url_projects_home_for(invited_user),
            )

            create_notification(
                request.user,
                "Member Added",
                f"{invited_user.email} was added to '{project.name}'.",
                redirect_url=url_manage_team(project.id),
            )

            return Response({"detail": "User added to project."}, status=status.HTTP_201_CREATED)

        # Email invite for non-registered users
        invite_link = f"{settings.FRONTEND_URL}/accept-invite?token={invite.token}"

        send_mail(
            subject="Project Invitation",
            message=(
                f"You have been invited to join the project "
                f"'{project.name}'.\n\n"
                f"Click the link below to accept the invitation:\n"
                f"{invite_link}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

        create_notification(
            request.user,
            "Invitation Sent",
            f"Invitation sent to {email} for project '{project.name}'.",
            redirect_url=url_manage_team(project.id),
        )

        return Response({"detail": "Invitation email sent."}, status=status.HTTP_201_CREATED)


class InviteAcceptView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        invite = get_object_or_404(
            Invite,
            token=token,
            accepted=False,
        )

        if request.user.email.lower() != invite.email.lower():
            return Response({"detail": "This invite is for a different email."}, status=status.HTTP_403_FORBIDDEN)

        ProjectTeam.objects.get_or_create(
            project=invite.project,
            user=request.user,
            defaults={"role": invite.role},
        )

        invite.invited_user = request.user
        invite.accepted = True
        invite.accepted_at = timezone.now()
        invite.save()

        # PM -> manage team page
        create_notification(
            invite.project.created_by,
            "Invitation Accepted",
            f"{request.user.get_full_name() or request.user.email} joined '{invite.project.name}'.",
            redirect_url=url_manage_team(invite.project.id),
        )

        # TM -> their projects list
        create_notification(
            request.user,
            "Invitation Accepted",
            f"You joined '{invite.project.name}'.",
            redirect_url=url_projects_home_for(request.user),
        )

        return Response({"detail": "Invitation accepted successfully."}, status=status.HTTP_200_OK)


# =========================
# Team Members / TM Projects
# =========================

from .serializers import ProjectSummarySerializer


class MyProjectsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProjectSummarySerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", None)

        # PM: projects they created
        if role == "PM":
            return Project.objects.filter(created_by=user).order_by("-updated_at")

        # TM: projects where they are in ProjectTeam (team related_name)
        return Project.objects.filter(team__user=user).distinct().order_by("-updated_at")


class ProjectTeamListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        # Only PM (created_by) OR project members can view
        is_member = ProjectTeam.objects.filter(project=project, user=request.user).exists()
        is_pm = (project.created_by == request.user)

        if not (is_member or is_pm):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        # Real joined members
        team_qs = (
            ProjectTeam.objects.filter(project=project)
            .select_related("user")
            .order_by("role", "invited_at")
        )
        data = ProjectTeamSerializer(team_qs, many=True).data

        # Pending invites = accepted=False
        pending_invites = Invite.objects.filter(project=project, accepted=False).order_by("-created_at")

        # Add invite entries so frontend can show "Invited"
        for inv in pending_invites:
            data.append({
                "id": f"invite-{inv.id}",
                "user_id": None,
                "email": inv.email,
                "username": inv.email,
                "full_name": "",
                "role": inv.role or "TM",
                "invited_at": inv.created_at,
                "is_invited": True,
            })

        return Response(data, status=status.HTTP_200_OK)