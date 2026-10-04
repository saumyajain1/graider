from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle


class IPScopedRateThrottle(ScopedRateThrottle):
    """Count auth requests by client IP even when a session already exists."""

    def get_ident(self, request):
        # Render places the real client IP first in X-Forwarded-For.
        if not settings.DEBUG:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
            if forwarded:
                client_ip = forwarded.split(",", 1)[0].strip()
                if client_ip:
                    return client_ip
        return request.META.get("REMOTE_ADDR", "")

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
