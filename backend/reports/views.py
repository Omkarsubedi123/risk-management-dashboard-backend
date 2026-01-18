from io import BytesIO
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncMonth
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart

from projects.models import Project
from risks.models import Risk


# === Severity colors ===
COL_HIGH = colors.HexColor("#ef4444")   # red
COL_MED  = colors.HexColor("#d97706")   # dark yellow
COL_LOW  = colors.HexColor("#16a34a")   # green


def _pm_only(user):
    return getattr(user, "role", None) == "PM"


def _safe(v, dash="—"):
    if v is None:
        return dash
    s = str(v).strip()
    return s if s else dash


def _risk_score(r):
    try:
        if getattr(r, "risk_score", None) not in (None, ""):
            return int(r.risk_score)
    except:
        pass
    try:
        p = int(getattr(r, "probability", 0) or 0)
        i = int(getattr(r, "impact", 0) or 0)
        return p * i
    except:
        return 0


def _make_donut_severity(title, labels, values):
    d = Drawing(240, 160)
    d.add(String(0, 145, title, fontSize=11, fillColor=colors.HexColor("#0f172a")))

    pie = Pie()
    pie.x = 55
    pie.y = 20
    pie.width = 115
    pie.height = 115
    pie.data = values if values else [1]
    pie.labels = labels if labels else ["No data"]
    pie.slices.strokeWidth = 0.6
    pie.slices.strokeColor = colors.white
    pie.sideLabels = True
    pie.simpleLabels = False

    mapping = {"High": COL_HIGH, "Medium": COL_MED, "Low": COL_LOW}
    for i, lab in enumerate(pie.labels):
        pie.slices[i].fillColor = mapping.get(str(lab), colors.HexColor("#64748b"))

    d.add(pie)
    return d


def _make_bar_severity(title, categories, values):
    # 3 series so each bar can have its own color
    d = Drawing(320, 180)
    d.add(String(0, 165, title, fontSize=11, fillColor=colors.HexColor("#0f172a")))

    bc = VerticalBarChart()
    bc.x = 35
    bc.y = 25
    bc.height = 120
    bc.width = 270

    v0 = values[0] if values else 0
    v1 = values[1] if values else 0
    v2 = values[2] if values else 0

    bc.data = [[v0, 0, 0], [0, v1, 0], [0, 0, v2]]
    bc.categoryAxis.categoryNames = categories if categories else ["High", "Medium", "Low"]

    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = (max(values) + 2) if values else 5
    bc.valueAxis.valueStep = 1

    bc.barWidth = 22
    bc.groupSpacing = 12
    bc.barSpacing = 6

    bc.bars[0].fillColor = COL_HIGH
    bc.bars[1].fillColor = COL_MED
    bc.bars[2].fillColor = COL_LOW

    d.add(bc)
    return d


def _make_trend_multiline(title, month_labels, high_vals, med_vals, low_vals):
    d = Drawing(320, 180)
    d.add(String(0, 165, title, fontSize=11, fillColor=colors.HexColor("#0f172a")))

    if not month_labels or len(month_labels) < 2:
        month_labels = ["Dec", "Jan"]
        high_vals = high_vals or [0, 0]
        med_vals = med_vals or [0, 0]
        low_vals = low_vals or [0, 0]

    max_y = max([0] + high_vals + med_vals + low_vals) + 1

    lc = HorizontalLineChart()
    lc.x = 40
    lc.y = 30
    lc.height = 110
    lc.width = 260
    lc.data = [high_vals, med_vals, low_vals]
    lc.joinedLines = 1

    # thick visible lines
    lc.lines[0].strokeColor = COL_HIGH
    lc.lines[0].strokeWidth = 3
    lc.lines[1].strokeColor = COL_MED
    lc.lines[1].strokeWidth = 3
    lc.lines[2].strokeColor = COL_LOW
    lc.lines[2].strokeWidth = 3

    lc.categoryAxis.categoryNames = month_labels
    lc.valueAxis.valueMin = 0
    lc.valueAxis.valueMax = max_y
    lc.valueAxis.valueStep = 1

    d.add(lc)

    # legend-like labels
    d.add(String(45, 12, "High", fontSize=9, fillColor=COL_HIGH))
    d.add(String(95, 12, "Medium", fontSize=9, fillColor=COL_MED))
    d.add(String(160, 12, "Low", fontSize=9, fillColor=COL_LOW))

    return d


class PMReportFilterOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not _pm_only(user):
            return Response({"detail": "Unauthorized"}, status=403)

        projects = Project.objects.filter(created_by=user).values("id", "name").order_by("-id")
        risks_qs = Risk.objects.filter(project__created_by=user)

        statuses = list(
            risks_qs.exclude(status__isnull=True)
                    .exclude(status__exact="")
                    .values_list("status", flat=True)
                    .distinct()
                    .order_by("status")
        )

        mitigation_statuses = list(
            risks_qs.exclude(mitigation_status__isnull=True)
                    .exclude(mitigation_status__exact="")
                    .values_list("mitigation_status", flat=True)
                    .distinct()
                    .order_by("mitigation_status")
        )

        return Response({
            "projects": list(projects),
            "risk_levels": ["High", "Medium", "Low"],
            "statuses": statuses,
            "mitigation_statuses": mitigation_statuses,
        })


class PMRiskReportPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not _pm_only(user):
            return Response({"detail": "Unauthorized"}, status=403)

        project_param = request.query_params.get("project", "all")
        risk_level = request.query_params.get("risk_level") or ""
        status_param = request.query_params.get("status") or ""
        mitigation_status = request.query_params.get("mitigation_status") or ""

        projects_qs = Project.objects.filter(created_by=user).order_by("-created_at")

        selected_project = None
        if project_param != "all":
            try:
                pid = int(project_param)
                selected_project = projects_qs.filter(id=pid).first()
                if not selected_project:
                    return Response({"detail": "Project not found."}, status=404)
                projects_qs = projects_qs.filter(id=pid)
            except ValueError:
                return Response({"detail": "Invalid project id."}, status=400)

        risks_qs = Risk.objects.filter(project__in=projects_qs).select_related("project", "assigned_to")

        if risk_level:
            risks_qs = risks_qs.filter(risk_level__iexact=risk_level)

        if status_param:
            if status_param.lower() == "open":
                risks_qs = risks_qs.exclude(status__iexact="Closed")
            else:
                risks_qs = risks_qs.filter(status__iexact=status_param)

        if mitigation_status:
            risks_qs = risks_qs.filter(mitigation_status__iexact=mitigation_status)

        risks_qs = risks_qs.order_by("-created_at")

        total = risks_qs.count()
        open_count = risks_qs.exclude(status__iexact="Closed").count()
        closed_count = risks_qs.filter(status__iexact="Closed").count()

        high = risks_qs.filter(risk_level__iexact="High").count()
        med = risks_qs.filter(risk_level__iexact="Medium").count()
        low = risks_qs.filter(risk_level__iexact="Low").count()

        # trend by month + level
        trend_qs = (
            risks_qs.annotate(m=TruncMonth("created_at"))
            .values("m", "risk_level")
            .annotate(c=Count("id"))
            .order_by("m")
        )

        month_order = []
        tmp = {}
        for row in trend_qs:
            if not row["m"]:
                continue
            mlabel = row["m"].strftime("%b")
            if mlabel not in tmp:
                tmp[mlabel] = {"High": 0, "Medium": 0, "Low": 0}
                month_order.append(mlabel)
            lvl = (row["risk_level"] or "").capitalize()
            if lvl in tmp[mlabel]:
                tmp[mlabel][lvl] = row["c"]

        if len(month_order) < 2:
            month_order = month_order or ["Dec", "Jan"]
            for m in month_order:
                tmp.setdefault(m, {"High": 0, "Medium": 0, "Low": 0})

        high_vals = [tmp[m]["High"] for m in month_order]
        med_vals = [tmp[m]["Medium"] for m in month_order]
        low_vals = [tmp[m]["Low"] for m in month_order]

        # Key risks
        risks_list = list(risks_qs[:600])
        risks_list.sort(key=_risk_score, reverse=True)
        key_risks = risks_list[:8]

        prepared_by = (
            user.get_full_name().strip()
            if hasattr(user, "get_full_name") and user.get_full_name()
            else _safe(getattr(user, "username", None), dash=_safe(user.email))
        )

        now = timezone.now().strftime("%Y-%m-%d %H:%M")
        scope_title = selected_project.name if selected_project else "All Projects"

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=28, rightMargin=28, topMargin=24, bottomMargin=24)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"<font color='#0f766e'><b>{_safe(scope_title)}</b></font>", styles["Heading2"]))
        story.append(Paragraph("<b>Risk Overview Report</b>", styles["Title"]))
        story.append(Spacer(1, 6))

        hdr = Table(
            [["Generated on", now], ["Prepared by", prepared_by], ["Generated for", _safe(user.email)]],
            colWidths=[110, 360],
        )
        hdr.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(hdr)
        story.append(Spacer(1, 10))

        # Filters (line-break / bullet style)
        story.append(Paragraph("<b>Filters</b>", styles["Heading3"]))
        story.append(Paragraph(f"• Risk Level: <b>{_safe(risk_level, 'Any')}</b>", styles["Normal"]))
        story.append(Paragraph(f"• Status: <b>{_safe(status_param, 'Any')}</b>", styles["Normal"]))
        story.append(Paragraph(f"• Mitigation Status: <b>{_safe(mitigation_status, 'Any')}</b>", styles["Normal"]))
        story.append(Spacer(1, 14))

        story.append(Paragraph("<b>Summary</b>", styles["Heading2"]))
        story.append(Spacer(1, 8))

        summary = Table(
            [
                ["Total Risks", total],
                ["Open", open_count],
                ["Closed", closed_count],
                ["High Severity", high],
                ["Medium Severity", med],
                ["Low Severity", low],
            ],
            colWidths=[240, 90],
        )
        summary.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))

        # donut = _make_donut_severity("Risks by Level", ["High", "Medium", "Low"], [high, med, low])
        # bar = _make_bar_severity("Risks by Severity", ["High", "Medium", "Low"], [high, med, low])
        # trend = _make_trend_multiline("Risk Trend Over Time", month_order, high_vals, med_vals, low_vals)

        # # Layout: donut on right, bar+trend on left
        # left_charts = Table([[bar], [Spacer(1, 8)], [trend]], colWidths=[320])
        # left_charts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

        # right_charts = Table([[donut]], colWidths=[240])
        # right_charts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

        # top_block = Table(
        #     [[summary, right_charts],
        #      [left_charts, ""]],
        #     colWidths=[340, 240],
        # )
        # top_block.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        # story.append(top_block)
        donut = _make_donut_severity("Risks by Level", ["High", "Medium", "Low"], [high, med, low])
        bar = _make_bar_severity("Risks by Severity", ["High", "Medium", "Low"], [high, med, low])
        trend = _make_trend_multiline("Risk Trend Over Time", month_order, high_vals, med_vals, low_vals)

        # -- NEW: compact 2x2 layout so page 1 never looks empty ---
        # Summary full width
        story.append(summary)
        story.append(Spacer(1, 12))

        # Charts row: donut + bar side-by-side
        charts_row = Table(
            [[donut, bar]],
            colWidths=[250, 330],
        )
        charts_row.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ])
        )
        story.append(charts_row)
        story.append(Spacer(1, 10))

        # Trend full width under them
        trend_row = Table([[trend]], colWidths=[580])
        trend_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(trend_row)

        story.append(Spacer(1, 14))

        story.append(Spacer(1, 14))

        story.append(Paragraph("<b>Key Risks</b>", styles["Heading2"]))
        story.append(Spacer(1, 8))

        rows = [["Risk Title", "Score", "Severity", "Status", "Assigned To"]]
        for r in key_risks:
            assigned = "Unassigned"
            if getattr(r, "assigned_to", None):
                assigned = _safe(getattr(r.assigned_to, "email", None), dash=_safe(getattr(r.assigned_to, "username", None)))
            rows.append([_safe(r.title), _risk_score(r), _safe(r.risk_level), _safe(r.status), assigned])

        t = Table(rows, repeatRows=1, colWidths=[250, 55, 70, 75, 110])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))
        story.append(t)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        filename = "risk_overview_report.pdf" if not selected_project else f"risk_overview_project_{selected_project.id}.pdf"
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
