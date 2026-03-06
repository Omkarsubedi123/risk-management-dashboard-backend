from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.utils import create_notification, url_risk_for

from .models import Risk
from .serializers import (
    RiskMitigationUpdateSerializer,
    RiskSerializer,
    RiskTMStatusUpdateSerializer,
)
from .services.gemini_ai import generate_ai_mitigation_two_lines


class RiskViewSet(viewsets.ModelViewSet):
    serializer_class = RiskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Risk.objects.select_related("project", "assigned_to", "created_by")
        role = getattr(user, "role", None)

        # Hide rejected risks from normal APIs
        qs = qs.exclude(approval_status="rejected")

        # PM sees all risks inside their projects (including TM created)
        if role == "PM":
            qs = qs.filter(project__created_by=user)
        else:
            # TM sees assigned + created
            qs = qs.filter(Q(assigned_to=user) | Q(created_by=user))

        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)

        approval_status_param = self.request.query_params.get("approval_status")
        if approval_status_param:
            qs = qs.filter(approval_status=approval_status_param)

        return qs.order_by("-created_at")

    @action(detail=False, methods=["get"], url_path="trash")
    def trash(self, request):
        user = request.user
        qs = Risk.objects.filter(approval_status="rejected")

        role = getattr(user, "role", None)
        if role == "PM":
            qs = qs.filter(project__created_by=user)
        else:
            qs = qs.filter(Q(created_by=user) | Q(assigned_to=user))

        project_id = request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)

        return Response(RiskSerializer(qs.order_by("-rejected_at"), many=True).data)

    # =========================
    # AI Mitigation (PM only)
    # =========================
    @action(detail=True, methods=["post"], url_path="ai-mitigation")
    def ai_mitigation(self, request, pk=None):
        """
        PM-only: returns a short 2-line mitigation suggestion.
        Preview only (does not save).
        Frontend will Apply -> then save via existing mitigation endpoint.
        """
        risk = self.get_object()
        user = request.user

        # PM only and must own the project
        if getattr(user, "role", None) != "PM" or risk.project.created_by != user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        # Optional: only approved risks
        if (risk.approval_status or "").lower() != "approved":
            return Response(
                {"detail": "AI mitigation is available only for approved risks."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            suggestion = generate_ai_mitigation_two_lines(risk)
            if not suggestion.strip():
                return Response(
                    {"detail": "AI returned empty text. Try again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {"suggestion": suggestion, "model": getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            msg = str(e)

            # Friendly 429 / quota message
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg or "quota" in msg.lower():
                return Response(
                    {"detail": "Free AI limit reached. Please try again later."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            return Response(
                {"detail": f"AI generation failed: {msg}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # =========================
    # Risk Created Notification + approval workflow
    # =========================
    def perform_create(self, serializer):
        user = self.request.user
        role = getattr(user, "role", None)

        risk = serializer.save(created_by=user)

        # PERMANENT DEFAULT:
        # If TM creates a risk and frontend didn't choose assignee, assign to TM.
        if role == "TM" and risk.assigned_to is None:
            risk.assigned_to = user
            risk.save(update_fields=["assigned_to"])

        if role == "TM":
            risk.approval_status = "pending"
            risk.save(update_fields=["approval_status"])

            pm_user = risk.project.created_by

            create_notification(
                pm_user,
                "New Risk Submitted",
                f"TM submitted risk '{risk.title}' in project '{risk.project.name}'.",
                redirect_url=url_risk_for(pm_user, risk.id),
            )

            create_notification(
                user,
                "Risk Submitted",
                f"Your risk '{risk.title}' was submitted for PM approval.",
                redirect_url=url_risk_for(user, risk.id),
            )
        else:
            risk.approval_status = "approved"
            risk.save(update_fields=["approval_status"])

            create_notification(
                user,
                "Risk Created",
                f"A new risk was added to project '{risk.project.name}'.",
                redirect_url=url_risk_for(user, risk.id),
            )

    # Risk Updated Notification
    def perform_update(self, serializer):
        risk = serializer.save()

        create_notification(
            self.request.user,
            "Risk Updated",
            f"A risk in project '{risk.project.name}' was updated.",
            redirect_url=url_risk_for(self.request.user, risk.id),
        )

    # TM cannot delete risks
    def destroy(self, request, *args, **kwargs):
        role = getattr(request.user, "role", None)
        if role != "PM":
            return Response(
                {"detail": "Team Members cannot delete risks."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    # Risk Deleted Notification (PM only)
    def perform_destroy(self, instance):
        project_name = instance.project.name
        instance.delete()

        create_notification(
            self.request.user,
            "Risk Deleted",
            f"A risk was removed from project '{project_name}'.",
            redirect_url="/risks",
        )

    # =========================
    # PM Approval Actions (Risk)
    # =========================
    @action(detail=True, methods=["patch"], url_path="approve")
    def approve(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "PM":
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if risk.project.created_by != user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        risk.approval_status = "approved"
        if hasattr(risk, "approved_at"):
            risk.approved_at = timezone.now()
            risk.save(update_fields=["approval_status", "approved_at"])
        else:
            risk.save(update_fields=["approval_status"])

        if risk.created_by:
            create_notification(
                risk.created_by,
                "Risk Approved",
                f"Your risk '{risk.title}' was approved by the Project Manager.",
                redirect_url=url_risk_for(risk.created_by, risk.id),
            )

        create_notification(
            user,
            "Risk Approved",
            f"You approved risk '{risk.title}' in '{risk.project.name}'.",
            redirect_url=url_risk_for(user, risk.id),
        )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"], url_path="reject")
    def reject(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "PM":
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if risk.project.created_by != user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        risk.approval_status = "rejected"
        if hasattr(risk, "rejected_at"):
            risk.rejected_at = timezone.now()
            risk.save(update_fields=["approval_status", "rejected_at"])
        else:
            risk.save(update_fields=["approval_status"])

        if risk.created_by:
            create_notification(
                risk.created_by,
                "Risk Rejected",
                f"Your risk '{risk.title}' was rejected by the Project Manager.",
                redirect_url=url_risk_for(risk.created_by, risk.id),
            )

        create_notification(
            user,
            "Risk Rejected",
            f"You rejected risk '{risk.title}' in '{risk.project.name}'.",
            redirect_url="/risks",
        )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)

    # ==========================================================
    # TM -> Update Risk STATUS
    # ==========================================================
    @action(detail=True, methods=["patch"], url_path="tm-status")
    def tm_status(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "TM":
            return Response(
                {"detail": "Only Team Members can update risk status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user != risk.created_by and user != risk.assigned_to:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if (risk.approval_status or "").lower() != "approved":
            return Response(
                {"detail": "You can update status only after risk is approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RiskTMStatusUpdateSerializer(risk, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        old_status = risk.status
        serializer.save()
        new_status = risk.status

        pm_user = risk.project.created_by

        if pm_user and pm_user != user and old_status != new_status:
            create_notification(
                pm_user,
                "Risk Status Updated",
                f"TM updated risk '{risk.title}' status: {old_status} → {new_status} (Project: {risk.project.name}).",
                redirect_url=url_risk_for(pm_user, risk.id),
            )

        if old_status != new_status:
            create_notification(
                user,
                "Status Saved",
                f"Risk '{risk.title}' status updated: {old_status} → {new_status}.",
                redirect_url=url_risk_for(user, risk.id),
            )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)

    # ==========================================================
    # TM -> Suggest Mitigation
    # ==========================================================
    @action(detail=True, methods=["patch"], url_path="suggest-mitigation")
    def suggest_mitigation(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "TM":
            return Response(
                {"detail": "Only Team Members can suggest mitigation."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user != risk.created_by and user != risk.assigned_to:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if (risk.approval_status or "").lower() != "approved":
            return Response(
                {"detail": "You can suggest mitigation only after risk is approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        possible_keys = [
            "suggestion",
            "mitigation_suggestion",
            "tm_mitigation_suggestion",
            "tm_suggestion",
            "suggested_mitigation",
            "suggestion_text",
            "text",
            "message",
        ]
        raw = ""
        for k in possible_keys:
            val = request.data.get(k)
            if val is not None:
                raw = val
                break

        suggestion = (raw or "").strip()
        if not suggestion:
            return Response({"detail": "Suggestion is required."}, status=status.HTTP_400_BAD_REQUEST)

        risk.tm_mitigation_suggestion = suggestion
        risk.tm_suggestion_status = "pending"

        risk.save(update_fields=["tm_mitigation_suggestion", "tm_suggestion_status"])

        pm_user = risk.project.created_by
        if pm_user:
            create_notification(
                pm_user,
                "Mitigation Suggested",
                f"TM suggested mitigation for risk '{risk.title}' in '{risk.project.name}'.",
                redirect_url=url_risk_for(pm_user, risk.id),
            )

        create_notification(
            user,
            "Suggestion Submitted",
            f"Your mitigation suggestion for '{risk.title}' was sent to the PM.",
            redirect_url=url_risk_for(user, risk.id),
        )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)

    # ==========================================================
    # PM -> Approve & Apply Suggestion
    # ==========================================================
    @action(detail=True, methods=["patch"], url_path="approve-suggestion")
    def approve_suggestion(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "PM":
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if risk.project.created_by != user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if (risk.tm_suggestion_status or "").lower() != "pending":
            return Response({"detail": "No pending suggestion to approve."}, status=status.HTTP_400_BAD_REQUEST)

        risk.mitigation_plan = risk.tm_mitigation_suggestion

        new_status = request.data.get("mitigation_status")
        if new_status in ["NotStarted", "InProgress", "Completed"]:
            risk.mitigation_status = new_status

        risk.tm_suggestion_status = "approved"
        risk.save(update_fields=["mitigation_plan", "mitigation_status", "tm_suggestion_status"])

        tm_user = risk.created_by
        if tm_user:
            create_notification(
                tm_user,
                "Suggestion Approved",
                f"Your mitigation suggestion for '{risk.title}' was approved and applied by the PM.",
                redirect_url=url_risk_for(tm_user, risk.id),
            )

        create_notification(
            user,
            "Suggestion Applied",
            f"You approved and applied mitigation suggestion for '{risk.title}'.",
            redirect_url=url_risk_for(user, risk.id),
        )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)

    # ==========================================================
    # PM -> Reject Suggestion
    # ==========================================================
    @action(detail=True, methods=["patch"], url_path="reject-suggestion")
    def reject_suggestion(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "PM":
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if risk.project.created_by != user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if (risk.tm_suggestion_status or "").lower() != "pending":
            return Response({"detail": "No pending suggestion to reject."}, status=status.HTTP_400_BAD_REQUEST)

        risk.tm_suggestion_status = "rejected"
        risk.save(update_fields=["tm_suggestion_status"])

        tm_user = risk.created_by
        if tm_user:
            create_notification(
                tm_user,
                "Suggestion Rejected",
                f"Your mitigation suggestion for '{risk.title}' was rejected by the PM.",
                redirect_url=url_risk_for(tm_user, risk.id),
            )

        create_notification(
            user,
            "Suggestion Rejected",
            f"You rejected mitigation suggestion for '{risk.title}'.",
            redirect_url=url_risk_for(user, risk.id),
        )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)


class RiskMitigationUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        """
        - PM (project owner) can update mitigation_plan + mitigation_status
        - TM can update ONLY mitigation_status (progress), NOT the plan
        """
        risk = get_object_or_404(Risk.objects.select_related("project"), pk=pk)
        user = request.user
        role = getattr(user, "role", None)

        pm_user = risk.project.created_by

        if role == "PM" and pm_user == user:
            allowed_data = request.data.copy()
        else:
            if user != risk.created_by and user != risk.assigned_to:
                return Response(
                    {"detail": "You do not have permission to update mitigation."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            allowed_data = request.data.copy()
            if "mitigation_plan" in allowed_data:
                allowed_data.pop("mitigation_plan")

        serializer = RiskMitigationUpdateSerializer(risk, data=allowed_data, partial=True)

        if serializer.is_valid():
            before = risk.mitigation_status
            serializer.save()
            after = risk.mitigation_status

            if pm_user and pm_user != user and before != after:
                create_notification(
                    pm_user,
                    "Mitigation Updated",
                    f"Mitigation progress updated for risk '{risk.title}' in '{risk.project.name}': {before} → {after}.",
                    redirect_url=url_risk_for(pm_user, risk.id),
                )

            create_notification(
                user,
                "Mitigation Saved",
                f"Mitigation updated for risk '{risk.title}'.",
                redirect_url=url_risk_for(user, risk.id),
            )

            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GlobalRiskListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RiskSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", None)

        queryset = Risk.objects.select_related("project", "assigned_to", "created_by")
        queryset = queryset.exclude(approval_status="rejected")
        queryset = queryset.filter(approval_status="approved")

        if role == "PM":
            queryset = queryset.filter(project__created_by=user)
        else:
            queryset = queryset.filter(Q(created_by=user) | Q(assigned_to=user))

        project_id = self.request.query_params.get("project")
        if project_id and str(project_id).isdigit():
            queryset = queryset.filter(project_id=int(project_id))

        risk_level = self.request.query_params.get("risk_level")
        status_param = self.request.query_params.get("status")
        mitigation_status = self.request.query_params.get("mitigation_status")

        if risk_level:
            queryset = queryset.filter(risk_level=risk_level)
        if status_param:
            queryset = queryset.filter(status=status_param)
        if mitigation_status:
            queryset = queryset.filter(mitigation_status=mitigation_status)

        return queryset.order_by("-created_at")


class MyRisksView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RiskSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Risk.objects.select_related("project", "assigned_to", "created_by")
        qs = qs.filter(Q(assigned_to=user) | Q(created_by=user)).order_by("-created_at")

        project_id = self.request.query_params.get("project")
        if project_id and str(project_id).isdigit():
            qs = qs.filter(project_id=int(project_id))
        return qs