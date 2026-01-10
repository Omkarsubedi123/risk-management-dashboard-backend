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


class PMDashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _pm_only(request):
            return Response({"detail": "Unauthorized"}, status=403)

        user = request.user
        project_id = _get_project_id(request)

        # Base querysets
        projects_qs = Project.objects.filter(created_by=user)
        risks_qs = Risk.objects.filter(created_by=user)

        # Optional project filter
        if project_id:
            projects_qs = projects_qs.filter(id=project_id)
            risks_qs = risks_qs.filter(project_id=project_id)

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

        qs = Risk.objects.filter(created_by=user)

        if project_id:
            qs = qs.filter(project_id=project_id)

        qs = (
            qs.values("risk_level")
            .annotate(value=Count("id"))
            .order_by("risk_level")
        )

        data = [{"name": row["risk_level"], "value": row["value"]} for row in qs]
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

        qs = Risk.objects.filter(created_by=user)

        if project_id:
            qs = qs.filter(project_id=project_id)

        qs = (
            qs.annotate(month=TruncMonth("created_at"))
            .values("month", "risk_level")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        trend = {}
        for row in qs:
            if not row["month"]:
                continue

            month_label = row["month"].strftime("%b")  # Jan, Feb, etc.
            level = row["risk_level"]
            count = row["count"]

            if month_label not in trend:
                trend[month_label] = {"month": month_label}

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

        qs = Risk.objects.filter(created_by=user)
        if project_id:
            qs = qs.filter(project_id=project_id)

        # group by impact & probability
        agg = (
            qs.values("impact", "probability")
              .annotate(count=Count("id"))
        )

        # build 5x5 matrix
        # rows: impact 5->1 (top to bottom)
        # cols: probability 1->5 (left to right)
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