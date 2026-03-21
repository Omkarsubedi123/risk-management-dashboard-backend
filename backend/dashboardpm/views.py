from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count
from django.db.models.functions import TruncMonth

from projects.models import Project
from risks.models import Risk


def _get_project_id(request):
    """
    Reads ?project=<id> from query params.
    Returns int project_id or None.
    """
    project_id = request.query_params.get("project")
    if project_id and str(project_id).isdigit():
        return int(project_id)
    return None


def _pm_only(request):
    """
    Simple PM role guard.
    """
    user = request.user
    return getattr(user, "role", None) == "PM"


def _pm_projects_queryset(user, project_id=None):
    qs = Project.objects.filter(created_by=user)
    if project_id:
        qs = qs.filter(id=project_id)
    return qs


def _pm_risks_queryset(user, project_id=None):
    """
    IMPORTANT:
    PM dashboard must show risks inside projects currently owned by the PM.
    Do NOT filter by risk.created_by, because after ownership transfer
    the new PM may not be the original creator of the risk.
    """
    qs = Risk.objects.filter(project__created_by=user).exclude(approval_status="rejected")
    if project_id:
        qs = qs.filter(project_id=project_id)
    return qs


class PMDashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _pm_only(request):
            return Response({"detail": "Unauthorized"}, status=403)

        user = request.user
        project_id = _get_project_id(request)

        projects_qs = _pm_projects_queryset(user, project_id)
        risks_qs = _pm_risks_queryset(user, project_id)

        data = {
            "total_projects": projects_qs.count(),
            "total_risks": risks_qs.count(),
            "high_risks": risks_qs.filter(risk_level="High").count(),
            "open_risks": risks_qs.exclude(status="Closed").count(),
        }

        return Response(data)


class PMRiskCategoryView(APIView):
    """
    Pie chart data: risks grouped by risk_level (High/Medium/Low)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _pm_only(request):
            return Response({"detail": "Unauthorized"}, status=403)

        user = request.user
        project_id = _get_project_id(request)

        qs = _pm_risks_queryset(user, project_id)

        qs = (
            qs.values("risk_level")
            .annotate(value=Count("id"))
            .order_by("risk_level")
        )

        data = [
            {"name": row["risk_level"], "value": row["value"]}
            for row in qs
            if row["risk_level"]
        ]
        return Response(data)


class PMRiskTrendView(APIView):
    """
    Line chart data: monthly risk trend grouped by risk_level.
    Output example:
    [
      {"month":"Jan", "High":2, "Medium":5},
      {"month":"Feb", "Low":1}
    ]
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _pm_only(request):
            return Response({"detail": "Unauthorized"}, status=403)

        user = request.user
        project_id = _get_project_id(request)

        qs = _pm_risks_queryset(user, project_id)

        qs = (
            qs.annotate(month=TruncMonth("created_at"))
            .values("month", "risk_level")
            .annotate(count=Count("id"))
            .order_by("month", "risk_level")
        )

        trend = {}
        for row in qs:
            month_value = row.get("month")
            level = row.get("risk_level")
            count = row.get("count", 0)

            if not month_value or not level:
                continue

            month_label = month_value.strftime("%b")

            if month_label not in trend:
                trend[month_label] = {"month": month_label, "Low": 0, "Medium": 0, "High": 0}

            trend[month_label][level] = count

        return Response(list(trend.values()))


class PMRiskHeatmapView(APIView):
    """
    Risk Matrix Heatmap: Impact (1-5) vs Probability (1-5)
    Cell value = number of risks in that (impact, probability) pair.
    Color will be handled on frontend using score = impact * probability.
    Supports ?project=<id>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _pm_only(request):
            return Response({"detail": "Unauthorized"}, status=403)

        user = request.user
        project_id = _get_project_id(request)

        qs = _pm_risks_queryset(user, project_id)

        agg = (
            qs.values("impact", "probability")
              .annotate(count=Count("id"))
              .order_by("impact", "probability")
        )

        matrix = [[0 for _ in range(5)] for _ in range(5)]

        for row in agg:
            impact = row.get("impact")
            prob = row.get("probability")
            count = row.get("count", 0)

            if impact in [1, 2, 3, 4, 5] and prob in [1, 2, 3, 4, 5]:
                r = 5 - impact
                c = prob - 1
                matrix[r][c] = count

        return Response({
            "x_labels": [1, 2, 3, 4, 5],   # Probability
            "y_labels": [5, 4, 3, 2, 1],   # Impact
            "matrix": matrix
        })