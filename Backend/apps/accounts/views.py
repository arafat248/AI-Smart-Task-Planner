from __future__ import annotations
import logging
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import (
    AuthResponseSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    ForgotPasswordSerializer,
    LogoutSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    ResetPasswordSerializer,
    UpdateProfileSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)
from .services import (
    AuthService,
    EmailVerificationService,
    PasswordService,
    ProfileService,
)
logger = logging.getLogger(__name__)

_auth_svc = AuthService()
_pw_svc = PasswordService()
_ev_svc = EmailVerificationService()
_profile_svc = ProfileService()

TAG = ['auth']

class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAG,
        summary='Register a new account',
        description=(
            'Creates a new user, issues JWT tokens, and sends a verification email. '
            'The access token is valid for 60 minutes; refresh for 7 days.'
        ),
        request=RegisterSerializer,
        responses={
            201: AuthResponseSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = _auth_svc.register(serializer.validated_data)
        return Response(
            {
                'user': UserSerializer(result['user']).data,
                'access': result['access'],
                'refresh': result['refresh'],
            },
            status=status.HTTP_201_CREATED,
        )

class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    @extend_schema(
        tags=TAG,
        summary='Login — obtain JWT token pair',
        description='Returns access token (60 min) and refresh token (7 days).',
        responses={
            200: OpenApiResponse(description='{ access, refresh }'),
            401: OpenApiResponse(description='Invalid credentials'),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

class TokenRefreshDocView(TokenRefreshView):
    @extend_schema(
        tags=TAG,
        summary='Refresh access token',
        description=(
            'Exchange a valid refresh token for a new access token. '
            'If ROTATE_REFRESH_TOKENS is enabled the old refresh token is blacklisted.'
        ),
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=TAG,
        summary='Logout — blacklist refresh token',
        description='Adds the provided refresh token to the blacklist. Access tokens expire naturally.',
        request=LogoutSerializer,
        responses={
            204: OpenApiResponse(description='Logged out successfully'),
            400: OpenApiResponse(description='Invalid or missing token'),
        },
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _auth_svc.logout(serializer.validated_data['refresh'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=TAG,
        summary='Change password (authenticated)',
        description='Requires the current password. All existing sessions remain valid.',
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description='Password changed successfully'),
            400: OpenApiResponse(description='Old password incorrect or new password invalid'),
        },
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        _pw_svc.change_password(request.user, d['old_password'], d['new_password'])
        return Response({'detail': 'Password changed successfully.'})

class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAG,
        summary='Request password reset email',
        description=(
            'Sends a one-time reset link to the email address if an active account exists. '
            'Always returns 200 to prevent user enumeration.'
        ),
        request=ForgotPasswordSerializer,
        responses={200: OpenApiResponse(description='Reset email sent if account exists')},
    )
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _pw_svc.request_password_reset(serializer.validated_data['email'])
        return Response({'detail': 'If that email is registered, a reset link has been sent.'})

class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAG,
        summary='Reset password via token',
        description='Validates the token from the reset email and sets a new password. Token is single-use.',
        request=ResetPasswordSerializer,
        responses={
            200: OpenApiResponse(description='Password reset successfully'),
            400: OpenApiResponse(description='Invalid/expired token or mismatched passwords'),
        },
    )
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        _pw_svc.reset_password(d['token'], d['new_password'])
        return Response({'detail': 'Password reset successfully. You can now log in.'})

class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAG,
        summary='Verify email address via token',
        description='Marks the user as verified. Token is single-use and expires in 24 hours.',
        request=VerifyEmailSerializer,
        responses={
            200: OpenApiResponse(description='Email verified'),
            400: OpenApiResponse(description='Invalid or expired token'),
        },
    )
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _ev_svc.confirm(serializer.validated_data['token'])
        return Response({
            'detail': 'Email verified successfully.',
            'user': UserSerializer(user).data,
        })

class ResendVerificationView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAG,
        summary='Resend email verification link',
        description=(
            'Invalidates any existing token and sends a fresh verification email. '
            'Returns 200 even if the email is not found to prevent enumeration.'
        ),
        request=ResendVerificationSerializer,
        responses={200: OpenApiResponse(description='Verification email resent')},
    )
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .repositories import UserRepository
        user = UserRepository().get_by_email(serializer.validated_data['email'])
        if user and user.is_active and not user.is_email_verified:
            _ev_svc.send_verification(user)
        return Response({'detail': 'If that email is registered and unverified, a new link has been sent.'})

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=TAG,
        summary='Get current user profile',
        responses={200: UserSerializer},
    )
    def get(self, request):
        from .repositories import UserRepository
        user = UserRepository().get_by_id(request.user.id)
        return Response(UserSerializer(user).data)

    @extend_schema(
        tags=TAG,
        summary='Update profile',
        description='Partial update — send only the fields you want to change.',
        request=UpdateProfileSerializer,
        responses={200: UserSerializer},
    )
    def patch(self, request):
        serializer = UpdateProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user_fields, profile_fields = serializer.split(serializer.validated_data)
        updated_user = _profile_svc.update(request.user, user_fields, profile_fields)
        return Response(UserSerializer(updated_user).data)
