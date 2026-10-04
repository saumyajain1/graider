import logging

from allauth.socialaccount.adapter import get_adapter
from django.conf import settings
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema_view
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.schema import APIErrorSerializer, api_schema

from .google import redirect_to_google
from .models import User
from .serializers import (
    AccountMessageSerializer,
    AuthOptionsSerializer,
    DisconnectAccountSerializer,
    GoogleRedirectSerializer,
    GoogleStartSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .throttles import IPScopedRateThrottle


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(
    post=api_schema(
        request=RegisterSerializer,
        response=UserSerializer,
        code=201,
        errors={429: APIErrorSerializer},
    ),
)
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = "auth_register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(
    post=api_schema(
        request=LoginSerializer, response=UserSerializer, errors={429: APIErrorSerializer}
    ),
)
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = "auth_login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request, user)
        return Response(UserSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(
    post=api_schema(code=204),
)
class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if request.user.is_authenticated:
            logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
@extend_schema_view(
    get=api_schema(
        response=UserSerializer, errors={401: APIErrorSerializer, 429: APIErrorSerializer}
    ),
)
class MeView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = "auth_me"

    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(UserSerializer(request.user).data)


@method_decorator(ensure_csrf_cookie, name="dispatch")
@extend_schema_view(get=api_schema(response=AuthOptionsSerializer))
class AuthOptionsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(
            {
                "google_enabled": settings.GOOGLE_LOGIN_ENABLED,
                "password_reset_enabled": settings.PASSWORD_RESET_ENABLED,
            }
        )


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(
    post=api_schema(
        request=GoogleStartSerializer,
        response=GoogleRedirectSerializer,
        errors={429: APIErrorSerializer, 503: APIErrorSerializer},
        description="Start Google sign-in/signup or explicitly connect an authenticated account. "
        "Navigate the browser to redirect_url; the callback establishes a Django session.",
    )
)
class GoogleStartView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = "auth_google"

    def post(self, request):
        serializer = GoogleStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        process = serializer.validated_data["process"]
        if process == "connect" and not request.user.is_authenticated:
            return Response({"detail": "Sign in before connecting Google."}, status=403)
        if process == "login" and request.user.is_authenticated:
            return Response({"detail": "Use Connect Google from your profile."}, status=400)
        if not settings.GOOGLE_LOGIN_ENABLED:
            return Response({"detail": "Google sign-in is not configured yet."}, status=503)
        provider = get_adapter(request._request).get_provider(request._request, "google")
        response = redirect_to_google(request._request, provider, process)
        return Response({"redirect_url": response.url})


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(patch=api_schema(request=ProfileUpdateSerializer, response=UserSerializer))
class ProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.full_name = serializer.validated_data["full_name"]
        request.user.save(update_fields=["full_name"])
        return Response(UserSerializer(request.user).data)


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(post=api_schema(request=PasswordChangeSerializer, response=UserSerializer))
class PasswordChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = "auth_account"

    def post(self, request):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            serializer = PasswordChangeSerializer(data=request.data, context={"user": user})
            serializer.is_valid(raise_exception=True)
            user.set_password(serializer.validated_data["new_password"])
            user.save(update_fields=["password"])
        update_session_auth_hash(request._request, user)
        return Response(UserSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(
    post=api_schema(
        request=PasswordResetRequestSerializer,
        response=AccountMessageSerializer,
        errors={429: APIErrorSerializer, 503: APIErrorSerializer},
    )
)
class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = "auth_recovery"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not settings.PASSWORD_RESET_ENABLED:
            return Response(
                {
                    "detail": "Password recovery is not available yet. Please contact Graider support."
                },
                status=503,
            )
        users = User.objects.filter(
            email__iexact=serializer.validated_data["email"], is_active=True
        )
        for user in users:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            # The token stays in the URL fragment, which browsers do not send to servers/referrers.
            base = settings.FRONTEND_URL.rstrip("/") or request.build_absolute_uri("/").rstrip("/")
            link = f"{base}/reset-password#{uid}/{token}"
            try:
                send_mail(
                    "Reset your Graider password",
                    f"Use this link to set a new password for Graider:\n\n{link}\n\nThis link expires in one hour and works once. If you did not request it, ignore this email.",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            except Exception:
                # Do not log provider responses or token-bearing email contents.
                logging.getLogger(__name__).error("Password recovery email delivery failed")
        return Response(
            {
                "detail": "If an account matches this email, you will receive a reset link. Check your inbox and spam folder."
            }
        )


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(
    post=api_schema(
        request=PasswordResetConfirmSerializer,
        response=AccountMessageSerializer,
        errors={429: APIErrorSerializer},
    )
)
class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = "auth_account"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=serializer.validated_data["user"].pk)
            if not default_token_generator.check_token(user, serializer.validated_data["token"]):
                return Response(
                    {"detail": "This reset link has already been used. Request a new link."},
                    status=400,
                )
            user.set_password(serializer.validated_data["new_password"])
            user.save(update_fields=["password"])
        # Password changes invalidate all existing sessions; recovery does not automatically sign in.
        return Response({"detail": "Password updated. Sign in with your new password."})


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(post=api_schema(request=DisconnectAccountSerializer, response=UserSerializer))
class DisconnectAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = "auth_account"

    def post(self, request):
        serializer = DisconnectAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not user.has_usable_password():
                return Response(
                    {
                        "detail": "Set a password using an email reset link before disconnecting Google."
                    },
                    status=400,
                )
            if not user.check_password(serializer.validated_data["current_password"]):
                return Response(
                    {"detail": "Enter your current password to disconnect Google."}, status=400
                )
            user.socialaccount_set.filter(provider=serializer.validated_data["provider"]).delete()
        return Response(UserSerializer(user).data)
