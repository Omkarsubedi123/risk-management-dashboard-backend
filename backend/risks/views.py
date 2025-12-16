from rest_framework import viewsets, permissions
from .models import Risk
from .serializers import RiskSerializer

class RiskViewSet(viewsets.ModelViewSet):
    serializer_class = RiskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_id = self.request.query_params.get("project")
        queryset = Risk.objects.all()

        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset
