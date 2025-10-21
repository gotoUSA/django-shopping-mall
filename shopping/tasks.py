"""
Celery 비동기 작업 정의
포인트 만료 처리 및 알림 발송
"""

from django.utils import timezone

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


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
    from django.contrib.auth import get_user_model

    from shopping.services.point_service import PointService

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
    from datetime import timedelta

    from shopping.models.point import PointHistory

    cutoff_date = timezone.now() - timedelta(days=days)

    try:
        # 만료된 포인트 중 오래된 것 삭제
        deleted_count, _ = PointHistory.objects.filter(type="expire", created_at__lt=cutoff_date).delete()

        logger.info(f"오래된 포인트 이력 삭제: {deleted_count}건")

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "cutoff_date": cutoff_date.isoformat(),
        }

    except Exception as e:
        logger.error(f"포인트 이력 정리 실패: {str(e)}")
        return {"status": "error", "message": str(e)}
