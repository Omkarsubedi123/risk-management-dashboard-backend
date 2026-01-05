from django.urls import path
from .views import NotificationListView, MarkNotificationReadView
from .views import MarkAllReadView, ClearAllNotificationsView

urlpatterns = [
    path("", NotificationListView.as_view(), name="notifications"),
    path("<int:pk>/read/", MarkNotificationReadView.as_view(), name="notification-read"),
    path("mark-all-read/", MarkAllReadView.as_view(), name="mark-all-read"),
    path("clear/", ClearAllNotificationsView.as_view(), name="clear-notifications"),
]
