from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import health, spa_index

urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        ensure_csrf_cookie(
            SpectacularSwaggerView.as_view(url_name="schema", template_name_js="api/swagger.js")
        ),
        name="swagger-ui",
    ),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/assignments/", include("apps.assignments.urls")),
    path("api/", include("apps.grading.urls")),
    re_path(
        r"^(?!api(?:/|$)|admin(?:/|$)|static(?:/|$)|media(?:/|$)|health(?:/|$)|favicon\.ico(?:/|$)|robots\.txt(?:/|$)).*$",
        spa_index,
        name="spa-index",
    ),
]
