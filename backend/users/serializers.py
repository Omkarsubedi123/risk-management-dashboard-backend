from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.core.mail import send_mail
from django.conf import settings
from .models import CustomUser
import random

User = get_user_model()


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    conf_password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'conf_password', 'role']

    def validate(self, data):
        if data['password'] != data['conf_password']:
            raise serializers.ValidationError({"conf_password": "Passwords do not match."})

        if CustomUser.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError({"email": "Email already exists."})

        if data.get("role") == "AD":
            raise serializers.ValidationError({"role": "Admin account cannot be created through public signup."})

        return data

    def create(self, validated_data):
        validated_data.pop('conf_password')
        user = CustomUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', 'TM'),
            is_verified=False
        )

        otp_code = str(random.randint(100000, 999999))
        user.otp_code = otp_code
        user.save(update_fields=["otp_code"])

        send_mail(
            subject="Verify your email",
            message=f"Your OTP code is: {otp_code}",
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['role'] = user.role
        token['user_id'] = user.id
        token['email'] = user.email
        return token

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated. Please contact admin.")

        user = authenticate(request=self.context.get('request'), email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_verified:
            raise serializers.ValidationError("Email not verified. Please check your inbox.")

        data = super().validate(attrs)
        data['role'] = user.role
        data['username'] = user.username
        data['user_id'] = user.id
        data['email'] = user.email
        return data


class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("No account found with this email.")

        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated. Please contact admin.")

        return value

    def save(self):
        email = self.validated_data['email']
        user = User.objects.get(email=email)
        otp = str(random.randint(100000, 999999))

        user.set_otp(otp)

        send_mail(
            subject="Password Reset Request",
            message=f"Your OTP code is {otp}. It will expire in 5 minutes.",
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[email],
            fail_silently=False
        )
        return user


class ConfirmResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    con_password = serializers.CharField(write_only=True)

    def validate(self, data):
        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid email"})

        if not user.is_active:
            raise serializers.ValidationError({"email": "This account has been deactivated. Please contact admin."})

        if not user.verify_otp(data['otp']):
            raise serializers.ValidationError({"otp": "Invalid or expired OTP"})

        if data['new_password'] != data['con_password']:
            raise serializers.ValidationError({"con_password": "Passwords do not match"})

        return data

    def save(self):
        user = User.objects.get(email=self.validated_data['email'])
        user.set_password(self.validated_data['new_password'])
        user.otp_code = None
        user.otp_expiry = None
        user.save(update_fields=["password", "otp_code", "otp_expiry"])
        return user


class AdminUserListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "role",
            "is_active",
            "is_verified",
            "full_name",
            "date_joined",
        ]

    def get_full_name(self, obj):
        full_name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return full_name if full_name else (obj.username or obj.email)


class AdminDashboardSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    total_pms = serializers.IntegerField()
    total_tms = serializers.IntegerField()
    total_admins = serializers.IntegerField()
    verified_users = serializers.IntegerField()
    unverified_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    inactive_users = serializers.IntegerField()


class AdminDeactivatePMSerializer(serializers.Serializer):
    pm_id = serializers.IntegerField()

    def validate(self, attrs):
        pm_id = attrs.get("pm_id")

        try:
            pm = User.objects.get(id=pm_id, role="PM")
        except User.DoesNotExist:
            raise serializers.ValidationError({"pm_id": "Project Manager not found."})

        if not pm.is_active:
            raise serializers.ValidationError({"pm_id": "This PM account is already deactivated."})

        owned_projects_count = pm.projects.count()
        if owned_projects_count > 0:
            raise serializers.ValidationError({
                "pm_id": f"This PM still owns {owned_projects_count} project(s). Transfer ownership first."
            })

        attrs["pm"] = pm
        return attrs


class AdminDeletePMSerializer(serializers.Serializer):
    pm_id = serializers.IntegerField()

    def validate(self, attrs):
        pm_id = attrs.get("pm_id")

        try:
            pm = User.objects.get(id=pm_id, role="PM")
        except User.DoesNotExist:
            raise serializers.ValidationError({"pm_id": "Project Manager not found."})

        if pm.is_active:
            raise serializers.ValidationError({
                "pm_id": "Deactivate this PM account before deleting it."
            })

        owned_projects_count = pm.projects.count()
        if owned_projects_count > 0:
            raise serializers.ValidationError({
                "pm_id": f"This PM still owns {owned_projects_count} project(s). Transfer ownership first."
            })

        attrs["pm"] = pm
        return attrs