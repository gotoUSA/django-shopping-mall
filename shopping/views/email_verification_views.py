import uuid
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone

from shopping.models.email_verification import EmailVerificationToken, EmailLog
from shopping.serializers.email_verification_serializers import (
    SendVerificationEmailSerializer,
    VerifyEmailByTokenSerializer,
    VerifyEmailByCodeSerializer,
    ResendVerificationEmailSerializer,
)


class SendVerificationEmailView(APIView):
    """이메일 인증 발송 API"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SendVerificationEmailSerializer(
            data=request.data, context={"request": request}
        )

        if not serializer.is_valid():
            # 재발송 제한 에러인 경우 429 반환
            if "1분" in str(serializer.errors):
                return Response(
                    serializer.errors, status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        # 기존 미사용 토큰 무효화
        EmailVerificationToken.objects.filter(user=user, is_used=False).update(
            is_used=True
        )

        # 새 토큰 생성
        token = EmailVerificationToken.objects.create(user=user)

        # 이메일 로그 생성
        email_log = EmailLog.objects.create(
            user=user,
            email_type="verification",
            recipient_email=user.email,
            subject="[쇼핑몰] 이메일 인증을 완료해주세요",
            token=token,
            status="pending",
        )

        # 이메일 발송 (동기 방식 - 나중에 Celery로 변경)
        try:
            verification_url = (
                f"{settings.FRONTEND_URL}/verify-email?token={token.token}"
            )

            # HTML 이메일 내용
            html_message = render_to_string(
                "email/verification.html",
                {
                    "user": user,
                    "verification_url": verification_url,
                    "verification_code": token.verification_code,
                },
            )

            # 텍스트 버전
            plain_message = f"""
안녕하세요, {user.first_name}님!

이메일 인증을 완료하려면 아래 링크를 클릭하거나 인증 코드를 입력해주세요.

인증 링크: {verification_url}
인증 코드: {token.verification_code}

이 링크와 코드는 24시간 동안 유효합니다.

감사합니다.
쇼핑몰 팀 드림
"""

            send_mail(
                subject="[쇼핑몰] 이메일 인증을 완료해주세요",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )

            # 발송 성공 처리
            email_log.mark_as_sent()

            return Response(
                {
                    "message": "인증 이메일이 발송되었습니다. 이메일을 확인해주세요.",
                    "verification_code": token.verification_code,  # 테스트용
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            # 발송 실패 처리
            email_log.mark_as_failed(str(e))

            return Response(
                {"error": "이메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyEmailView(APIView):
    """이메일 인증 확인 API"""

    permission_classes = [AllowAny]

    def get(self, request):
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
            EmailLog.objects.filter(token=token_obj).update(
                status="verified", verified_at=timezone.now()
            )

            return Response(
                {"message": "이메일 인증이 완료되었습니다!"}, status=status.HTTP_200_OK
            )

        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"error": "유효하지 않은 토큰입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def post(self, request):
        """6자리 코드로 인증 (POST 요청)"""
        if not request.user.is_authenticated:
            return Response(
                {"error": "로그인이 필요합니다."}, status=status.HTTP_401_UNAUTHORIZED
            )

        code = request.data.get("code")

        if not code:
            return Response(
                {"error": "인증 코드가 제공되지 않았습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 대문자로 변환
        code = code.upper()

        try:
            token_obj = EmailVerificationToken.objects.get(
                user=request.user, verification_code=code, is_used=False
            )

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
            EmailLog.objects.filter(token=token_obj).update(
                status="verified", verified_at=timezone.now()
            )

            return Response(
                {"message": "이메일 인증이 완료되었습니다."}, status=status.HTTP_200_OK
            )

        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"error": "유효하지 않은 인증 코드입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ResendVerificationEmailView(APIView):
    """이메일 재발송 API"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ResendVerificationEmailSerializer(
            data=request.data, context={"request": request}
        )

        if not serializer.is_valid():
            # 재발송 제한 에러인 경우 429 반환
            if "1분" in str(serializer.errors):
                return Response(
                    serializer.errors, status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        # 기존 미사용 토큰 무효화
        EmailVerificationToken.objects.filter(user=user, is_used=False).update(
            is_used=True
        )

        # 새 토큰 생성
        token = EmailVerificationToken.objects.create(user=user)

        # 이메일 로그 생성
        email_log = EmailLog.objects.create(
            user=user,
            email_type="verification",
            recipient_email=user.email,
            subject="[쇼핑몰] 이메일 인증을 완료해주세요 (재발송)",
            token=token,
            status="pending",
        )

        # 이메일 발송
        try:
            verification_url = (
                f"{settings.FRONTEND_URL}/verify-email?token={token.token}"
            )

            html_message = render_to_string(
                "email/verification.html",
                {
                    "user": user,
                    "verification_url": verification_url,
                    "verification_code": token.verification_code,
                    "is_resend": True,  # 재발송 표시
                },
            )

            plain_message = f"""
안녕하세요, {user.first_name}님!

요청하신 이메일 인증 메일을 다시 보내드립니다.

인증 링크: {verification_url}
인증 코드: {token.verification_code}

이 링크와 코드는 24시간 동안 유효합니다.

이전에 받으신 인증 메일은 더 이상 유효하지 않습니다.

감사합니다.
쇼핑몰 팀 드림
"""

            send_mail(
                subject="[쇼핑몰] 이메일 인증을 완료해주세요 (재발송)",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )

            email_log.mark_as_sent()

            return Response(
                {
                    "message": "인증 이메일이 재발송되었습니다.",
                    "verification_code": token.verification_code,  # 테스트용
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            email_log.mark_as_failed(str(e))

            return Response(
                {"error": "이메일 발송에 실패했습니다."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_verification_status(request):
    """이메일 인증 상태 확인 API"""
    user = request.user

    # 최신 토큰 정보
    latest_token = (
        EmailVerificationToken.objects.filter(user=user).order_by("-created_at").first()
    )

    response_data = {"is_verified": user.is_email_verified, "email": user.email}

    if not user.is_email_verified and latest_token:
        response_data.update(
            {
                "pending_verification": True,
                "token_expired": latest_token.is_expired(),
                "can_resend": (
                    latest_token.can_resend() if not latest_token.is_used else True
                ),
            }
        )

    return Response(response_data, status=status.HTTP_200_OK)
