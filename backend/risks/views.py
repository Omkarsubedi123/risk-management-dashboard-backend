from rest_framework import viewsets, permissions, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q

from .models import Risk
from .serializers import RiskSerializer, RiskMitigationUpdateSerializer


class RiskViewSet(viewsets.ModelViewSet):
    serializer_class = RiskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Risk.objects.select_related("project")

        if user.role == "PM":
            queryset = queryset.filter(created_by=user)
        else:
            queryset = queryset.filter(assigned_to=user)

        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class RiskMitigationUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        risk = get_object_or_404(Risk, pk=pk)
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

        # 🔹 Manual filters (THIS FIXES YOUR ISSUE)
        risk_level = self.request.query_params.get("risk_level")
        status = self.request.query_params.get("status")
        mitigation_status = self.request.query_params.get("mitigation_status")

        if risk_level:
            queryset = queryset.filter(risk_level=risk_level)

        if status:
            queryset = queryset.filter(status=status)

        if mitigation_status:
            queryset = queryset.filter(
                mitigation_status=mitigation_status
            )

        return queryset.order_by("-created_at")
