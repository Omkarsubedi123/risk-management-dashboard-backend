from rest_framework import serializers
from .models import Risk


class RiskSerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source="created_by.id")

    class Meta:
        model = Risk
        fields = "__all__"
        read_only_fields = (
            "created_by",
            "risk_score",
            "likelihood",
            "risk_level",
            "mitigation_status",
            "created_at",
            "updated_at",
        )


class RiskMitigationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Risk
        fields = ("mitigation_plan", "mitigation_status")
