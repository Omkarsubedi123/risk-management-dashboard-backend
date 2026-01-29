
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from notifications.utils import create_notification


from .models import Project, ProjectTeam, Invite
from .serializers import (
    ProjectSerializer,
    InviteSerializer,
    ProjectTeamSerializer,
)
from .permissions import IsProjectPMOrReadOnly, IsProjectPM

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
            f"Project '{project.name}' was created successfully."
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
            f"Project '{project.name}' was updated."
        )
    
    def perform_destroy(self, instance):
        project_name = instance.name
        instance.delete()
        create_notification(
            self.request.user,
            "Project Deleted",
            f"Project '{project_name}' was deleted."
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
        project_name = instance.project.name
        
        Invite.objects.filter(
            project=instance.project,
            email__iexact=removed_user.email
        ).delete()


        create_notification(
            removed_user,
            "Removed from Project",
            f"You were removed from the project '{project_name}'."
            )
        

        create_notification(
            self.request.user,
            "Member Removed",
            f"You removed {removed_user.email} from '{project_name}'."
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

        # ✅ membership check first (truth)
        if ProjectTeam.objects.filter(project=project, user__email__iexact=email).exists():
            return Response({"detail": "User is already a member of this project."}, status=status.HTTP_200_OK)
        invited_user = User.objects.filter(email__iexact=email).first()
        
        existing_invite = Invite.objects.filter(project=project, email__iexact=email).first()

        # ✅ pending invite blocks
        if existing_invite and not existing_invite.accepted:
            return Response({"detail": "Invitation already sent."}, status=status.HTTP_200_OK)

        # ✅ stale accepted invite cleanup (user was removed earlier)
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

        # ✅ AUTO-ACCEPT IF USER EXISTS
        # ✅ AUTO-ACCEPT IF USER EXISTS
        if invited_user:
            ProjectTeam.objects.update_or_create(
            project=project,
            user=invited_user,
            defaults={"role": ProjectTeam.ROLE_TM},
        )

        invite.accepted = True
        invite.accepted_at = timezone.now()
        invite.save(update_fields=["accepted", "accepted_at"])

        # ✅ Notification for invited user (TM)
        create_notification(
            invited_user,
            "Added to Project",
            f"You were added to the project '{project.name}'."
        )

        # ✅ Notification for PM (who invited) — THIS IS THE MISSING PART
        create_notification(
            request.user,
            "Member Added",
            f"{invited_user.email} was added to '{project.name}'."
        )

        return Response(
            {"detail": "User added to project."},
            status=status.HTTP_201_CREATED,
        )


        # 📧 Email invite for non-registered users
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
            f"Invitation sent to {email} for project '{project.name}'."
        )

        return Response(
            {"detail": "Invitation email sent."},
            status=status.HTTP_201_CREATED,
        )


class InviteAcceptView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response(
                {"detail": "Token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invite = get_object_or_404(
            Invite,
            token=token,
            accepted=False,
        )

        if request.user.email.lower() != invite.email.lower():
            return Response(
                {"detail": "This invite is for a different email."},
                status=status.HTTP_403_FORBIDDEN,
            )

        ProjectTeam.objects.get_or_create(
            project=invite.project,
            user=request.user,
            defaults={"role": invite.role},
        )

        invite.invited_user = request.user
        invite.accepted = True
        invite.accepted_at = timezone.now()
        invite.save()

        create_notification(
            invite.project.created_by,
            "Invitation Accepted",
            f"{request.user.get_full_name() or request.user.email} joined "
            f"'{invite.project.name}'."
        )

        return Response(
            {"detail": "Invitation accepted successfully."},
            status=status.HTTP_200_OK,
        )


# Team Members 
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
