from rest_framework import serializers
from .models import Risk


class RiskSerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source="created_by.id")

    class Meta:
        model = Risk
        exclude = (
            "risk_score",
            "risk_level",
            "calculated_loss",
            "created_at",
        )

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["created_by"] = request.user
        return super().create(validated_data)
