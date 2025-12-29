from rest_framework import serializers
from .models import Risk


class RiskSerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source="created_by.id")

    # ✅ REQUIRED FOR GLOBAL RISK TABLE
    project_name = serializers.CharField(
        source="project.name", read_only=True
    )
    project_id = serializers.IntegerField(
        source="project.id", read_only=True
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


class RiskMitigationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Risk
        fields = ("mitigation_plan", "mitigation_status")
