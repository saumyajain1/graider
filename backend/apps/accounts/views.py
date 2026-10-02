from allauth.socialaccount.adapter import get_adapter
from django.conf import settings
from django.contrib.auth import login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema_view
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.schema import APIErrorSerializer, api_schema

from .google import redirect_to_google
from .serializers import (
    AuthOptionsSerializer,
    GoogleRedirectSerializer,
    GoogleStartSerializer,
    LoginSerializer,
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
        return Response({"google_enabled": settings.GOOGLE_LOGIN_ENABLED})


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
