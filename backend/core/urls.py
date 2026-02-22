from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path("api/projects/", include("projects.urls")),
    path("api/", include("risks.urls")),
    path("api/notifications/", include("notifications.urls")),
    path("api/dashboard/", include("dashboardpm.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/chat/", include("chat.urls")),
]

# serve uploaded media in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
