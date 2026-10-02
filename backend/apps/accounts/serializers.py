from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import User

LOCAL_TEST_PASSWORD = "test1234"


class ConnectedAccountSerializer(serializers.Serializer):
    provider = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)


class AuthOptionsSerializer(serializers.Serializer):
    google_enabled = serializers.BooleanField()


class GoogleStartSerializer(serializers.Serializer):
    process = serializers.ChoiceField(choices=["login", "connect"])


class GoogleRedirectSerializer(serializers.Serializer):
    redirect_url = serializers.URLField()


class UserSerializer(serializers.ModelSerializer):
    connected_accounts = serializers.SerializerMethodField()

    @extend_schema_field(ConnectedAccountSerializer(many=True))
    def get_connected_accounts(self, user):
        return [
            {"provider": account.provider, "email": account.extra_data.get("email", "")}
            for account in user.socialaccount_set.all()
        ]

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "connected_accounts")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("email", "full_name", "password")

    def validate_password(self, value):
        if settings.DEBUG and value == LOCAL_TEST_PASSWORD:
            return value
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request=request,
            email=attrs["email"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError({"detail": "Invalid email or password."})

        attrs["user"] = user
        return attrs
