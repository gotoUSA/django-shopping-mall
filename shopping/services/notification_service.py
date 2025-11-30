"""알림 서비스 레이어

알림 관련 비즈니스 로직을 처리합니다.

현업에서 널리 사용되는 서비스 레이어 패턴 적용:
1. 단일 책임 원칙 (SRP): 알림 관련 로직만 담당
2. 트랜잭션 경계 명확화: @transaction.atomic 데코레이터로 트랜잭션 관리
3. 예외 처리 표준화: NotificationServiceError로 비즈니스 로직 예외 통합
4. 로깅 표준화: 구조화된 로깅으로 디버깅 및 모니터링 용이

사용 예시:
    # 읽지 않은 알림 조회
    result = NotificationService.get_unread(user)

    # 읽음 처리
    count = NotificationService.mark_as_read(user, notification_ids=[1, 2])

    # 알림 생성
    notification = NotificationService.create(
        user=user,
        notification_type="order",
        title="주문 완료",
        message="주문이 완료되었습니다.",
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import QuerySet

if TYPE_CHECKING:
    from ..models.user import User

from ..models.notification import Notification
from .base import ServiceError, log_service_call

logger = logging.getLogger(__name__)


class NotificationServiceError(ServiceError):
    """알림 서비스 관련 에러"""

    def __init__(self, message: str, code: str = "NOTIFICATION_ERROR", details: dict | None = None):
        super().__init__(message, code, details)


# ===== Data Transfer Objects (DTO) =====


@dataclass
class UnreadResult:
    """읽지 않은 알림 조회 결과"""

    count: int
    notifications: list[Notification]


@dataclass
class MarkReadResult:
    """읽음 처리 결과"""

    count: int
    message: str


@dataclass
class ClearResult:
    """알림 삭제 결과"""

    count: int
    message: str


class NotificationService:
    """
    알림 관련 비즈니스 로직 서비스

    책임:
    - 알림 조회 (전체, 읽지 않은 알림)
    - 읽음 처리 (개별, 전체)
    - 알림 삭제
    - 알림 생성

    Note:
        모든 메서드는 stateless하게 설계되어 있으며,
        필요한 상태는 인자로 전달받습니다.
    """

    # ===== 정책 상수 =====
    PREVIEW_LIMIT = 5  # 미리보기 알림 개수

    # ===== 알림 조회 =====

    @staticmethod
    @log_service_call
    def get_queryset(user: User) -> QuerySet[Notification]:
        """
        사용자의 알림 쿼리셋 반환

        Args:
            user: 사용자

        Returns:
            QuerySet: 알림 쿼리셋 (최신순 정렬)
        """
        return Notification.objects.filter(user=user).order_by("-created_at")

    @staticmethod
    @log_service_call
    def get_unread(user: User, limit: int | None = None) -> UnreadResult:
        """
        읽지 않은 알림 조회

        Args:
            user: 사용자
            limit: 최대 개수 (기본: PREVIEW_LIMIT)

        Returns:
            UnreadResult: 읽지 않은 알림 정보
        """
        limit = limit or NotificationService.PREVIEW_LIMIT

        unread_qs = NotificationService.get_queryset(user).filter(is_read=False)
        count = unread_qs.count()

        # 최근 N개만 미리보기
        notifications = list(unread_qs[:limit])

        return UnreadResult(count=count, notifications=notifications)

    @staticmethod
    @log_service_call
    def get_by_id(user: User, notification_id: int) -> Notification:
        """
        알림 단일 조회

        Args:
            user: 사용자
            notification_id: 알림 ID

        Returns:
            Notification: 알림 객체

        Raises:
            NotificationServiceError: 알림이 없는 경우
        """
        try:
            return Notification.objects.get(id=notification_id, user=user)
        except Notification.DoesNotExist:
            raise NotificationServiceError(
                "알림을 찾을 수 없습니다.",
                code="NOTIFICATION_NOT_FOUND",
                details={"notification_id": notification_id},
            )

    # ===== 읽음 처리 =====

    @staticmethod
    @log_service_call
    @transaction.atomic
    def mark_as_read(user: User, notification_ids: list[int] | None = None) -> MarkReadResult:
        """
        알림 읽음 처리

        Args:
            user: 사용자
            notification_ids: 알림 ID 목록 (None이면 전체 읽음 처리)

        Returns:
            MarkReadResult: 읽음 처리 결과
        """
        queryset = NotificationService.get_queryset(user).filter(is_read=False)

        # 특정 알림만 처리
        if notification_ids:
            queryset = queryset.filter(id__in=notification_ids)

        count = queryset.update(is_read=True)

        if count == 0:
            message = "읽지 않은 알림이 없습니다."
        else:
            message = f"{count}개의 알림을 읽음 처리했습니다."

        logger.info(
            "[Notification] 읽음 처리 | user_id=%d, count=%d, ids=%s",
            user.id,
            count,
            notification_ids or "all",
        )

        return MarkReadResult(count=count, message=message)

    @staticmethod
    @log_service_call
    def mark_single_as_read(notification: Notification) -> bool:
        """
        단일 알림 읽음 처리

        Args:
            notification: 알림 객체

        Returns:
            bool: 읽음 처리 여부 (이미 읽은 경우 False)
        """
        if notification.is_read:
            return False

        notification.mark_as_read()

        logger.info(
            "[Notification] 단일 읽음 처리 | notification_id=%d, user_id=%d",
            notification.id,
            notification.user_id,
        )

        return True

    # ===== 알림 삭제 =====

    @staticmethod
    @log_service_call
    @transaction.atomic
    def clear_read(user: User) -> ClearResult:
        """
        읽은 알림 전체 삭제

        Args:
            user: 사용자

        Returns:
            ClearResult: 삭제 결과
        """
        read_qs = NotificationService.get_queryset(user).filter(is_read=True)
        count = read_qs.count()
        read_qs.delete()

        message = f"{count}개의 알림을 삭제했습니다."

        logger.info("[Notification] 읽은 알림 삭제 | user_id=%d, count=%d", user.id, count)

        return ClearResult(count=count, message=message)

    @staticmethod
    @log_service_call
    @transaction.atomic
    def delete_by_id(user: User, notification_id: int) -> str:
        """
        단일 알림 삭제

        Args:
            user: 사용자
            notification_id: 알림 ID

        Returns:
            str: 삭제된 알림 제목

        Raises:
            NotificationServiceError: 알림이 없는 경우
        """
        notification = NotificationService.get_by_id(user, notification_id)
        title = notification.title
        notification.delete()

        logger.info(
            "[Notification] 알림 삭제 | user_id=%d, notification_id=%d",
            user.id,
            notification_id,
        )

        return title

    # ===== 알림 생성 =====

    @staticmethod
    @log_service_call
    @transaction.atomic
    def create(
        user: User,
        notification_type: str,
        title: str,
        message: str = "",
        related_object_id: int | None = None,
        url: str = "",
    ) -> Notification:
        """
        알림 생성

        Args:
            user: 사용자
            notification_type: 알림 유형 (order, point, system 등)
            title: 알림 제목
            message: 알림 내용
            related_object_id: 관련 객체 ID
            url: 이동 URL

        Returns:
            Notification: 생성된 알림
        """
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            related_object_id=related_object_id,
            url=url,
        )

        logger.info(
            "[Notification] 알림 생성 | user_id=%d, type=%s, title=%s",
            user.id,
            notification_type,
            title,
        )

        return notification

    @staticmethod
    @log_service_call
    @transaction.atomic
    def bulk_create(
        users: list[User],
        notification_type: str,
        title: str,
        message: str = "",
    ) -> int:
        """
        다수 사용자에게 알림 일괄 생성

        Args:
            users: 사용자 목록
            notification_type: 알림 유형
            title: 알림 제목
            message: 알림 내용

        Returns:
            int: 생성된 알림 수
        """
        notifications = [
            Notification(
                user=user,
                notification_type=notification_type,
                title=title,
                message=message,
            )
            for user in users
        ]

        created = Notification.objects.bulk_create(notifications)

        logger.info(
            "[Notification] 일괄 알림 생성 | count=%d, type=%s, title=%s",
            len(created),
            notification_type,
            title,
        )

        return len(created)

    # ===== 통계 =====

    @staticmethod
    @log_service_call
    def get_unread_count(user: User) -> int:
        """
        읽지 않은 알림 개수 조회

        Args:
            user: 사용자

        Returns:
            int: 읽지 않은 알림 개수
        """
        return Notification.objects.filter(user=user, is_read=False).count()
