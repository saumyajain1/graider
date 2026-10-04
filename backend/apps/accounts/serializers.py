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
    password_reset_enabled = serializers.BooleanField()


class GoogleStartSerializer(serializers.Serializer):
    process = serializers.ChoiceField(choices=["login", "connect"])


class GoogleRedirectSerializer(serializers.Serializer):
    redirect_url = serializers.URLField()


class UserSerializer(serializers.ModelSerializer):
    connected_accounts = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()

    @extend_schema_field(serializers.BooleanField())
    def get_has_password(self, user):
        return user.has_usable_password()

    @extend_schema_field(ConnectedAccountSerializer(many=True))
    def get_connected_accounts(self, user):
        return [
            {"provider": account.provider, "email": account.extra_data.get("email", "")}
            for account in user.socialaccount_set.all()
        ]

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "connected_accounts", "has_password")


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


class ProfileUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context["user"]
        if not user.has_usable_password() or not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "Enter your current password."})
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode

        try:
            user = User.objects.get(pk=urlsafe_base64_decode(attrs["uid"]).decode(), is_active=True)
        except (ValueError, TypeError, OverflowError, UnicodeDecodeError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                {"detail": "This reset link is invalid or expired. Request a new link."}
            )
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        password_validation.validate_password(attrs["new_password"], user)
        attrs["user"] = user
        return attrs


class DisconnectAccountSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=["google"])
    current_password = serializers.CharField(write_only=True)


class AccountMessageSerializer(serializers.Serializer):
    detail = serializers.CharField()
