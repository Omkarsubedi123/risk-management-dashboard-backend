from django.db import models
from django.conf import settings

from projects.models import Project
from risks.models import Risk  # adjust if your risks app name is different


class RiskMessage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="risk_messages")
    risk = models.ForeignKey(Risk, on_delete=models.CASCADE, related_name="chat_messages")

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_risk_messages")

    body = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"RiskMessage({self.id}) risk={self.risk_id} sender={self.sender_id}"


def chat_upload_path(instance, filename):
    return f"chat/risk_{instance.message.risk_id}/msg_{instance.message_id}/{filename}"


class RiskMessageAttachment(models.Model):
    message = models.ForeignKey(RiskMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=chat_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"RiskMessageAttachment({self.id}) msg={self.message_id}"