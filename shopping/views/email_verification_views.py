from __future__ import annotations

from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopping.models.email_verification import EmailLog, EmailVerificationToken
from shopping.serializers.email_verification_serializers import (
    ResendVerificationEmailSerializer,
    SendVerificationEmailSerializer,
    VerifyEmailByCodeSerializer,
    VerifyEmailByTokenSerializer,
)
from shopping.tasks.email_tasks import send_verification_email_task
from shopping.throttles import EmailVerificationRateThrottle, EmailVerificationResendRateThrottle


class SendVerificationEmailView(APIView):
    """이메일 인증 발송 API (비동기 처리)"""

    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailVerificationRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = SendVerificationEmailSerializer(data=request.data, context={"request": request})

        if not serializer.is_valid():
            # 재발송 제한 에러인 경우 429 반환
            if "1분" in str(serializer.errors):
                return Response(serializer.errors, status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        # 기존 미사용 토큰 무효화
        EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)

        # 새 토큰 생성
        token = EmailVerificationToken.objects.create(user=user)

        # 비동기 이메일 발송 (Celery 태스크)
        send_verification_email_task.delay(
            user_id=user.id,
            token_id=token.id,
            is_resend=False,
        )

        return Response(
            {"message": "인증 이메일이 발송 중입니다. 잠시 후 이메일을 확인해주세요."},
            status=status.HTTP_200_OK,
        )


class VerifyEmailView(APIView):
    """이메일 인증 확인 API"""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        """UUID 토큰으로 인증 (GET 요청)"""
        token = request.GET.get("token")

        if not token:
            return Response(
                {"error": "토큰이 제공되지 않았습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Serializer를 사용한 검증 및 인증 처리
        serializer = VerifyEmailByTokenSerializer(data={"token": token}, context={"request": request})

        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "이메일 인증이 완료되었습니다!"},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request: Request) -> Response:
        """6자리 코드로 인증 (POST 요청)"""
        if not request.user.is_authenticated:
            return Response(
                {"error": "로그인이 필요합니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Serializer를 사용한 검증 및 인증 처리
        serializer = VerifyEmailByCodeSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "이메일 인증이 완료되었습니다."},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResendVerificationEmailView(APIView):
    """이메일 재발송 API"""

    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailVerificationResendRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = ResendVerificationEmailSerializer(data=request.data, context={"request": request})

        if not serializer.is_valid():
            # 재발송 제한 에러인 경우 429 반환
            if "1분" in str(serializer.errors):
                return Response(serializer.errors, status=status.HTTP_429_TOO_MANY_REQUESTS)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        # 기존 미사용 토큰 무효화
        EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)

        # 새 토큰 생성
        token = EmailVerificationToken.objects.create(user=user)

        # 비동기 이메일 재발송 (Celery 태스크)
        send_verification_email_task.delay(
            user_id=user.id,
            token_id=token.id,
            is_resend=True,
        )

        return Response(
            {"message": "인증 이메일이 재발송 중입니다. 잠시 후 이메일을 확인해주세요."},
            status=status.HTTP_200_OK,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_verification_status(request: Request) -> Response:
    """이메일 인증 상태 확인 API"""
    user = request.user

    response_data = {"is_verified": user.is_email_verified, "email": user.email}

    # 인증되지 않은 경우에만 최신 토큰 정보 조회 (성능 최적화)
    if not user.is_email_verified:
        latest_token = (
            EmailVerificationToken.objects.filter(user=user)
            .only("id", "created_at", "is_used")
            .order_by("-created_at")
            .first()
        )

        if latest_token:
            response_data.update(
                {
                    "pending_verification": True,
                    "token_expired": latest_token.is_expired(),
                    "can_resend": (latest_token.can_resend() if not latest_token.is_used else True),
                }
            )

    return Response(response_data, status=status.HTTP_200_OK)
