from django.conf import settings
from django.contrib.admin import AdminSite


class GraiderAdminSite(AdminSite):
    site_header = "Graider administration"
    site_title = "Graider admin"
    login_template = "admin/graider_login.html"

    def login(self, request, extra_context=None):
        errors = {
            "unavailable": "Google sign-in is not configured for this server.",
            "denied": "This Google account does not have admin access.",
            "cancelled": "Google sign-in was cancelled. You can try again.",
            "failed": "Google sign-in failed. Please try again.",
            "session_changed": "Your session changed. Please try signing in again.",
            "rate_limited": "Too many sign-in attempts. Please wait before trying again.",
        }
        context = {
            **(extra_context or {}),
            "google_login_enabled": settings.GOOGLE_LOGIN_ENABLED,
            "google_login_error": errors.get(request.GET.get("auth")),
        }
        return super().login(request, extra_context=context)
