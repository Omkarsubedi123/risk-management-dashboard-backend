from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RiskViewSet, RiskMitigationUpdateView

router = DefaultRouter()
router.register(r"risks", RiskViewSet, basename="risk")

urlpatterns = [
    # 🔹 Custom endpoint FIRST
    path(
        "risks/<int:pk>/mitigation/",
        RiskMitigationUpdateView.as_view(),
        name="risk-mitigation-update"
    ),

    # 🔹 Router endpoints AFTER
    path("", include(router.urls)),
]
