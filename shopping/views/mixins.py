"""View mixins for common functionality"""

import logging

from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class EmailVerificationRequiredMixin:
    """
    이메일 인증이 필요한 View에서 사용하는 Mixin

    이메일 인증이 완료되지 않은 사용자의 요청을 차단합니다.
    """

    def check_email_verification(self, request, action_name="이 작업을"):
        """
        이메일 인증 여부를 확인하고, 미인증 시 에러 응답을 반환합니다.

        Args:
            request: HTTP 요청 객체
            action_name: 수행하려는 작업 이름 (예: "결제를", "주문을")

        Returns:
            Response 또는 None: 미인증 시 에러 Response, 인증 완료 시 None
        """
        if not request.user.is_email_verified:
            logger.warning(
                f"미인증 사용자의 {action_name} 시도: "
                f"user_id={request.user.id}, email={request.user.email}"
            )
            return Response(
                {
                    "error": "이메일 인증이 필요합니다.",
                    "message": f"{action_name} 완료하려면 먼저 이메일 인증을 완료해주세요.",
                    "detail": "이메일 인증 후 모든 기능을 사용하실 수 있습니다.",
                    "verification_required": True,
                    "verification_url": "/api/email-verification/send/",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None
