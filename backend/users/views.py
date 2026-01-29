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
)
from .models import CustomUser


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


# ==========================
# ✅ PROFILE: GET/PATCH /me/
# ==========================
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


# =================================
# ✅ CHANGE PASSWORD: POST /change-password/
# =================================
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
