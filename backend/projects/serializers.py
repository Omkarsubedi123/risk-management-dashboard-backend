# projects/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Project, ProjectTeam, Invite

User = get_user_model()


class ProjectTeamSerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = ProjectTeam
        fields = ("id", "user_id", "email", "username", "full_name", "role", "invited_at")

    def get_email(self, obj):
        return obj.user.email

    def get_username(self, obj):
        return obj.user.username or obj.user.email

    def get_full_name(self, obj):
        # Works even if full_name does not exist in User model
        if hasattr(obj.user, "get_full_name"):
            name = obj.user.get_full_name()
            if name:
                return name
        return obj.user.username or obj.user.email
   
class ProjectSerializer(serializers.ModelSerializer):
    team = ProjectTeamSerializer(source="team.all", many=True, read_only=True)
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        
        model = Project
        fields = "__all__"
        read_only_fields = ("created_by", "created_at", "updated_at")

    def get_created_by_email(self, obj):
        return obj.created_by.email


class InviteSerializer(serializers.ModelSerializer):
    invited_by_email = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Invite
        fields = (
            "id",
            "token",
            "email",
            "role",
            "accepted",
            "invited_by_email",
            "created_at",
        )
        read_only_fields = ("id", "token", "accepted", "invited_by_email", "created_at")

    def get_invited_by_email(self, obj):
        return obj.invited_by.email
    
# Team Member part form here 

class ProjectSummarySerializer(serializers.ModelSerializer):
    team_count = serializers.SerializerMethodField()
    pm_email = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "description",
            "sector",
            "status",
            "created_at",
            "updated_at",
            "team_count",
            "pm_email",
        )

    def get_team_count(self, obj):
        # you use ProjectTeam with related_name "team"
        return obj.team.count()

    def get_pm_email(self, obj):
        return obj.created_by.email if obj.created_by else ""

