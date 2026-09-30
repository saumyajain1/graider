from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/assignments/", include("apps.assignments.urls")),
    path("api/", include("apps.grading.urls")),
]
