from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RiskViewSet,
    RiskMitigationUpdateView,
    GlobalRiskListView,
    MyRisksView,
)

router = DefaultRouter()
router.register(r"risks", RiskViewSet, basename="risk")

urlpatterns = [
    path("risks/my/", MyRisksView.as_view()),
    path(
        "risks/global/",
        GlobalRiskListView.as_view(),
        name="global-risk-list"
    ),
    path(
        "risks/<int:pk>/mitigation/",
        RiskMitigationUpdateView.as_view(),
        name="risk-mitigation-update"
    ),
    path("", include(router.urls)),
    
]
