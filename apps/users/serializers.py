"""User serializers."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Read/update representation of a user (no password exposure)."""

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "is_active",
            "is_staff",
            "created_at",
        ]
        # ``email`` is the login identifier and gates email verification, so it
        # is NOT updatable here — changing it needs a dedicated re-verification
        # flow that also syncs the allauth EmailAddress record.
        read_only_fields = ["id", "email", "is_active", "is_staff", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    """Self-service registration with write-only, validated password."""

    # Declared explicitly to drop the model's auto ``UniqueValidator``: a 400
    # "already exists" here would leak which emails are registered. The view
    # handles the duplicate case in an enumeration-safe way instead.
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True, min_length=8, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ["id", "email", "password", "first_name", "last_name"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        # Run Django's AUTH_PASSWORD_VALIDATORS (common/numeric/min-length and
        # attribute-similarity). ``create_user``/``set_password`` do NOT run
        # these, so without this step signup would only enforce ``min_length``.
        # Build an unsaved User so the similarity check can compare against the
        # email/name fields.
        user = User(
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)
