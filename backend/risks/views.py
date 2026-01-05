from rest_framework import viewsets, permissions, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q

from notifications.utils import create_notification
from projects.models import Project

from .models import Risk
from .serializers import RiskSerializer, RiskMitigationUpdateSerializer


class RiskViewSet(viewsets.ModelViewSet):
    serializer_class = RiskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Risk.objects.select_related("project")

        if getattr(user, "role", None) == "PM":
            queryset = queryset.filter(created_by=user)
        else:
            queryset = queryset.filter(assigned_to=user)

        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset.order_by("-created_at")

    # ✅ Risk Created Notification
    def perform_create(self, serializer):
        risk = serializer.save(created_by=self.request.user)

        # Project is available via risk.project
        create_notification(
            self.request.user,
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

    # ✅ Risk Deleted Notification
    def perform_destroy(self, instance):
        project_name = instance.project.name
        instance.delete()

        create_notification(
            self.request.user,
            "Risk Deleted",
            f"A risk was removed from project '{project_name}'."
        )


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

        serializer = RiskMitigationUpdateSerializer(
            risk, data=request.data, partial=True
        )

        if serializer.is_valid():
            serializer.save()

            # ✅ Mitigation Updated Notification (PM side)
            create_notification(
                request.user,
                "Risk Mitigation Updated",
                f"Mitigation was updated for a risk in '{risk.project.name}'."
            )

            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GlobalRiskListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RiskSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Risk.objects.select_related("project", "assigned_to")

        # 🔹 Permission logic
        if not user.is_staff:
            queryset = queryset.filter(
                Q(created_by=user) | Q(assigned_to=user)
            )

        # 🔹 Manual filters
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
