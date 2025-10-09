import logging
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from shopping.models.email_verification import EmailVerificationToken, EmailLog
from shopping.models.user import User

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,  # 최대 3번 재시도
    default_retry_delay=60,  # 실패 시 60초 후 재시도
    autoretry_for=(Exception,),  # 모든 예외에 대해 자동 재시도
)
def send_verification_email_task(self, user_id, token_id, is_resend=False):
    """
    이메일 인증 메일 발송 태스크 (비동기)

    Args:
        self: Celery task 인스턴스 (bind=True)
        user_id: 사용자 ID
        token_id: 인증 토큰 ID
        is_resend: 재발송 여부

    Returns:
        dict: 발송 결과 {'success': bool, 'message': str}
    """
    try:
        # 사용자 및 토큰 조회
        user = User.objects.get(id=user_id)
        token = EmailVerificationToken.objects.get(id=token_id)

        # 이메일 로그 조회 또는 생성
        email_log, created = EmailLog.objects.get_or_create(
            token=token,
            defaults={
                "user": user,
                "email_type": "verification",
                "recipient_email": user.email,
                "subject": "[쇼핑몰] 이메일 인증을 완료해주세요"
                + (" (재발송)" if is_resend else ""),
                "status": "pending",
            },
        )

        # 이미 발송 성공한 경우 중복 발송 방지
        if email_log.status == "send" and not is_resend:
            logger.info(f"이미 발송된 이메일입니다: {user.email}")
            return {
                "success": True,
                "message": "이미 발송된 이메일입니다.",
            }

        # 인증 URL 생성
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token.token}"

        # HTML 이메일 내용
        # HTML 이메일 내용
        html_message = render_to_string(
            "email/verification.html",
            {
                "user": user,
                "verification_url": verification_url,
                "verification_code": token.verification_code,
                "is_resend": is_resend,
            },
        )

        # 텍스트 버전
        plain_message = f"""
안녕하세요, {user.first_name}님!

{'요청하신 이메일 인증 메일을 다시 보내드립니다.' if is_resend else '회원가입을 환영합니다!'}

이메일 인증을 완료하려면 아래 링크를 클릭하거나 인증 코드를 입력해주세요.

인증 링크: {verification_url}
인증 코드: {token.verification_code}

이 링크와 코드는 24시간 동안 유효합니다.

{'이전에 받으신 인증 메일은 더 이상 유효하지 않습니다.' if is_resend else ''}

감사합니다.
쇼핑몰 팀 드림
"""

        # 이메일 발송
        send_mail(
            subject=email_log.subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )

        # 발송 성공 처리
        email_log.mark_as_sent()

        logger.info(
            f"✅ 이메일 발송 성공: {user.email} (토큰: {token.verification_code})"
        )

        return {
            "success": True,
            "message": "이메일이 성공적으로 발송되었습니다.",
            "recipient": user.email,
            "verification_code": token.verification_code,
        }

    except User.DoesNotExist:
        logger.error(f"❌ 사용자를 찾을 수 없습니다: user_id={user_id}")
        return {
            "success": False,
            "message": "사용자를 찾을 수 없습니다.",
        }

    except EmailVerificationToken.DoesNotExist:
        logger.error(f"❌ 토큰을 찾을 수 없습니다: token_id={token_id}")
        return {
            "success": False,
            "message": "토큰을 찾을 수 없습니다.",
        }

    except Exception as e:
        logger.error(
            f"❌ 이메일 발송 실패: {user.email if 'user' in locals() else 'unknown'} - {str(e)}"
        )

        # 이메일 로그 실패 처리
        if "email_log" in locals():
            email_log.mark_as_failed(str(e))

        # Celery 재시도 (max_retries까지)
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True)
def retry_failed_emails_task(self):
    """
    실패한 이메일 재발송 태스크 (주기적 실행)

    최근 24시간 이내 실패한 이메일 중,
    재시도 횟수가 3회 미만인 것만 재발송

    Returns:
        dict: 재시도 결과 통계
    """
    try:
        # 24시간 이내 실패한 이메일 로그 조회
        failed_logs = EmailLog.objects.filter(
            status="failed",
            created_at__gte=timezone.now() - timedelta(hours=24),
            email_type="verification",
        ).select_related("token", "user")

        retry_count = 0
        success_count = 0

        for email_log in failed_logs:
            # 토큰이 없거나 만료된 경우 스킵
            if not email_log.token or email_log.token.is_expired():
                logger.info(f"⏭️ 만료된 토큰 스킵: {email_log.recipient_email}")
                continue

            # 이미 인증된 경우 스킵
            if email_log.user and email_log.user.is_email_verified:
                logger.info(f"⏭️ 이미 인증됨 스킵: {email_log.recipient_email}")
                continue

            # 재발송 시도
            try:
                retry_count += 1

                # 비동기 태스크 호출
                result = send_verification_email_task.delay(
                    user_id=email_log.user.id,
                    token_id=email_log.token.id,
                    is_resend=True,
                )

                success_count += 1
                logger.info(f"🔄 재발송 예약 성공: {email_log.recipient_email}")

            except Exception as e:
                logger.error(
                    f"❌ 재발송 예약 실패: {email_log.recipient_email} - {str(e)}"
                )

        result = {
            "success": True,
            "total_failed": failed_logs.count(),
            "retry_attempted": retry_count,
            "retry_success": success_count,
        }

        logger.info(f"📊 실패 이메일 재시도 완료: {result}")
        return result

    except Exception as e:
        logger.error(f"❌ 실패 이메일 재시도 작업 실패: {str(e)}")
        return {
            "success": False,
            "message": str(e),
        }
