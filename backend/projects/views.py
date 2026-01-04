# projects/views.py

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model

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


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsProjectPMOrReadOnly,
    ]


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
            raise PermissionDenied(
                "Cannot remove the Project Manager from the project."
            )
        instance.delete()


# =========================
# INVITATION VIEWS (EMAIL BASED)
# =========================

# class InviteCreateView(generics.GenericAPIView):
#     serializer_class = InviteSerializer
#     permission_classes = [permissions.IsAuthenticated, IsProjectPM]

#     def post(self, request, pk):
#         project = get_object_or_404(Project, pk=pk)
#         self.check_object_permissions(request, project)

#         email = request.data.get("email", "").lower()
#         role = request.data.get("role", ProjectTeam.ROLE_TM)

#         if not email:
#             return Response(
#                 {"detail": "Email is required."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         invited_user = User.objects.filter(email__iexact=email).first()

#         invite, created = Invite.objects.get_or_create(
#             project=project,
#             email=email,
#             defaults={
#                 "invited_by": request.user,
#                 "invited_user": invited_user,
#                 "role": role,
#             },
#         )

#         if not created:
#             return Response(
#                 {"detail": "Invite already exists."},
#                 status=status.HTTP_200_OK,
#             )

#         # If user already exists → auto add
#         if invited_user:
#             ProjectTeam.objects.get_or_create(
#                 project=project,
#                 user=invited_user,
#                 defaults={"role": role},
#             )
#             invite.accepted = True
#             invite.accepted_at = timezone.now()
#             invite.save()

#             return Response(
#                 {"detail": "User added to project."},
#                 status=status.HTTP_201_CREATED,
#             )

#         # Send email invitation
#         invite_link = (
#             f"{settings.FRONTEND_URL}/accept-invite?token={invite.token}"
#         )

#         send_mail(
#             subject="Project Invitation",
#             message=(
#                 f"You have been invited to join the project "
#                 f"'{project.name}'.\n\n"
#                 f"Click the link below to accept the invitation:\n"
#                 f"{invite_link}"
#             ),
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=[email],
#             fail_silently=False,
#         )

#         return Response(
#             {"detail": "Invitation email sent."},
#             status=status.HTTP_201_CREATED,
#         )

class InviteCreateView(generics.GenericAPIView):
    serializer_class = InviteSerializer
    permission_classes = [permissions.IsAuthenticated, IsProjectPM]

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        self.check_object_permissions(request, project)

        email = request.data.get("email", "").lower().strip()
        role = ProjectTeam.ROLE_TM  # 🔒 PM cannot invite another PM

        if not email:
            return Response(
                {"detail": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invited_user = User.objects.filter(email__iexact=email).first()

        # 🔴 Prevent duplicate accepted invite
        existing_invite = Invite.objects.filter(
            project=project,
            email=email,
        ).first()

        if existing_invite:
            if existing_invite.accepted:
                return Response(
                    {"detail": "User is already a member of this project."},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"detail": "Invitation already sent."},
                status=status.HTTP_200_OK,
            )

        # Create invite
        invite = Invite.objects.create(
            project=project,
            email=email,
            invited_by=request.user,
            invited_user=invited_user,
            role=role,
        )

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

        return Response(
            {"detail": "Invitation accepted successfully."},
            status=status.HTTP_200_OK,
        )
