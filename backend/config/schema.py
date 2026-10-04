from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers


class APIErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


def api_schema(*, response=None, code=200, request=None, ai=False, **kwargs):
    responses = {
        400: OpenApiResponse(
            OpenApiTypes.OBJECT, description="Invalid input: detail or field errors."
        ),
        403: OpenApiResponse(
            APIErrorSerializer, description="Login required or CSRF check failed."
        ),
        404: OpenApiResponse(
            APIErrorSerializer, description="Missing resource or another teacher's resource."
        ),
    }
    responses.update(response if isinstance(response, dict) else {code: response})
    if ai:
        kwargs["parameters"] = [
            *kwargs.get("parameters", []),
            OpenApiParameter(
                "Idempotency-Key",
                OpenApiTypes.STR,
                OpenApiParameter.HEADER,
                description="Optional unique action key. Background mode replays the same job for repeated identical requests.",
            ),
        ]
        responses.update(
            {
                429: OpenApiResponse(
                    APIErrorSerializer, description="AI request rate or token quota exceeded."
                ),
                502: OpenApiResponse(
                    APIErrorSerializer,
                    description="AI generation failed; safe error message returned.",
                ),
                503: OpenApiResponse(
                    APIErrorSerializer,
                    description="AI configuration or provider spending limit reached.",
                ),
            }
        )
    responses.update(kwargs.pop("errors", {}))
    return extend_schema(request=request, responses=responses, **kwargs)
