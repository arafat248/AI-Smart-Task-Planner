from __future__ import annotations
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Profile, User

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['avatar_url', 'timezone', 'bio', 'preferences']

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'full_name', 'is_email_verified', 'date_joined', 'profile',
        ]
        read_only_fields = fields

    def get_full_name(self, obj: User) -> str:
        return obj.get_full_name()

class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)

class AuthResponseSerializer(serializers.Serializer):
    user = UserSerializer(read_only=True)
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)

class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(
        help_text='Must be unique. Used to log in.'
    )
    password = serializers.CharField(
        min_length=8,
        write_only=True,
        style={'input_type': 'password'},
        help_text='Minimum 8 characters.',
    )
    first_name = serializers.CharField(max_length=150, required=False, default='')
    last_name = serializers.CharField(max_length=150, required=False, default='')

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        help_text='The refresh token to blacklist.'
    )

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
        help_text='Current password.',
    )
    new_password = serializers.CharField(
        min_length=8,
        write_only=True,
        style={'input_type': 'password'},
        help_text='New password — minimum 8 characters.',
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
        help_text='Repeat new password.',
    )
    def validate(self, data: dict) -> dict:
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': 'Passwords do not match.'}
            )
        return data

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(
        help_text='Email address associated with your account.'
    )

class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(
        help_text='UUID token received in the reset email.'
    )
    new_password = serializers.CharField(
        min_length=8,
        write_only=True,
        style={'input_type': 'password'},
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
    )

    def validate(self, data: dict) -> dict:
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': 'Passwords do not match.'}
            )
        return data

class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField(
        help_text='UUID token received in the verification email.'
    )

class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(
        help_text='Email address to resend verification to.'
    )

class UpdateProfileSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    username = serializers.CharField(max_length=150, required=False)
    avatar_url = serializers.URLField(required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=64, required=False)
    bio = serializers.CharField(max_length=300, required=False, allow_blank=True)
    preferences = serializers.DictField(required=False)

    USER_FIELDS = {'first_name', 'last_name', 'username'}
    PROFILE_FIELDS = {'avatar_url', 'timezone', 'bio', 'preferences'}

    def split(self, validated_data: dict) -> tuple[dict, dict]:
        user_fields = {k: v for k, v in validated_data.items() if k in self.USER_FIELDS}
        profile_fields = {k: v for k, v in validated_data.items() if k in self.PROFILE_FIELDS}
        return user_fields, profile_fields

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user: User):
        token = super().get_token(user)
        token['email'] = user.email
        token['is_email_verified'] = user.is_email_verified
        return token
