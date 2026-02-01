from time import timezone
from rest_framework import viewsets, permissions, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.db.models import Q
from urllib3 import request

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

        # 🚨 IMPORTANT: hide rejected risks from normal APIs
        qs = qs.exclude(approval_status="rejected")

        if role == "PM":
            qs = qs.filter(project__created_by=user)
        else:
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

        # TM submits -> pending approval and notify PM
        if role == "TM":
            risk.approval_status = "pending"
            risk.save(update_fields=["approval_status"])

            pm_user = risk.project.created_by

            # Notify PM
            create_notification(
                pm_user,
                "New Risk Submitted",
                f"TM submitted risk '{risk.title}' in project '{risk.project.name}'."
            )

            # Notify TM (confirmation)
            create_notification(
                user,
                "Risk Submitted",
                f"Your risk '{risk.title}' was submitted for PM approval."
            )

        # PM creates -> approved
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
    # PM Approval Actions
    # =========================

    @action(detail=True, methods=["patch"], url_path="approve")
    def approve(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "PM":
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        # PM can only approve risks inside their projects
        if risk.project.created_by != user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        risk.approval_status = "approved"
        risk.approved_at = timezone.now()
        risk.save(update_fields=["approval_status", "approved_at"])

        # notify TM creator
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

        return Response({"message": "Risk approved."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"], url_path="reject")
    def reject(self, request, pk=None):
        risk = self.get_object()
        user = request.user

        if getattr(user, "role", None) != "PM":
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        if risk.project.created_by != user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        risk.approval_status = "rejected"
        risk.rejected_at = timezone.now()
        risk.save(update_fields=["approval_status", "rejected_at"])

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

        return Response({"message": "Risk rejected."}, status=status.HTTP_200_OK)


class RiskMitigationUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        risk = get_object_or_404(Risk.objects.select_related("project"), pk=pk)
        user = request.user

        if user != risk.created_by and user != risk.assigned_to:
            return Response(
                {"detail": "You do not have permission to update mitigation."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = RiskMitigationUpdateSerializer(risk, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()

            # ✅ Notify PM who owns the project
            pm_user = risk.project.created_by
            if pm_user and pm_user != user:
                create_notification(
                    pm_user,
                    "Mitigation Updated",
                    f"Mitigation updated for risk '{risk.title}' in '{risk.project.name}'."
                )

            # ✅ Also notify actor (optional)
            create_notification(
                user,
                "Mitigation Saved",
                f"Mitigation saved for risk '{risk.title}'."
            )

            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GlobalRiskListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RiskSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Risk.objects.select_related("project", "assigned_to")

        if not user.is_staff:
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

        # TM: assigned OR created by them
        qs = qs.filter(Q(assigned_to=user) | Q(created_by=user)).order_by("-created_at")

        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)

        return qs

