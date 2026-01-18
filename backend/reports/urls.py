from django.urls import path
from .views import PMRiskReportPDFView, PMReportFilterOptionsView

urlpatterns = [
    path("pm/risk-report/pdf/", PMRiskReportPDFView.as_view(), name="pm-risk-report-pdf"),
    path("pm/risk-report/options/", PMReportFilterOptionsView.as_view(), name="pm-risk-report-options"),
]
