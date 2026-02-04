from django.utils import timezone
from rest_framework import viewsets, permissions, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.db.models import Q

from notifications.utils import create_notification
from .models import Risk
from .serializers import RiskSerializer, RiskMitigationUpdateSerializer


class RiskViewSet(viewsets.ModelViewSet):
    serializer_class = RiskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Risk.objects.select_related("project", "assigned_to", "created_by")
        role = getattr(user, "role", None)

        # ✅ Hide rejected risks from normal APIs
        qs = qs.exclude(approval_status="rejected")

        # ✅ PM sees all risks inside their projects (including TM created)
        if role == "PM":
            qs = qs.filter(project__created_by=user)
        else:
            # ✅ TM sees assigned + created
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

    # ✅ Risk Created Notification + approval workflow
    def perform_create(self, serializer):
        user = self.request.user
        role = getattr(user, "role", None)

        risk = serializer.save(created_by=user)

        if role == "TM":
            risk.approval_status = "pending"
            risk.save(update_fields=["approval_status"])

            pm_user = risk.project.created_by

            create_notification(
                pm_user,
                "New Risk Submitted",
                f"TM submitted risk '{risk.title}' in project '{risk.project.name}'."
            )

            create_notification(
                user,
                "Risk Submitted",
                f"Your risk '{risk.title}' was submitted for PM approval."
            )
        else:
            risk.approval_status = "approved"
            risk.save(update_fields=["approval_status"])

            create_notification(
                user,
                "Risk Created",
                f"A new risk was added to project '{risk.project.name}'."
            )

    # ✅ Risk Updated Notification
    def perform_update(self, serializer):
        risk = serializer.save()

        create_notification(
            self.request.user,
            "Risk Updated",
            f"A risk in project '{risk.project.name}' was updated."
        )

    # ✅ TM cannot delete risks
    def destroy(self, request, *args, **kwargs):
        role = getattr(request.user, "role", None)
        if role != "PM":
            return Response(
                {"detail": "Team Members cannot delete risks."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    # ✅ Risk Deleted Notification (PM only)
    def perform_destroy(self, instance):
        project_name = instance.project.name
        instance.delete()

        create_notification(
            self.request.user,
            "Risk Deleted",
            f"A risk was removed from project '{project_name}'."
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
                f"Your risk '{risk.title}' was approved by the Project Manager."
            )

        create_notification(
            user,
            "Risk Approved",
            f"You approved risk '{risk.title}' in '{risk.project.name}'."
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
                f"Your risk '{risk.title}' was rejected by the Project Manager."
            )

        create_notification(
            user,
            "Risk Rejected",
            f"You rejected risk '{risk.title}' in '{risk.project.name}'."
        )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)

    # ==========================================================
    # ✅ TM → Suggest Mitigation (does NOT overwrite PM plan)
    # URL: PATCH /api/risks/<id>/suggest-mitigation/
    # ==========================================================
    @action(detail=True, methods=["patch"], url_path="suggest-mitigation")
    def suggest_mitigation(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "TM":
            return Response(
                {"detail": "Only Team Members can suggest mitigation."},
                status=status.HTTP_403_FORBIDDEN
            )

        if user != risk.created_by and user != risk.assigned_to:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if (risk.approval_status or "").lower() != "approved":
            return Response(
                {"detail": "You can suggest mitigation only after risk is approved."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ✅ Accept multiple possible frontend keys safely (prevents “Suggestion is required” bug)
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

        needed_fields = ["tm_mitigation_suggestion", "tm_suggestion_status"]
        for f in needed_fields:
            if not hasattr(risk, f):
                return Response(
                    {"detail": f"Backend model missing field '{f}'. Add it in Risk model & migrate."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        risk.tm_mitigation_suggestion = suggestion
        risk.tm_suggestion_status = "pending"

        if hasattr(risk, "tm_suggested_at"):
            risk.tm_suggested_at = timezone.now()
        if hasattr(risk, "tm_suggested_by"):
            risk.tm_suggested_by = user

        update_fields = ["tm_mitigation_suggestion", "tm_suggestion_status"]
        if hasattr(risk, "tm_suggested_at"):
            update_fields.append("tm_suggested_at")
        if hasattr(risk, "tm_suggested_by"):
            update_fields.append("tm_suggested_by")

        risk.save(update_fields=update_fields)

        pm_user = risk.project.created_by
        if pm_user:
            create_notification(
                pm_user,
                "Mitigation Suggested",
                f"TM suggested mitigation for risk '{risk.title}' in '{risk.project.name}'."
            )

        create_notification(
            user,
            "Suggestion Submitted",
            f"Your mitigation suggestion for '{risk.title}' was sent to the PM."
        )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)

    # ==========================================================
    # ✅ PM → Approve & Apply Suggestion
    # URL: PATCH /api/risks/<id>/approve-suggestion/
    # ==========================================================
    @action(detail=True, methods=["patch"], url_path="approve-suggestion")
    def approve_suggestion(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "PM":
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if risk.project.created_by != user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(risk, "tm_suggestion_status") or not hasattr(risk, "tm_mitigation_suggestion"):
            return Response(
                {"detail": "Backend model missing mitigation suggestion fields. Add them & migrate."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if (risk.tm_suggestion_status or "").lower() != "pending":
            return Response({"detail": "No pending suggestion to approve."}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Apply suggestion to PM plan
        risk.mitigation_plan = risk.tm_mitigation_suggestion

        new_status = request.data.get("mitigation_status")
        if new_status in ["NotStarted", "InProgress", "Completed"]:
            risk.mitigation_status = new_status

        risk.tm_suggestion_status = "approved"

        if hasattr(risk, "tm_reviewed_at"):
            risk.tm_reviewed_at = timezone.now()
        if hasattr(risk, "tm_reviewed_by"):
            risk.tm_reviewed_by = user

        update_fields = ["mitigation_plan", "tm_suggestion_status"]
        if new_status in ["NotStarted", "InProgress", "Completed"]:
            update_fields.append("mitigation_status")
        if hasattr(risk, "tm_reviewed_at"):
            update_fields.append("tm_reviewed_at")
        if hasattr(risk, "tm_reviewed_by"):
            update_fields.append("tm_reviewed_by")

        risk.save(update_fields=list(set(update_fields)))

        tm_user = getattr(risk, "tm_suggested_by", None) or risk.created_by
        if tm_user:
            create_notification(
                tm_user,
                "Suggestion Approved",
                f"Your mitigation suggestion for '{risk.title}' was approved and applied by the PM."
            )

        create_notification(
            user,
            "Suggestion Applied",
            f"You approved and applied mitigation suggestion for '{risk.title}'."
        )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)

    # ==========================================================
    # ✅ PM → Reject Suggestion
    # URL: PATCH /api/risks/<id>/reject-suggestion/
    # ==========================================================
    @action(detail=True, methods=["patch"], url_path="reject-suggestion")
    def reject_suggestion(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "PM":
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if risk.project.created_by != user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(risk, "tm_suggestion_status"):
            return Response(
                {"detail": "Backend model missing 'tm_suggestion_status'. Add it & migrate."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if (risk.tm_suggestion_status or "").lower() != "pending":
            return Response({"detail": "No pending suggestion to reject."}, status=status.HTTP_400_BAD_REQUEST)

        risk.tm_suggestion_status = "rejected"
        if hasattr(risk, "tm_reviewed_at"):
            risk.tm_reviewed_at = timezone.now()
        if hasattr(risk, "tm_reviewed_by"):
            risk.tm_reviewed_by = user

        update_fields = ["tm_suggestion_status"]
        if hasattr(risk, "tm_reviewed_at"):
            update_fields.append("tm_reviewed_at")
        if hasattr(risk, "tm_reviewed_by"):
            update_fields.append("tm_reviewed_by")

        risk.save(update_fields=update_fields)

        tm_user = getattr(risk, "tm_suggested_by", None) or risk.created_by
        if tm_user:
            create_notification(
                tm_user,
                "Suggestion Rejected",
                f"Your mitigation suggestion for '{risk.title}' was rejected by the PM."
            )

        create_notification(
            user,
            "Suggestion Rejected",
            f"You rejected mitigation suggestion for '{risk.title}'."
        )

        return Response(RiskSerializer(risk).data, status=status.HTTP_200_OK)


class RiskMitigationUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        """
        ✅ NEW RULE (no collisions):
        - PM (project owner) can update mitigation_plan + mitigation_status
        - TM can update ONLY mitigation_status (progress), NOT the plan
        """
        risk = get_object_or_404(Risk.objects.select_related("project"), pk=pk)
        user = request.user
        role = getattr(user, "role", None)

        pm_user = risk.project.created_by

        # PM can update if owns project
        if role == "PM" and pm_user == user:
            allowed_data = request.data.copy()
        else:
            # TM must be involved
            if user != risk.created_by and user != risk.assigned_to:
                return Response(
                    {"detail": "You do not have permission to update mitigation."},
                    status=status.HTTP_403_FORBIDDEN
                )

            allowed_data = request.data.copy()
            # TM cannot change mitigation_plan (only status)
            if "mitigation_plan" in allowed_data:
                allowed_data.pop("mitigation_plan")

        serializer = RiskMitigationUpdateSerializer(risk, data=allowed_data, partial=True)

        if serializer.is_valid():
            serializer.save()

            if pm_user and pm_user != user:
                create_notification(
                    pm_user,
                    "Mitigation Updated",
                    f"Mitigation progress updated for risk '{risk.title}' in '{risk.project.name}'."
                )

            create_notification(
                user,
                "Mitigation Saved",
                f"Mitigation updated for risk '{risk.title}'."
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

        #  Always hide rejected from global
        queryset = queryset.exclude(approval_status="rejected")

        #  Only show approved items in Global Risk Register
        queryset = queryset.filter(approval_status="approved")

        #  PM should see ALL approved risks inside their projects (including TM created)
        if role == "PM":
            queryset = queryset.filter(project__created_by=user)
        else:
            #  TM (and others) see only what they created or assigned
            queryset = queryset.filter(Q(created_by=user) | Q(assigned_to=user))

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
