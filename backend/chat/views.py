from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from notifications.utils import create_notification
from risks.models import Risk

try:
    from projects.models import ProjectTeam
except Exception:
    ProjectTeam = None

from .models import RiskMessage
from .serializers import RiskMessageSerializer, RiskMessageCreateSerializer, MENTION_RE
from .permissions import CanAccessRiskChat

User = get_user_model()


def _notify_mentions(sender, risk, body: str):
    usernames = set(MENTION_RE.findall(body or ""))
    if not usernames:
        return

    # Only notify users that are part of THIS project/risk context
    targets = User.objects.filter(username__in=list(usernames)).distinct()

    for u in targets:
        if u == sender:
            continue

        role = getattr(u, "role", None)

        # PM mentioned -> must be project owner
        if role == "PM":
            if risk.project.created_by != u:
                continue
        else:
            # TM/others -> must be involved or in team
            involved = (u == risk.created_by) or (u == risk.assigned_to)
            in_team = False
            if ProjectTeam is not None:
                in_team = ProjectTeam.objects.filter(project=risk.project, user=u).exists()
            if not (involved or in_team):
                continue

        create_notification(
            u,
            "You were mentioned",
            f"{sender.get_full_name() or sender.username} mentioned you in risk '{risk.title}'."
        )


def _notify_new_message(sender, risk):
    pm_user = risk.project.created_by

    # Notify PM when someone else posts
    if pm_user and pm_user != sender:
        create_notification(
            pm_user,
            "New Risk Message",
            f"New message on risk '{risk.title}' in project '{risk.project.name}'."
        )

    # Notify assigned user if not sender and not PM
    if risk.assigned_to and risk.assigned_to != sender and risk.assigned_to != pm_user:
        create_notification(
            risk.assigned_to,
            "New Risk Message",
            f"New message on risk '{risk.title}'."
        )


class RiskMessageListCreateView(generics.GenericAPIView):
    permission_classes = [CanAccessRiskChat]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, risk_id):
        risk = get_object_or_404(Risk.objects.select_related("project"), pk=risk_id)
        self.check_object_permissions(request, risk)

        qs = (
            RiskMessage.objects.filter(risk_id=risk_id)
            .select_related("sender")
            .prefetch_related("attachments")
            .order_by("created_at")
        )

        return Response(RiskMessageSerializer(qs, many=True, context={"request": request}).data)

    def post(self, request, risk_id):
        risk = get_object_or_404(
            Risk.objects.select_related("project", "assigned_to", "created_by"),
            pk=risk_id
        )
        self.check_object_permissions(request, risk)

        # recommended: chat only after approved
        if (risk.approval_status or "").lower() != "approved":
            return Response(
                {"detail": "Chat is available only after PM approves the risk."},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = request.data.copy()
        data["risk"] = risk_id

        files = request.FILES.getlist("files")
        if files:
            data.setlist("files", files)

        ser = RiskMessageCreateSerializer(data=data, context={"request": request})
        ser.is_valid(raise_exception=True)
        msg = ser.save()

        _notify_new_message(request.user, risk)
        _notify_mentions(request.user, risk, msg.body)

        return Response(
            RiskMessageSerializer(msg, context={"request": request}).data,
            status=status.HTTP_201_CREATED
        )


# ✅ NEW: Edit message (only author can edit)
class RiskMessageEditView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, message_id):
        msg = get_object_or_404(
            RiskMessage.objects.select_related("risk__project", "sender", "risk__assigned_to", "risk__created_by"),
            pk=message_id
        )
        risk = msg.risk

        # Reuse your existing object permission logic safely
        perm = CanAccessRiskChat()
        if not perm.has_object_permission(request, self, risk):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        # Only author can edit
        if msg.sender_id != request.user.id:
            return Response({"detail": "You can edit only your own message."}, status=status.HTTP_403_FORBIDDEN)

        new_body = (request.data.get("body") or "").strip()

        # allow edit only if message still has attachments or body is not empty
        has_attachments = msg.attachments.exists()
        if not new_body and not has_attachments:
            return Response({"detail": "Message cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        msg.body = new_body
        msg.edited_at = timezone.now()
        msg.save(update_fields=["body", "edited_at"])

        # notify mentions if changed
        _notify_mentions(request.user, risk, msg.body)

        return Response(RiskMessageSerializer(msg, context={"request": request}).data, status=status.HTTP_200_OK)


# ✅ NEW: Participants list for @mention suggestions (real project members)
class RiskChatParticipantsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, risk_id):
        risk = get_object_or_404(
            Risk.objects.select_related("project", "assigned_to", "created_by", "project__created_by"),
            pk=risk_id
        )

        perm = CanAccessRiskChat()
        if not perm.has_object_permission(request, self, risk):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        ids = set()

        # PM
        if risk.project.created_by_id:
            ids.add(risk.project.created_by_id)

        # Team members (ProjectTeam)
        if ProjectTeam is not None:
            team_ids = ProjectTeam.objects.filter(project=risk.project).values_list("user_id", flat=True)
            ids.update(list(team_ids))

        # Risk creator + assignee
        if risk.created_by_id:
            ids.add(risk.created_by_id)
        if risk.assigned_to_id:
            ids.add(risk.assigned_to_id)

        users = User.objects.filter(id__in=list(ids)).order_by("username")

        data = []
        for u in users:
            data.append({
                "id": u.id,
                "name": (u.get_full_name() or getattr(u, "username", "") or getattr(u, "email", "")),
                "username": getattr(u, "username", "") or "",
                "email": getattr(u, "email", "") or "",
            })

        return Response(data, status=status.HTTP_200_OK)