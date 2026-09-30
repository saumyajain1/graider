from django.contrib import admin
from django.urls import include, path, re_path

from .views import health, spa_index

urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/assignments/", include("apps.assignments.urls")),
    path("api/", include("apps.grading.urls")),
    re_path(
        r"^(?!api(?:/|$)|admin(?:/|$)|static(?:/|$)|media(?:/|$)|health(?:/|$)|favicon\.ico(?:/|$)|robots\.txt(?:/|$)).*$",
        spa_index,
        name="spa-index",
    ),
]
