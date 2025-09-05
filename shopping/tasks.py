"""
Celery 비동기 작업 정의
포인트 만료 처리 및 알림 발송
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from typing import Optional
import traceback

logger = get_task_logger(__name__)


@shared_task(
    name="shopping.tasks.expire_points_task",
    max_retries=3,
    default_retry_delay=60,  # 1분 후 재시도
)
def expire_points_task() -> dict:
    """
    포인트 만료 처리 태스크
    매일 새벽 2시에 실행됨

    Returns:
        처리 결과 딕셔너리
    """
    from shopping.services.point_service import PointService

    logger.info(f"포인트 만료 처리 시작: {timezone.now()}")

    try:
        service = PointService()
        expired_count = service.expire_points()

        result = {
            "status": "success",
            "expired_count": expired_count,
            "executed_at": timezone.now().isoformat(),
            "message": f"{expired_count}건의 포인트가 만료 처리되었습니다.",
        }

        logger.info(f"포인트 만료 처리 완료: {result}")
        return result

    except Exception as e:
        logger.error(f"포인트 만료 처리 실패: {str(e)}\n{traceback.format_exc()}")

        # 재시도
        raise expire_points_task.retry(exc=e)


@shared_task(
    name="shopping.tasks.send_expiry_notification_task",
    max_retries=3,
    default_retry_delay=60,
)
def send_expiry_notification_task() -> dict:
    """
    포인트 만료 예정 알림 발송 태스크
    매일 오전 10시에 실행됨

    Returns:
        처리 결과 딕셔너리
    """
    from shopping.services.point_service import PointService

    logger.info(f"포인트 만료 알림 발송 시작: {timezone.now()}")

    try:
        service = PointService()
        notification_count = service.send_expiry_notifications()

        result = {
            "status": "success",
            "notification_count": notification_count,
            "executed_at": timezone.now().isoformat(),
            "message": f"{notification_count}명에게 만료 예정 알림을 발송했습니다.",
        }

        logger.info(f"포인트 만료 알림 발송 완료: {result}")
        return result

    except Exception as e:
        logger.error(f"포인트 만료 알림 발송 실패: {str(e)}\n{traceback.format_exc()}")
        raise send_expiry_notification_task.retry(exc=e)


@shared_task(name="shopping.tasks.process_single_user_points", queue="points")
def process_single_user_points(user_id: int) -> dict:
    """
    특정 사용자의 포인트 만료 처리
    관리자가 수동으로 실행하거나 특정 이벤트 시 사용

    Args:
        user_id: 사용자 ID

    Returns:
        처리 결과
    """
    from shopping.services.point_service import PointService
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        user = User.objects.get(id=user_id)
        service = PointService()

        # 해당 사용자의 만료 포인트만 처리
        expired_points = service.get_expired_points()
        user_expired = [p for p in expired_points if p.user_id == user_id]

        expired_count = 0
        for point in user_expired:
            # 개별 처리 로직...
            expired_count += 1

        return {
            "status": "success",
            "user": user.username,
            "expired_count": expired_count,
        }
    except User.DoesNotExist:
        logger.error(f"사용자를 찾을 수 없음: ID={user_id}")
        return {"status": "error", "message": f"User {user_id} not found"}
    except Exception as e:
        logger.error(f"사용자 포인트 처리 실패: User={user_id}, Error={str(e)}")
        return {"status": "error", "message": str(e)}


@shared_task(
    name="shopping.tasks.send_email_notification",
    queue="notifications",
    max_retries=5,
    default_retry_delay=120,  # 2분 후 재시도
)
def send_email_notification(
    email: str, subject: str, message: str, html_message: Optional[str] = None
) -> bool:
    """
    이메일 알림 발송 태스크

    Args:
        email: 수신자 이메일
        subject: 제목
        message: 본문 (텍스트)
        html_message: HTML 본문 (선택)

    Returns:
        발송 성공 여부
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=(
                settings.DEFAULT_FROM_EMAIL
                if hasattr(settings, "DEFAULT_FROM_EMAIL")
                else "noreply@shopping.com"
            ),
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"이메일 발송 성공: {email} - {subject}")
        return True

    except Exception as e:
        logger.error(f"이메일 발송 실패: {email} - {str(e)}")

        # 재시도
        raise send_email_notification.retry(exc=e)


@shared_task(name="shopping.tasks.test_periodic_task", ignore_result=True)
def cleanup_old_point_histories(days: int = 730) -> dict:
    """
    오래된 포인트 이력 정리
    기본 2년 이상 된 만료 이력 삭제

    Args:
        days: 보관 기간 (일)

    Returns:
        삭제 결과
    """
    from shopping.models.point import PointHistory
    from datetime import timedelta

    cutoff_date = timezone.now() - timedelta(days=days)

    try:
        # 만료된 포인트 중 오래된 것 삭제
        deleted_count, _ = PointHistory.objects.filter(
            type="expire", created_at__lt=cutoff_date
        ).delete()

        logger.info(f"오래된 포인트 이력 삭제: {deleted_count}건")

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "cutoff_date": cutoff_date.isoformat(),
        }

    except Exception as e:
        logger.error(f"포인트 이력 정리 실패: {str(e)}")
        return {"status": "error", "message": str(e)}
