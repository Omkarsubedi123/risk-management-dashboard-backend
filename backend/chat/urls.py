from django.urls import path
from .views import RiskMessageListCreateView, RiskMessageEditView, RiskChatParticipantsView

urlpatterns = [
    path("risks/<int:risk_id>/messages/", RiskMessageListCreateView.as_view(), name="risk-messages"),
    path("messages/<int:message_id>/", RiskMessageEditView.as_view(), name="risk-message-edit"),
    path("risks/<int:risk_id>/participants/", RiskChatParticipantsView.as_view(), name="risk-chat-participants"),
]