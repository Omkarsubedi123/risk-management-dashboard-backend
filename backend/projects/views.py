# projects/views.py
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import Project, ProjectTeam, Invite
from .serializers import ProjectSerializer, InviteSerializer, ProjectTeamSerializer
from .permissions import IsProjectPMOrReadOnly, IsProjectPM

User = get_user_model()

class ProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # If user has explicit role field and is PM, show created projects
        role = getattr(user, "role", None)
        if role == "PM":
            return Project.objects.filter(created_by=user).order_by("-created_at")
        # otherwise show projects where user is member
        return Project.objects.filter(team__user=user).order_by("-created_at")

    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user)
        # add creator as PM in ProjectTeam
        ProjectTeam.objects.get_or_create(project=project, user=self.request.user, defaults={"role": ProjectTeam.ROLE_PM})


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated, IsProjectPMOrReadOnly]


class ProjectMembersView(generics.ListAPIView):
    serializer_class = ProjectTeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_id = self.kwargs.get("pk")
        project = get_object_or_404(Project, pk=project_id)
        user = self.request.user
        # allow view if user is PM (creator) or member
        if project.created_by == user or project.team.filter(user=user).exists():
            return ProjectTeam.objects.filter(project=project)
        # else return empty queryset (client will get 200 with empty list or you can raise 403)
        return ProjectTeam.objects.none()


class RemoveMemberView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, IsProjectPM]
    lookup_url_kwarg = "member_id"
    queryset = ProjectTeam.objects.all()

    def perform_destroy(self, instance):
        # Prevent removing PM
        if instance.role == ProjectTeam.ROLE_PM:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Cannot remove the Project Manager from the project.")
        instance.delete()


class InviteCreateView(generics.GenericAPIView):
    serializer_class = InviteSerializer
    permission_classes = [permissions.IsAuthenticated, IsProjectPM]

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        # check PM permission
        self.check_object_permissions(request, project)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        invited_user = None
        try:
            invited_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            invited_user = None

        invite, created = Invite.objects.get_or_create(
            project=project,
            email=email,
            defaults={"invited_by": request.user, "invited_user": invited_user}
        )

        if not created:
            return Response({"detail": "Invite already exists."}, status=status.HTTP_200_OK)

        # If user exists, add immediately as member
        if invited_user:
            ProjectTeam.objects.get_or_create(project=project, user=invited_user, defaults={"role": ProjectTeam.ROLE_TM})
            invite.invited_user = invited_user
            invite.accepted = True
            invite.accepted_at = timezone.now()
            invite.save()
            return Response({"detail": "User added to project."}, status=status.HTTP_201_CREATED)

        # else TODO: send email with invite.token (frontend link)
        # Example link: f"{FRONTEND_URL}/accept-invite?token={invite.token}"
        return Response({"detail": "Invite created; user must accept or sign up."}, status=status.HTTP_201_CREATED)


class InviteAcceptView(generics.GenericAPIView):
    serializer_class = InviteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        token = request.data.get("token")
        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        invite = get_object_or_404(Invite, token=token)
        if invite.accepted:
            return Response({"detail": "Invite already accepted."}, status=status.HTTP_400_BAD_REQUEST)

        # email must match logged-in user
        if request.user.email.lower() != invite.email.lower():
            return Response({"detail": "This invite is for a different email."}, status=status.HTTP_403_FORBIDDEN)

        membership, created = ProjectTeam.objects.get_or_create(project=invite.project, user=request.user, defaults={"role": ProjectTeam.ROLE_TM})
        invite.invited_user = request.user
        invite.accepted = True
        invite.accepted_at = timezone.now()
        invite.save()

        return Response({"detail": "Invite accepted. You are now a team member."}, status=status.HTTP_200_OK)
