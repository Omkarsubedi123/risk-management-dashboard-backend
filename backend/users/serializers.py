# users/serializers.py
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
        user.save()

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
        return token

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Invalid email or password.")

        user = authenticate(request=self.context.get('request'), email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_verified:
            raise serializers.ValidationError("Email not verified. Please check your inbox.")

        data = super().validate(attrs)
        data['role'] = user.role
        data['username'] = user.username
        return data


class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # normalize email if you want: value = value.lower().strip()
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("No account found with this email.")
        return value

    def save(self):
        email = self.validated_data['email']
        user = User.objects.get(email=email)
        otp = str(random.randint(100000, 999999))

        # Assumes you have these methods on your CustomUser
        # set_otp should also set otp_expiry
        user.set_otp(otp)
        user.save()

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

        # Verify OTP (assumes CustomUser.verify_otp handles expiry)
        if not user.verify_otp(data['otp']):
            raise serializers.ValidationError({"otp": "Invalid or expired OTP"})

        if data['new_password'] != data['con_password']:
            raise serializers.ValidationError({"con_password": "Passwords do not match"})

        return data

    def save(self):
        user = User.objects.get(email=self.validated_data['email'])
        user.set_password(self.validated_data['new_password'])
        # Clear OTP state after successful reset
        user.otp_code = None
        user.otp_expiry = None
        user.save()
        return user
