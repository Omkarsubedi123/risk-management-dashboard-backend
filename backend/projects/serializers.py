# projects/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Project, ProjectTeam, Invite

User = get_user_model()


class ProjectTeamSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = ProjectTeam
        fields = ("id", "user_id", "user_email", "role", "invited_at")

    def get_user_email(self, obj):
        return obj.user.email


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
