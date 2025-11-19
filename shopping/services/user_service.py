"""사용자 서비스 레이어"""

import logging

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)


class UserServiceError(Exception):
    """사용자 서비스 관련 에러"""

    pass


class UserService:
    """사용자 관련 비즈니스 로직을 처리하는 서비스"""

    @staticmethod
    def send_verification_email(user, token) -> dict:
        """
        이메일 인증 발송 로직

        Args:
            user: 사용자 객체
            token: EmailVerificationToken 객체

        Returns:
            dict: 발송 결과 및 verification_code (DEBUG 모드에서만)
        """
        from shopping.tasks.email_tasks import send_verification_email_task

        logger.info(f"이메일 인증 발송 시작: user_id={user.id}, email={user.email}")

        # 비동기 이메일 발송 (Celery 태스크)
        send_verification_email_task.delay(
            user_id=user.id,
            token_id=token.id,
            is_resend=False,
        )

        result = {"message": "인증 이메일을 발송했습니다."}

        # DEBUG 모드에서만 verification_code 반환
        if settings.DEBUG:
            result["verification_code"] = token.verification_code
            logger.debug(f"DEBUG 모드: verification_code={token.verification_code}")

        logger.info(f"이메일 인증 발송 완료: user_id={user.id}")
        return result

    @staticmethod
    def create_tokens_for_user(user) -> dict:
        """
        사용자용 JWT 토큰 생성

        Args:
            user: 사용자 객체

        Returns:
            dict: access, refresh 토큰
        """
        refresh = RefreshToken.for_user(user)
        logger.info(f"JWT 토큰 생성: user_id={user.id}, username={user.username}")

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }

    @staticmethod
    def register_user(user) -> dict:
        """
        회원가입 후처리 로직 (토큰 생성 + 이메일 발송)

        Args:
            user: 생성된 사용자 객체

        Returns:
            dict: tokens, verification_result
        """
        from shopping.models.email_verification import EmailVerificationToken

        logger.info(f"회원가입 후처리 시작: user_id={user.id}, email={user.email}")

        # JWT 토큰 생성
        tokens = UserService.create_tokens_for_user(user)

        # 이메일 인증 토큰 생성
        verification_token = EmailVerificationToken.objects.create(user=user)
        logger.info(f"이메일 인증 토큰 생성: token_id={verification_token.id}")

        # 인증 이메일 발송
        verification_result = UserService.send_verification_email(user, verification_token)

        logger.info(f"회원가입 후처리 완료: user_id={user.id}")

        return {
            "tokens": tokens,
            "verification_result": verification_result,
        }
