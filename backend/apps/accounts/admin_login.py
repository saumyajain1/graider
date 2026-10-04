from urllib.parse import urlsplit

from allauth.socialaccount.adapter import get_adapter
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .adapters import auth_redirect
from .google import redirect_to_google
from .throttles import IPScopedRateThrottle


class AdminGoogleThrottle:
    throttle_scope = "auth_google"


@require_POST
@csrf_protect
def admin_google_login(request):
    next_url = request.POST.get("next", "")
    admin_root = reverse("admin:index")
    if not (
        url_has_allowed_host_and_scheme(next_url, allowed_hosts=set())
        and urlsplit(next_url).path.startswith(admin_root)
    ):
        next_url = admin_root
    if request.user.is_authenticated:
        if request.user.is_active and request.user.is_staff:
            return HttpResponseRedirect(next_url)
        return auth_redirect("denied", admin_login=True)
    if not settings.GOOGLE_LOGIN_ENABLED:
        return auth_redirect("unavailable", admin_login=True)
    if not IPScopedRateThrottle().allow_request(request, AdminGoogleThrottle()):
        return auth_redirect("rate_limited", admin_login=True)
    provider = get_adapter(request).get_provider(request, "google")
    return redirect_to_google(request, provider, "login", admin_next=next_url)
