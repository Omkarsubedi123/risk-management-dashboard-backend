from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .serializers import (
    SignupSerializer,
    CustomTokenObtainPairSerializer,
    RequestPasswordResetSerializer,
    ConfirmResetPasswordSerializer,
    AdminUserListSerializer,
    AdminDashboardSerializer,
)
from .models import CustomUser
from .permissions import IsAdminRole
from django.db.models import Q

class SignupView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = SignupSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            "message": "User registered successfully. Please verify your email.",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role
            }
        }, status=status.HTTP_201_CREATED)


class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp_code = request.data.get("otp_code")

        if not email or not otp_code:
            return Response({"error": "Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        if str(user.otp_code).strip() == str(otp_code).strip():
            user.is_verified = True
            user.is_active = True
            user.otp_code = None
            user.save()
            return Response({"message": "Email verified successfully"}, status=status.HTTP_200_OK)

        return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


class RequestPasswordResetView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RequestPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Password reset OTP sent."}, status=status.HTTP_200_OK)


class ConfirmResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ConfirmResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Password reset successfully."}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response({
            "id": u.id,
            "email": u.email,
            "username": getattr(u, "username", "") or "",
            "first_name": getattr(u, "first_name", "") or "",
            "last_name": getattr(u, "last_name", "") or "",
            "role": getattr(u, "role", "") or "",
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        u = request.user
        data = request.data or {}

        if "username" in data:
            u.username = (data.get("username") or "").strip()

        if "first_name" in data:
            u.first_name = (data.get("first_name") or "").strip()

        if "last_name" in data:
            u.last_name = (data.get("last_name") or "").strip()

        u.save(update_fields=["username", "first_name", "last_name"])
        return Response({"detail": "Profile updated successfully."}, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        u = request.user

        current_password = request.data.get("current_password", "")
        new_password = request.data.get("new_password", "")
        confirm_password = request.data.get("confirm_password", "")

        if not u.check_password(current_password):
            return Response({"detail": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({"detail": "New password and confirm password do not match."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(new_password, user=u)
        except ValidationError as e:
            return Response({"detail": " ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        u.set_password(new_password)
        u.save()
        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)



# ADMIN MODULE - BACKEND

class AdminDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request):
        data = {
            "total_users": CustomUser.objects.count(),
            "total_pms": CustomUser.objects.filter(role="PM").count(),
            "total_tms": CustomUser.objects.filter(role="TM").count(),
            "total_admins": CustomUser.objects.filter(role="AD").count(),
            "verified_users": CustomUser.objects.filter(is_verified=True).count(),
            "unverified_users": CustomUser.objects.filter(is_verified=False).count(),
            "active_users": CustomUser.objects.filter(is_active=True).count(),
            "inactive_users": CustomUser.objects.filter(is_active=False).count(),
        }

        serializer = AdminDashboardSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminUsersListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request):
        role = request.query_params.get("role")
        search = request.query_params.get("search", "").strip()

        users = CustomUser.objects.all().order_by("-date_joined")

        if role in ["PM", "TM", "AD"]:
            users = users.filter(role=role)

        if search:
            users = users.filter(
                Q(email__icontains=search) |
                Q(username__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )

        serializer = AdminUserListSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)