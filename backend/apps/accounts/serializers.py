from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from rest_framework import serializers

from .models import User


LOCAL_TEST_PASSWORD = "test1234"


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "full_name")


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
            raise serializers.ValidationError(
                {"detail": "Invalid email or password."}
            )

        attrs["user"] = user
        return attrs
