from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import datetime


class CustomUser(AbstractUser):
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    email = models.EmailField(unique=True)

    ROLE_CHOICES = (
        ('PM', 'Project Manager'),
        ('TM', 'Team Member'),
        ('AD', 'Admin'),
    )
    role = models.CharField(max_length=2, choices=ROLE_CHOICES, default='TM')
    sector = models.CharField(max_length=100, blank=True, null=True)

    # Email verification / OTP
    is_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_expiry = models.DateTimeField(blank=True, null=True)

    # Password reset OTP
    reset_otp = models.CharField(max_length=6, blank=True, null=True)
    reset_otp_expires_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.email

    def set_otp(self, code):
        self.otp_code = code
        self.otp_expiry = timezone.now() + datetime.timedelta(minutes=5)
        self.save(update_fields=["otp_code", "otp_expiry"])

    def verify_otp(self, code):
        return (
            str(self.otp_code).strip() == str(code).strip()
            and self.otp_expiry
            and timezone.now() <= self.otp_expiry
        )