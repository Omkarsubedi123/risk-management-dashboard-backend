from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    SignupView,
    VerifyOTPView,
    CustomTokenObtainPairView,
    RequestPasswordResetView,
    ConfirmResetPasswordView,
    MeView,
    ChangePasswordView,
    AdminDashboardView,
    AdminUsersListView,
    AdminDeactivatePMView,
    AdminDeletePMView,
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('password/reset/', RequestPasswordResetView.as_view(), name='password-reset'),
    path('password/reset/confirm/', ConfirmResetPasswordView.as_view(), name='password-reset-confirm'),

    path("me/", MeView.as_view(), name="me"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),

    path("admin/dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("admin/users/", AdminUsersListView.as_view(), name="admin-users"),
    path("admin/deactivate-pm/", AdminDeactivatePMView.as_view(), name="admin-deactivate-pm"),
    path("admin/delete-pm/", AdminDeletePMView.as_view(), name="admin-delete-pm"),
]