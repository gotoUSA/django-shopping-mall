from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from celery import Task, shared_task
from django.utils import timezone

from shopping.models.email_verification import EmailLog, EmailVerificationToken
from shopping.models.user import User

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def delete_unverified_users_task(self: Task, days: int = 7) -> dict[str, Any]:
    """
    미인증 계정 자동 삭제 태스크

    조건:
    - 회원가입 후 N일 경과 (기본 7일)
    - 이메일 인증 미완료
    - 주문 이력 없음

    Args:
        self: Celery task 인스턴스
        days: 삭제 기준 일수 (기본 7일)

    Returns:
        dict: 삭제 결과 통계
    """
    try:
        # 삭제 기준 날짜 계산
        cutoff_date = timezone.now() - timedelta(days=days)

        # 미인증 사용자 조회
        unverified_users = User.objects.filter(
            is_email_verified=False,
            date_joined__lt=cutoff_date,
        ).select_related()

        # 주문 이력이 있는 사용자 제외
        users_to_delete = []
        users_to_keep = []

        for user in unverified_users:
            # 주문이 있으면 유지
            if hasattr(user, "orders") and user.orders.exists():
                users_to_keep.append(user.email)
                logger.info(f"⏭️ 주문 이력 있음, 유지: {user.email}")
                continue

            users_to_delete.append(user)

        # 삭제 전 로그 기록
        delete_count = len(users_to_delete)
        deleted_emails = [user.email for user in users_to_delete]

        if users_to_delete:
            # 일괄 삭제 (연관된 토큰, 로그도 자동 삭제됨 - CASCADE)
            User.objects.filter(id__in=[user.id for user in users_to_delete]).delete()

            logger.info(f"🗑️ 미인증 계정 {delete_count}개 삭제 완료")
            logger.info(f"삭제된 계정: {deleted_emails}")
        else:
            logger.info("✅ 삭제할 미인증 계정이 없습니다.")

        result = {
            "success": True,
            "total_unverified": unverified_users.count(),
            "deleted_count": delete_count,
            "kept_count": len(users_to_keep),
            "deleted_emails": deleted_emails,
            "kept_emails": users_to_keep,
            "cutoff_date": cutoff_date.isoformat(),
        }

        logger.info(f"📊 미인증 계정 정리 완료: {result}")
        return result

    except Exception as e:
        logger.error(f"❌ 미인증 계정 삭제 실패: {str(e)}")
        return {
            "success": False,
            "message": str(e),
        }


@shared_task(bind=True)
def cleanup_old_email_logs_task(self: Task, days: int = 90) -> dict[str, Any]:
    """
    오래된 이메일 로그 정리 태스크

    조건:
    - N일(기본 90일) 이상 경과한 로그
    - 'sent', 'verified', 'failed' 상태만 삭제
    - 'pending' 상태는 유지 (아직 처리 중)

    Args:
        self: Celery task 인스턴스
        days: 삭제 기준 일수 (기본 90일)

    Returns:
        dict: 삭제 결과 통계
    """
    try:
        # 삭제 기준 날짜 계산
        cutoff_date = timezone.now() - timedelta(days=days)

        # 삭제 전 통계 먼저 계산
        status_counts = {}
        for status in ["send", "verified", "failed"]:
            count = EmailLog.objects.filter(
                created_at__lt=cutoff_date,
                status=status,
            ).count()
            status_counts[status] = count

        # 오래된 이메일 로그 조회
        old_logs = EmailLog.objects.filter(
            created_at__lt=cutoff_date,
            status__in=["sent", "verified", "failed"],  # pending은 제외
        )

        total_count = old_logs.count()

        # 일괄 삭제
        if total_count > 0:
            old_logs.delete()
            logger.info(f"🗑️ 오래된 이메일 로그 {total_count}개 삭제 완료")
        else:
            logger.info("✅ 삭제할 오래된 이메일 로그가 없습니다.")

        result = {
            "success": True,
            "deleted_count": total_count,
            "status_counts": status_counts,
            "cutoff_date": cutoff_date.isoformat(),
        }

        logger.info(f"📊 이메일 로그 정리 완료: {result}")
        return result

    except Exception as e:
        logger.error(f"❌ 이메일 로그 정리 실패: {str(e)}")
        return {
            "success": False,
            "message": str(e),
        }


@shared_task(bind=True)
def cleanup_used_tokens_task(self: Task, days: int = 30) -> dict[str, Any]:
    """
    사용된 인증 토큰 정리 태스크

    조건:
    - N일(기본 30일) 이상 경과
    - 이미 사용됨 (is_used=True)

    Args:
        self: Celery task 인스턴스
        days: 삭제 기준 일수 (기본 30일)

    Returns:
        dict: 삭제 결과 통계
    """
    try:
        # 삭제 기준 날짜 계산
        cutoff_date = timezone.now() - timedelta(days=days)

        # 사용된 오래된 토큰 조회
        used_tokens = EmailVerificationToken.objects.filter(
            is_used=True,
            used_at__lt=cutoff_date,
        )

        # 삭제 전 통계
        total_count = used_tokens.count()

        # 일괄 삭제
        if total_count > 0:
            used_tokens.delete()
            logger.info(f"🗑️ 사용된 토큰 {total_count}개 삭제 완료")
        else:
            logger.info("✅ 삭제할 사용된 토큰이 없습니다.")

        result = {
            "success": True,
            "deleted_count": total_count,
            "cutoff_date": cutoff_date.isoformat(),
        }

        logger.info(f"📊 사용된 토큰 정리 완료: {result}")
        return result

    except Exception as e:
        logger.error(f"❌ 사용된 토큰 정리 실패: {str(e)}")
        return {
            "success": False,
            "message": str(e),
        }


@shared_task(bind=True)
def cleanup_expired_tokens_task(self: Task) -> dict[str, Any]:
    """
    만료된 미사용 토큰 정리 태스크

    조건:
    - 24시간 이상 경과
    - 미사용 (is_used=False)

    Returns:
        dict: 삭제 결과 통계
    """
    try:
        # 24시간 이전 생성된 토큰
        cutoff_date = timezone.now() - timedelta(hours=24)

        # 만료된 미사용 토큰 조회
        expired_tokens = EmailVerificationToken.objects.filter(
            is_used=False,
            created_at__lt=cutoff_date,
        )

        # 삭제 전 통계
        total_count = expired_tokens.count()

        # 일괄 삭제
        if total_count > 0:
            expired_tokens.delete()
            logger.info(f"🗑️ 만료된 토큰 {total_count}개 삭제 완료")
        else:
            logger.info("✅ 삭제할 만료된 토큰이 없습니다.")

        result = {
            "success": True,
            "deleted_count": total_count,
            "cutoff_date": cutoff_date.isoformat(),
        }

        logger.info(f"📊 만료된 토큰 정리 완료: {result}")
        return result

    except Exception as e:
        logger.error(f"❌ 만료된 토큰 정리 실패: {str(e)}")
        return {
            "success": False,
            "message": str(e),
        }
