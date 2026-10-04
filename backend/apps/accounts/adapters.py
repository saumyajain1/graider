from urllib.parse import urlencode

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.base import AuthProcess
from allauth.socialaccount.providers.base.constants import AuthError
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import User
from .throttles import IPScopedRateThrottle


def frontend_url(path, **params):
    url = f"{settings.FRONTEND_URL.rstrip('/')}{path}"
    return f"{url}?{urlencode(params)}" if params else url


def auth_redirect(code, *, connect=False, admin_login=False):
    if admin_login:
        return HttpResponseRedirect(f"{reverse('admin:login')}?{urlencode({'auth': code})}")
    return HttpResponseRedirect(frontend_url("/profile" if connect else "/login", auth=code))


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        return frontend_url("/")

    def get_signup_redirect_url(self, request):
        return frontend_url("/")

    def respond_user_inactive(self, request, user):
        state = getattr(request, "graider_oauth_state", {})
        return auth_redirect(
            "unavailable", admin_login=bool(state.get("data", {}).get("admin_login"))
        )


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    throttle_scope = "auth_register"

    def save_user(self, request, sociallogin, form=None):
        try:
            with transaction.atomic():
                return super().save_user(request, sociallogin, form=form)
        except IntegrityError:
            # Two simultaneous registrations must not leave a partial user.
            raise ImmediateHttpResponse(auth_redirect("existing_account"))

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        name = sociallogin.account.extra_data.get("name") or " ".join(
            part for part in (data.get("first_name"), data.get("last_name")) if part
        )
        user.full_name = (name or "Teacher")[:255]
        return user

    def pre_social_login(self, request, sociallogin):
        if sociallogin.state.get("data", {}).get("admin_login"):
            if not (
                sociallogin.is_existing and sociallogin.user.is_active and sociallogin.user.is_staff
            ):
                raise ImmediateHttpResponse(auth_redirect("denied", admin_login=True))
            return
        connect = sociallogin.state.get("process") == AuthProcess.CONNECT
        if connect:
            # Bind the callback to the user who explicitly started linking.
            expected_user = sociallogin.state.get("data", {}).get("user_id")
            if not request.user.is_authenticated or request.user.pk != expected_user:
                raise ImmediateHttpResponse(auth_redirect("session_changed"))
            if sociallogin.is_existing and sociallogin.user.pk != request.user.pk:
                raise ImmediateHttpResponse(auth_redirect("already_connected", connect=True))
            if (
                request.user.socialaccount_set.filter(provider="google")
                .exclude(uid=sociallogin.account.uid)
                .exists()
            ):
                raise ImmediateHttpResponse(auth_redirect("different_google", connect=True))
        elif not sociallogin.is_existing:
            email = sociallogin.user.email
            if not email or not any(
                address.verified and address.email.casefold() == email.casefold()
                for address in sociallogin.email_addresses
            ):
                raise ImmediateHttpResponse(auth_redirect("unverified_email"))
            if User.objects.filter(email__iexact=email).exists():
                raise ImmediateHttpResponse(auth_redirect("existing_account"))
            if not IPScopedRateThrottle().allow_request(request, self):
                raise ImmediateHttpResponse(auth_redirect("rate_limited"))

    def get_connect_redirect_url(self, request, socialaccount):
        return frontend_url("/profile", auth="connected")

    def on_authentication_error(
        self, request, provider, error=None, exception=None, extra_context=None
    ):
        state = (extra_context or {}).get("state") or {}
        code = "cancelled" if error == AuthError.CANCELLED else "failed"
        raise ImmediateHttpResponse(
            auth_redirect(
                code,
                connect=state.get("process") == AuthProcess.CONNECT,
                admin_login=bool(state.get("data", {}).get("admin_login")),
            )
        )
