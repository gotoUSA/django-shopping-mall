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
)

__all__ = [
    # 이메일 태스크
    "send_verification_email_task",
    "retry_failed_emails_task",
    # 정리 태스크
    "delete_unverified_users_task",
    "cleanup_old_email_logs_task",
]
