from __future__ import annotations

import uuid

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
)
from shopping.tasks.email_tasks import send_verification_email_task


class SendVerificationEmailView(APIView):
    """이메일 인증 발송 API (비동기 처리)"""

    permission_classes = [IsAuthenticated]

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
            {
                "message": "인증 이메일이 발송 중입니다. 잠시 후 이메일을 확인해주세요.",
                "verification_code": token.verification_code,  # 테스트용
            },
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

        # UUID 형식 검증
        try:
            uuid.UUID(str(token))
        except (ValueError, TypeError, AttributeError):
            return Response(
                {"error": "유효하지 않은 토큰입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            # UUID 토큰으로 인증
            token_obj = EmailVerificationToken.objects.get(token=token)

            # 이미 사용된 토큰 체크
            if token_obj.is_used:
                return Response(
                    {"error": "이미 사용된 토큰입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 만료 체크
            if token_obj.is_expired():
                return Response(
                    {"error": "토큰이 만료되었습니다. 다시 요청해주세요."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 인증 처리
            user = token_obj.user
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])

            # 토큰 사용 처리
            token_obj.mark_as_used()

            # 로그 업데이트
            EmailLog.objects.filter(token=token_obj).update(status="verified", verified_at=timezone.now())

            return Response({"message": "이메일 인증이 완료되었습니다!"}, status=status.HTTP_200_OK)

        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"error": "유효하지 않은 토큰입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def post(self, request: Request) -> Response:
        """6자리 코드로 인증 (POST 요청)"""
        if not request.user.is_authenticated:
            return Response({"error": "로그인이 필요합니다."}, status=status.HTTP_401_UNAUTHORIZED)

        code = request.data.get("code")

        if not code:
            return Response(
                {"error": "인증 코드가 제공되지 않았습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 대문자로 변환
        code = code.upper()

        try:
            token_obj = EmailVerificationToken.objects.get(user=request.user, verification_code=code, is_used=False)

            # 만료 체크
            if token_obj.is_expired():
                return Response(
                    {"error": "인증 코드가 만료되었습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 인증 처리
            user = token_obj.user
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])

            # 토큰 사용 처리
            token_obj.mark_as_used()

            # 로그 업데이트
            EmailLog.objects.filter(token=token_obj).update(status="verified", verified_at=timezone.now())

            return Response({"message": "이메일 인증이 완료되었습니다."}, status=status.HTTP_200_OK)

        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"error": "유효하지 않은 인증 코드입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ResendVerificationEmailView(APIView):
    """이메일 재발송 API"""

    permission_classes = [IsAuthenticated]

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
            {
                "message": "인증 이메일이 재발송 중입니다. 잠시 후 이메일을 확인해주세요.",
                "verification_code": token.verification_code,  # 테스트용
            },
            status=status.HTTP_200_OK,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_verification_status(request: Request) -> Response:
    """이메일 인증 상태 확인 API"""
    user = request.user

    # 최신 토큰 정보
    latest_token = EmailVerificationToken.objects.filter(user=user).order_by("-created_at").first()

    response_data = {"is_verified": user.is_email_verified, "email": user.email}

    if not user.is_email_verified and latest_token:
        response_data.update(
            {
                "pending_verification": True,
                "token_expired": latest_token.is_expired(),
                "can_resend": (latest_token.can_resend() if not latest_token.is_used else True),
            }
        )

    return Response(response_data, status=status.HTTP_200_OK)
