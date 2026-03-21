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
        if hasattr(obj.user, "get_full_name"):
            name = obj.user.get_full_name()
            if name:
                return name
        return obj.user.username or obj.user.email


class ProjectSerializer(serializers.ModelSerializer):
    team = ProjectTeamSerializer(source="team.all", many=True, read_only=True)
    created_by_email = serializers.SerializerMethodField()
    pm_email = serializers.SerializerMethodField()
    team_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = ("created_by", "created_at", "updated_at")

    def get_created_by_email(self, obj):
        return obj.created_by.email if obj.created_by else ""

    def get_pm_email(self, obj):
        return obj.created_by.email if obj.created_by else ""

    def get_team_count(self, obj):
        return obj.team.count()


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
        return obj.team.count()

    def get_pm_email(self, obj):
        return obj.created_by.email if obj.created_by else ""


class AdminPMListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    project_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "full_name", "project_count")

    def get_full_name(self, obj):
        if hasattr(obj, "get_full_name"):
            name = obj.get_full_name()
            if name:
                return name
        return obj.username or obj.email

    def get_project_count(self, obj):
        return obj.projects.count()


class AdminTransferOwnershipSerializer(serializers.Serializer):
    from_pm_id = serializers.IntegerField()
    to_pm_id = serializers.IntegerField()

    def validate(self, attrs):
        from_pm_id = attrs.get("from_pm_id")
        to_pm_id = attrs.get("to_pm_id")

        if from_pm_id == to_pm_id:
            raise serializers.ValidationError("Source PM and target PM cannot be the same.")

        try:
            from_pm = User.objects.get(id=from_pm_id, role="PM", is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError({"from_pm_id": "Source Project Manager not found."})

        try:
            to_pm = User.objects.get(id=to_pm_id, role="PM", is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError({"to_pm_id": "Target Project Manager not found."})

        attrs["from_pm"] = from_pm
        attrs["to_pm"] = to_pm
        return attrs