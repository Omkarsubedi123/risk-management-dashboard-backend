from rest_framework import serializers
from .models import Risk


class RiskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Risk
        fields = [
            "risk_id",
            "project",
            "title",
            "description",
            "impact",
            "probability",
            "risk_score",
            "risk_level",
            "estimated_cost",
            "loss_percentage",
            "calculated_loss",
            "risk_decision",
            "assigned_to",
            "created_at",
        ]
        read_only_fields = [
            "risk_score",
            "risk_level",
            "calculated_loss",
            "created_at",
        ]
