from django.urls import path
from .views import (
    PMDashboardSummaryView,
    PMRiskCategoryView,
    PMRiskHeatmapView,
    PMRiskTrendView,
)

urlpatterns = [
    path("pm/summary/", PMDashboardSummaryView.as_view(), name="pm-dashboard-summary"),
    path("pm/risk-category/", PMRiskCategoryView.as_view(), name="pm-risk-category"),
    path("pm/risk-trend/", PMRiskTrendView.as_view(), name="pm-risk-trend"),
    path("pm/heatmap/", PMRiskHeatmapView.as_view(), name="pm-risk-heatmap"),
]