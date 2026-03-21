from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser

    list_display = [
        'id',
        'username',
        'email',
        'role',
        'is_verified',
        'is_active',
        'is_staff',
        'is_superuser',
    ]
    list_filter = [
        'role',
        'is_verified',
        'is_active',
        'is_staff',
        'is_superuser',
    ]

    fieldsets = (
        (None, {'fields': ('username', 'email', 'password', 'role', 'sector')}),
        ('Verification', {'fields': ('is_verified', 'otp_code', 'otp_expiry')}),
        ('Password Reset OTP', {'fields': ('reset_otp', 'reset_otp_expires_at')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username',
                'email',
                'password1',
                'password2',
                'role',
                'sector',
                'is_verified',
                'is_active',
                'is_staff',
                'is_superuser',
            )
        }),
    )

    search_fields = ('email', 'username')
    ordering = ('email',)