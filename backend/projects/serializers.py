from rest_framework import serializers
from .models import Project

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ["created_at", "updated_at", "created_by"]

    # def create(self, validated_data):
    #     user = self.context["request"].user
    #     validated_data["created_by"] = user
    #     return super().create(validated_data)
