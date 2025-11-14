from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopping.models.email_verification import EmailLog
from shopping.models.password_reset import PasswordResetToken
from shopping.serializers.password_reset_serializers import PasswordResetConfirmSerializer, PasswordResetRequestSerializer
from shopping.tasks.email_tasks import send_email_task

User = get_user_model()


class PasswordResetRequestView(APIView):
    """
    비밀번호 재설정 요청 (이메일 발송)

    POST /api/auth/password/reset/request/

    인증 불필요
    """

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        """
        비밀번호 재설정 이메일 발송

        요청:
        {
            "email": "user@example.com"
        }

        응답:
        {
            "message": "비밀번호 재설정 이메일이 발송되었습니다."
        }

        보안 고려사항:
        - 존재하지 않는 이메일이어도 같은 메시지 반환 (계정 존재 여부 노출 방지)
        - 실제 이메일은 존재하는 계정에만 발송
        """
        serializer = PasswordResetRequestSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data.get("user")

            # 사용자가 존재하는 경우에만 이메일 발송
            if user:
                # 토큰 생성
                token = PasswordResetToken.objects.create(user=user)

                # 재설정 링크 생성
                frontend_url = settings.FRONTEND_URL
                reset_link = f"{frontend_url}/password-reset?token={token.token}"

                # 이메일 발송 (비동기)
                send_email_task.delay(
                    subject="[Django 쇼핑몰] 비밀번호 재설정 안내",
                    message=f"""
안녕하세요 {user.username}님,

비밀번호 재설정을 요청하셨습니다.
아래 링크를 클릭하여 새로운 비밀번호를 설정해주세요.

재설정 링크: {reset_link}

※ 이 링크는 24시간 동안 유효합니다.
※ 본인이 요청하지 않았다면 이 이메일을 무시하세요.

감사합니다.
                    """.strip(),
                    recipient_list=[user.email],
                    user_id=user.id,
                    email_type="password_reset",
                )

                # 로그 생성
                EmailLog.objects.create(
                    user=user,
                    email_type="password_reset",
                    recipient_email=user.email,
                    subject="[Django 쇼핑몰] 비밀번호 재설정 안내",
                    status="pending",
                )

            # 보안: 사용자 존재 여부와 관계없이 같은 메시지 반환
            return Response(
                {
                    "message": "해당 이메일로 비밀번호 재설정 링크가 발송되었습니다. 이메일을 확인해주세요.",
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(APIView):
    """
    비밀번호 재설정 확인 (새 비밀번호 설정)

    POST /api/auth/password/reset/confirm/

    인증 불필요
    """

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        """
        토큰을 사용하여 새 비밀번호 설정

        요청:
        {
            "token": "uuid-token-here",
            "new_password": "newpass123!",
            "new_password2": "newpass123!"
        }

        응답:
        {
            "message": "비밀번호가 성공적으로 변경되었습니다. 새 비밀번호로 로그인해주세요."
        }
        """
        serializer = PasswordResetConfirmSerializer(data=request.data)

        if serializer.is_valid():
            # 비밀번호 변경
            user = serializer.save()

            return Response(
                {
                    "message": "비밀번호가 성공적으로 변경되었습니다. 새 비밀번호로 로그인해주세요.",
                    "username": user.username,  # 로그인 시 사용
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
