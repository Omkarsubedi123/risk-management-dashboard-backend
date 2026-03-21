from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.db import transaction

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
    ProjectSummarySerializer,
    AdminPMListSerializer,
    AdminTransferOwnershipSerializer,
)
from .permissions import IsProjectPMOrReadOnly, IsProjectPM
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from users.permissions import IsAdminRole

User = get_user_model()


class ProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", None)

        if role == "PM":
            return Project.objects.filter(created_by=user).order_by("-created_at")

        return Project.objects.filter(team__user=user).distinct().order_by("-created_at")

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
    permission_classes = [permissions.IsAuthenticated, IsProjectPMOrReadOnly]

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
            return ProjectTeam.objects.filter(project=project).select_related("user")

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

        create_notification(
            removed_user,
            "Removed from Project",
            f"You were removed from the project '{project_name}'.",
            redirect_url=url_projects_home_for(removed_user),
        )

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

        # already member
        if ProjectTeam.objects.filter(project=project, user__email__iexact=email).exists():
            return Response({"detail": "User is already a member of this project."}, status=status.HTTP_200_OK)

        invited_user = User.objects.filter(email__iexact=email).first()
        existing_invite = Invite.objects.filter(project=project, email__iexact=email).first()

        if existing_invite and not existing_invite.accepted:
            return Response({"detail": "Invitation already sent."}, status=status.HTTP_200_OK)

        if existing_invite and existing_invite.accepted:
            existing_invite.delete()

        invite = Invite.objects.create(
            project=project,
            email=email,
            invited_by=request.user,
            invited_user=invited_user,
            role=role,
        )

        # Auto accept if already registered user exists
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

        invite_link = f"{settings.FRONTEND_URL}/accept-invite?token={invite.token}"

        send_mail(
            subject="Project Invitation",
            message=(
                f"You have been invited to join the project '{project.name}'.\n\n"
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

        invite = get_object_or_404(Invite, token=token, accepted=False)

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
        invite.save(update_fields=["invited_user", "accepted", "accepted_at"])

        create_notification(
            invite.project.created_by,
            "Invitation Accepted",
            f"{request.user.get_full_name() or request.user.email} joined '{invite.project.name}'.",
            redirect_url=url_manage_team(invite.project.id),
        )

        create_notification(
            request.user,
            "Invitation Accepted",
            f"You joined '{invite.project.name}'.",
            redirect_url=url_projects_home_for(request.user),
        )

        return Response({"detail": "Invitation accepted successfully."}, status=status.HTTP_200_OK)


class MyProjectsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProjectSummarySerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", None)

        if role == "PM":
            return Project.objects.filter(created_by=user).order_by("-updated_at")

        return Project.objects.filter(team__user=user).distinct().order_by("-updated_at")


class ProjectTeamListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        is_member = ProjectTeam.objects.filter(project=project, user=request.user).exists()
        is_pm = (project.created_by == request.user)

        if not (is_member or is_pm):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        team_qs = (
            ProjectTeam.objects.filter(project=project)
            .select_related("user")
            .order_by("role", "invited_at")
        )
        data = ProjectTeamSerializer(team_qs, many=True).data

        pending_invites = Invite.objects.filter(project=project, accepted=False).order_by("-created_at")

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


# =========================
# ADMIN PROJECT MANAGEMENT
# =========================

class AdminPMListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request):
        pms = User.objects.filter(role="PM", is_active=True).order_by("username", "email")
        serializer = AdminPMListSerializer(pms, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminProjectsByPMView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request, pm_id):
        pm = get_object_or_404(User, id=pm_id, role="PM")
        projects = Project.objects.filter(created_by=pm).order_by("-updated_at")
        serializer = ProjectSummarySerializer(projects, many=True)

        return Response({
            "pm": {
                "id": pm.id,
                "username": pm.username,
                "email": pm.email,
                "is_active": pm.is_active,
            },
            "project_count": projects.count(),
            "projects": serializer.data,
        }, status=status.HTTP_200_OK)


class AdminTransferOwnershipView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def post(self, request):
        serializer = AdminTransferOwnershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from_pm = serializer.validated_data["from_pm"]
        to_pm = serializer.validated_data["to_pm"]

        projects = Project.objects.filter(created_by=from_pm)

        if not projects.exists():
            return Response(
                {"detail": "Selected source PM has no projects to transfer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        transferred_project_ids = []
        transferred_project_names = []

        with transaction.atomic():
            for project in projects:
                project.created_by = to_pm
                project.save(update_fields=["created_by", "updated_at"])

                # ensure new PM is PM in project team
                ProjectTeam.objects.update_or_create(
                    project=project,
                    user=to_pm,
                    defaults={"role": ProjectTeam.ROLE_PM},
                )

                # remove old PM PM-membership from project
                old_pm_membership = ProjectTeam.objects.filter(
                    project=project,
                    user=from_pm,
                    role=ProjectTeam.ROLE_PM
                ).first()

                if old_pm_membership:
                    old_pm_membership.delete()

                transferred_project_ids.append(project.id)
                transferred_project_names.append(project.name)

                create_notification(
                    to_pm,
                    "Project Ownership Transferred",
                    f"You are now the Project Manager of '{project.name}'.",
                    redirect_url=url_project_for(to_pm, project.id),
                )

            create_notification(
                request.user,
                "Projects Transferred",
                f"{len(transferred_project_ids)} project(s) transferred from {from_pm.email} to {to_pm.email}.",
                redirect_url=url_projects_home_for(request.user),
            )

        return Response({
            "detail": "Project ownership transferred successfully.",
            "from_pm": {
                "id": from_pm.id,
                "email": from_pm.email,
                "username": from_pm.username,
            },
            "to_pm": {
                "id": to_pm.id,
                "email": to_pm.email,
                "username": to_pm.username,
            },
            "transferred_count": len(transferred_project_ids),
            "transferred_project_ids": transferred_project_ids,
            "transferred_project_names": transferred_project_names,
        }, status=status.HTTP_200_OK)