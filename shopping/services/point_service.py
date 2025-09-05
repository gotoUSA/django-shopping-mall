"""
포인트 관련 비즈니스 로직
FIFO 방식 포인트 사용 및 만료 처리
"""

from django.db import transaction
from django.db.models import Q, F, Sum
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
from typing import List, Dict, Optional
import logging

from shopping.models.point import PointHistory

User = get_user_model()
logger = logging.getLogger(__name__)


class PointService:
    """포인트 관련 서비스 클래스"""

    def get_expired_points(self) -> List[PointHistory]:
        """
        만료된 포인트 조회

        Returns:
            만료된 포인트 이력 리스트
        """
        now = timezone.now()

        # 만료되지 않은 적립 포인트 중 만료일이 지난 것들
        expired_points = (
            PointHistory.objects.filter(type="earn", expires_at__lte=now)
            .exclude(
                # 이미 만료 처리된 포인트 제외
                metadata__contains={"expired": True}
            )
            .select_related("user")
        )

        return list(expired_points)

    def get_expiring_points_soon(self, days: int = 7) -> List[PointHistory]:
        """
        곧 만료될 포인트 조회 (기본 7일 이내)

        Args:
            days: 만료 예정 일수

        Returns:
            만료 예정 포인트 리스트
        """
        now = timezone.now()
        target_date = now + timedelta(days=days)

        # 7일 이내 만료 예정이고 아직 알림 안 보낸 포인트
        expiring_points = (
            PointHistory.objects.filter(
                type="earn",
                expires_at__gt=now,  # 아직 만료되지 않음
                expires_at__lte=target_date,  # 7일 이내 만료
            )
            .exclude(metadata__contains={"expiry_notified": True})
            .select_related("user")
        )

        return list(expiring_points)

    @transaction.atomic
    def expire_points(self) -> int:
        """
        만료된 포인트 일괄 처리

        Returns:
            처리된 포인트 건수
        """
        expired_points = self.get_expired_points()
        expired_count = 0

        for point_history in expired_points:
            try:
                # 남은 포인트 계산
                remaining = self.get_remaining_points(point_history)

                if remaining > 0:
                    # 사용자 포인트 차감
                    user = point_history.user
                    user.points = max(0, user.points - remaining)
                    user.save(update_fields=["points"])

                    # 만료 이력 생성
                    PointHistory.create_history(
                        user=user,
                        points=-remaining,
                        type="expire",
                        description=f"포인트 만료 (적립일: {point_history.created_at.date()})",
                        metadata={
                            "original_history_id": point_history.id,
                            "original_points": point_history.points,
                            "expired_amount": remaining,
                        },
                    )

                    # 원본 이력에 만료 표시
                    point_history.metadata["expired"] = True
                    point_history.metadata["expired_at"] = timezone.now().isoformat()
                    point_history.metadata["expired_amount"] = remaining
                    point_history.save(update_fields=["metadata"])

                    expired_count += 1

                    logger.info(
                        f"포인트 만료 처리: User={user.username}, "
                        f"Amount={remaining}, HistoryID={point_history.id}"
                    )

            except Exception as e:
                logger.error(
                    f"포인트 만료 처리 실패: HistoryID={point_history.id}, "
                    f"Error={str(e)}"
                )
                continue

        return expired_count

    def get_remaining_points(self, point_history: PointHistory) -> int:
        """
        특정 적립 건의 남은 포인트 계산

        Args:
            point_history: 포인트 적립 이력

        Returns:
            남은 포인트
        """
        if point_history.type != "earn":
            return 0

        # 메타데이터에서 사용된 포인트 확인
        used_amount = point_history.metadata.get("used_amount", 0)
        remaining = point_history.points - used_amount

        return max(0, remaining)

    @transaction.atomic
    def use_points_fifo(self, user, amount: int) -> Dict:
        """
        FIFO 방식으로 포인트 사용

        Args:
            user: 사용자
            amount: 사용할 포인트

        Returns:
            {
                'success': bool,
                'used_details': [{'history_id': int, 'amount': int}],
                'message': str
            }
        """
        if amount <= 0:
            return {
                "success": False,
                "used_details": [],
                "message": "사용할 포인트는 0보다 커야 합니다.",
            }

        if user.points < amount:
            return {
                "success": False,
                "used_details": [],
                "message": "포인트가 부족합니다.",
            }

        # 사용 가능한 포인트 조회 (만료일 순서)
        available_points = (
            PointHistory.objects.filter(
                user=user,
                type="earn",
                expires_at__gt=timezone.now(),  # 만료되지 않은 것만
            )
            .exclude(metadata__contains={"expired": True})
            .order_by("expires_at", "created_at")
        )

        used_details = []
        remaining_to_use = amount

        for point_history in available_points:
            if remaining_to_use <= 0:
                break

            # 이 적립 건에서 사용 가능한 포인트
            available = self.get_remaining_points(point_history)

            if available <= 0:
                continue

            # 사용할 포인트 계산
            use_from_this = min(available, remaining_to_use)

            # 메타데이터 업데이트
            if "used_amount" not in point_history.metadata:
                point_history.metadata["used_amount"] = 0
            metadata = point_history.metadata.copy()
            metadata["used_amount"] = metadata.get("used_amount", 0) + use_from_this

            # 사용 내역 추가
            if "usage_history" not in point_history.metadata:
                point_history.metadata["usage_history"] = []
            point_history.metadata["usage_history"].append(
                {"amount": use_from_this, "used_at": timezone.now().isoformat()}
            )

            point_history.metadata = metadata
            point_history.save()

            used_details.append(
                {
                    "history_id": point_history.id,
                    "amount": use_from_this,
                    "expires_at": point_history.expires_at.isoformat(),
                }
            )

            remaining_to_use -= use_from_this

        # 사용자 포인트 차감
        user.points -= amount
        user.save(update_fields=["points"])

        # 사용 이력 생성
        PointHistory.create_history(
            user=user,
            points=-amount,
            type="use",
            description=f"포인트 사용 (FIFO)",
            metadata={"used_details": used_details},
        )

        return {
            "success": True,
            "used_details": used_details,
            "message": f"{amount} 포인트를 사용했습니다.",
        }

    def send_expiry_notifications(self) -> int:
        """
        만료 예정 포인트 알림 발송

        Returns:
            알림 발송 건수
        """
        from shopping.tasks import send_email_notification

        expiring_points = self.get_expiring_points_soon(days=7)

        # 사용자별로 그룹화
        user_points = {}
        for point in expiring_points:
            user_id = point.user_id
            if user_id not in user_points:
                user_points[user_id] = {"user": point.user, "points": [], "total": 0}
            remaining = self.get_remaining_points(point)
            if remaining > 0:
                user_points[user_id]["points"].append(point)
                user_points[user_id]["total"] += remaining

        notification_count = 0

        for user_data in user_points.values():
            user = user_data["user"]
            total_expiring = user_data["total"]

            if total_expiring > 0:
                # 이메일 발송
                subject = f"포인트 만료 예정 안내 - {total_expiring:,} 포인트"
                message = self._create_expiry_notification_message(
                    user, user_data["points"], total_expiring
                )

                try:
                    send_email_notification(user.email, subject, message)

                    # 알림 발송 표시
                    for point in user_data["points"]:
                        point.metadata["expiry_notified"] = True
                        point.metadata["notified_at"] = timezone.now().isoformat()
                        point.save(update_fields=["metadata"])

                    notification_count += 1

                    logger.info(
                        f"포인트 만료 알림 발송: User={user.username}, "
                        f"points={total_expiring}"
                    )

                except Exception as e:
                    logger.error(
                        f"알림 발송 실패: User={user.username}, " f"Error={str(e)}"
                    )
        return notification_count

    def _create_expiry_notification_message(
        self, user, points: List[PointHistory], total: int
    ) -> str:
        """
        만료 알림 메세지 생성

        Args:
            user: 사용자
            points: 만료 예정 포인트 리스트
            total: 총 만료 예정 포인트
        Returns:
            이메일 메시지
        """
        message = f"""
안녕하세요, {user.username}님!

보유하신 포인트 중 일부가 곧 만료될 예정입니다.

[만료 예정 포인트]
총 {total:,} 포인트

[상세 내역]
"""

        for point in points:
            remaining = self.get_remaining_points(point)
            expiry_date = point.expires_at.strftime("%Y년 %m월 %d일")
            message += f"- {remaining:,}P (만료일: {expiry_date})\n"

        message += f"""

만료되기 전에 사용해 주세요!

감사합니다.
쇼핑몰 드림
"""

        return message
