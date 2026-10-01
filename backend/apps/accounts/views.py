from django.contrib.auth import login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema_view
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.schema import APIErrorSerializer, api_schema

from .serializers import LoginSerializer, RegisterSerializer, UserSerializer
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
