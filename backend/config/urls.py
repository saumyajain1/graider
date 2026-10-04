from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.admin_login import admin_google_login
from apps.accounts.google import google_callback

from .views import health, privacy, public_home, spa_index

urlpatterns = [
    path("about/", public_home, name="public-home"),
    path("privacy/", privacy, name="privacy"),
    path("health/", health, name="health"),
    path("admin/google/login/", admin_google_login, name="admin-google-login"),
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
    path("accounts/google/login/callback/", google_callback, name="google_callback"),
    path("api/assignments/", include("apps.assignments.urls")),
    path("api/", include("apps.grading.urls")),
    re_path(
        r"^(?!api(?:/|$)|accounts(?:/|$)|admin(?:/|$)|static(?:/|$)|media(?:/|$)|health(?:/|$)|favicon\.ico(?:/|$)|robots\.txt(?:/|$)).*$",
        spa_index,
        name="spa-index",
    ),
]
