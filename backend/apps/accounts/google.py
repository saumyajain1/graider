import secrets

import jwt
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter, _verify_and_decode
from allauth.socialaccount.providers.oauth2.client import OAuth2Error
from allauth.socialaccount.providers.oauth2.views import OAuth2CallbackView
from django.conf import settings
from django.utils.crypto import constant_time_compare

from .adapters import auth_redirect


class GoogleOIDCAdapter(GoogleOAuth2Adapter):
    """Require a signed ID token and the nonce bound to this browser's handshake."""

    def complete_login(self, request, app, token, **kwargs):
        credential = kwargs["response"].get("id_token")
        if not credential:
            raise OAuth2Error("Missing identity token")
        try:
            if jwt.get_unverified_header(credential).get("alg") != "RS256":
                raise OAuth2Error("Unexpected signing algorithm")
        except jwt.PyJWTError as exc:
            raise OAuth2Error("Invalid identity token") from exc
        data = _verify_and_decode(app, credential, verify_signature=True)
        expected = request.graider_oauth_state.get("data", {}).get("nonce")
        if (
            not expected
            or not isinstance(data.get("nonce"), str)
            or not constant_time_compare(data["nonce"], expected)
            or not isinstance(data.get("sub"), str)
            or not data["sub"]
            or "exp" not in data
            or data.get("email_verified") is not True
        ):
            raise OAuth2Error("Invalid identity claims")
        # Retain only profile information; never persist provider tokens.
        profile = {
            key: data[key] for key in ("sub", "email", "email_verified", "name") if key in data
        }
        return self.get_provider().sociallogin_from_response(request, profile)


class GoogleCallbackView(OAuth2CallbackView):
    def dispatch(self, request, *args, **kwargs):
        if not settings.GOOGLE_LOGIN_ENABLED:
            return auth_redirect("unavailable")
        return super().dispatch(request, *args, **kwargs)

    def _get_state(self, request, provider):
        state, response = super()._get_state(request, provider)
        request.graider_oauth_state = state or {}
        if state and not response:
            expected_user = state.get("data", {}).get("user_id")
            actual_user = request.user.pk if request.user.is_authenticated else None
            if expected_user != actual_user:
                return None, auth_redirect(
                    "session_changed", admin_login=bool(state.get("data", {}).get("admin_login"))
                )
        return state, response


google_callback = GoogleCallbackView.adapter_view(GoogleOIDCAdapter)


def redirect_to_google(request, provider, process, *, admin_next=None):
    nonce = secrets.token_urlsafe(32)
    params = provider.get_auth_params()
    params["nonce"] = nonce
    return provider.redirect(
        request,
        process=process,
        auth_params=params,
        next_url=admin_next,
        data={
            "nonce": nonce,
            "user_id": request.user.pk if process == "connect" else None,
            "admin_login": bool(admin_next),
        },
    )
