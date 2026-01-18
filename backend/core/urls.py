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

]
