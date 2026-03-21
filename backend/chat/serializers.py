import re
from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import RiskMessage, RiskMessageAttachment

User = get_user_model()

MENTION_RE = re.compile(r"@([A-Za-z0-9_.-]+)")


class RiskMessageAttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = RiskMessageAttachment
        fields = ("id", "url", "uploaded_at")

    def get_url(self, obj):
        request = self.context.get("request")
        try:
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        except Exception:
            return ""


class RiskMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_username = serializers.SerializerMethodField()
    is_edited = serializers.SerializerMethodField()
    attachments = RiskMessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = RiskMessage
        fields = (
            "id",
            "project",
            "risk",
            "sender",
            "sender_name",
            "sender_username",
            "body",
            "created_at",
            "edited_at",
            "is_edited",
            "attachments",
        )
        read_only_fields = ("project", "sender", "created_at", "edited_at", "is_edited")

    def get_sender_name(self, obj):
        u = obj.sender
        if not u:
            return "Deleted User"
        return u.get_full_name() or getattr(u, "username", "") or getattr(u, "email", "")

    def get_sender_username(self, obj):
        if not obj.sender:
            return ""
        return getattr(obj.sender, "username", "") or ""

    def get_is_edited(self, obj):
        return bool(obj.edited_at)


class RiskMessageCreateSerializer(serializers.ModelSerializer):
    files = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        write_only=True
    )

    class Meta:
        model = RiskMessage
        fields = ("risk", "body", "files")

    def create(self, validated_data):
        files = validated_data.pop("files", [])
        request = self.context["request"]
        user = request.user
        risk = validated_data["risk"]

        msg = RiskMessage.objects.create(
            project=risk.project,
            sender=user,
            **validated_data
        )

        for f in files:
            RiskMessageAttachment.objects.create(message=msg, file=f)

        return msg