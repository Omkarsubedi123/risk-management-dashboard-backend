from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Risk
from .serializers import RiskSerializer, RiskMitigationUpdateSerializer


class RiskViewSet(viewsets.ModelViewSet):
    serializer_class = RiskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Risk.objects.all()

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
