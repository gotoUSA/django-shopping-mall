"""
Celery 태스크 패키지
모든 태스크를 여기서 임포트하여 Celery가 자동으로 발견할 수 있게 함
"""

from .email_tasks import (
    send_verification_email_task,
    retry_failed_emails_task,
)

from .cleanup_tasks import (
    delete_unverified_users_task,
    cleanup_old_email_logs_task,
    cleanup_used_tokens_task,
    cleanup_expired_tokens_task,
)

from .point_tasks import (
    expire_points_task,
    send_expiry_notification_task,
    send_email_notification,
)


__all__ = [
    # 이메일 태스크
    "send_verification_email_task",
    "retry_failed_emails_task",
    # 정리 태스크
    "delete_unverified_users_task",
    "cleanup_old_email_logs_task",
    "cleanup_used_tokens_task",
    "cleanup_expired_tokens_task",
    # 포인트 태스크
    "expire_points_task",
    "send_expiry_notification_task",
    "send_email_notification",
]
