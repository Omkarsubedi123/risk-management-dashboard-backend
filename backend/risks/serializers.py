from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Risk

User = get_user_model()


class RiskSerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source="created_by.id")

    project_name = serializers.CharField(source="project.name", read_only=True)
    project_id = serializers.IntegerField(source="project.id", read_only=True)

    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Risk
        fields = "__all__"
        read_only_fields = (
            "created_by",
            "risk_score",
            "likelihood",
            "risk_level",
            "created_at",
            "updated_at",
        )

    def get_assigned_to_name(self, obj):
        if not obj.assigned_to:
            return ""
        return obj.assigned_to.get_full_name() or obj.assigned_to.username or obj.assigned_to.email

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return ""
        return obj.created_by.get_full_name() or obj.created_by.username or obj.created_by.email


class RiskMitigationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Risk
        fields = ("mitigation_plan", "mitigation_status")


class RiskTMStatusUpdateSerializer(serializers.ModelSerializer):
    """
    TM can update only risk.status (Open/InProgress/Closed)
    """
    class Meta:
        model = Risk
        fields = ("status",)