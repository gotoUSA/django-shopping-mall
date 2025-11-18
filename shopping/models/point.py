from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

if TYPE_CHECKING:
    from shopping.models.order import Order
    from shopping.models.user import User


class PointHistory(models.Model):
    """
    포인트 이력 관리 모델
    사용자의 모든 포인트 변동 내역을 기록합니다.
    """

    # 포인트 이력 타입
    TYPE_CHOICES = [
        ("earn", "적립"),  # 구매 시 적립
        ("use", "사용"),  # 주문 시 사용
        ("cancel_refund", "취소환불"),  # 주문 취소로 인한 환불
        ("cancel_deduct", "취소차감"),  # 주문 취소로 인한 적립 포인트 차감
        ("expire", "만료"),  # 유효기간 만료
        ("admin_add", "관리자지급"),  # 관리자가 수동으로 지급
        ("admin_deduct", "관리자차감"),  # 관리자가 수동으로 차감
        ("event", "이벤트"),  # 이벤트 지급
    ]

    # 사용자
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="point_histories",
        verbose_name="사용자",
    )

    # 포인트 변동량 (양수: 적립, 음수: 사용/차감)
    points = models.IntegerField(verbose_name="포인트", help_text="양수는 적립, 음수는 사용/차감")

    # 변경 후 잔액
    balance = models.PositiveIntegerField(verbose_name="잔액", help_text="변경 후 포인트 잔액")

    # 포인트 타입
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="타입")

    # 관련 주문 (있는 경우)
    order = models.ForeignKey(
        "Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="point_histories",
        verbose_name="관련 주문",
    )

    # 설명
    description = models.CharField(max_length=255, verbose_name="설명", help_text="포인트 변동 사유")

    # 유효기간 (적립 포인트의 경우)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="만료일시",
        help_text="적립 포인트의 유효기간",
    )

    # 메타 데이터 (추가 정보 저장용)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="메타데이터",
        help_text="추가 정보 (JSON)",
    )

    # 생성일시
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일시")

    class Meta:
        db_table = "shopping_point_history"
        verbose_name = "포인트 이력"
        verbose_name_plural = "포인트 이력 목록"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["type"]),
            models.Index(fields=["order"]),
            models.Index(fields=["expires_at"]),  # 만료 포인트 배치 조회용
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.get_type_display()} {self.points:+d}P"

    def clean(self) -> None:
        """
        포인트 이력 데이터 검증
        """
        super().clean()

        # 포인트 변동량은 0이 될 수 없음
        if self.points == 0:
            raise ValidationError({"points": "포인트 변동량은 0이 될 수 없습니다."})

        # type별 points 부호 검증
        positive_types = {"earn", "cancel_refund", "admin_add", "event"}
        negative_types = {"use", "cancel_deduct", "admin_deduct", "expire"}

        if self.type in positive_types and self.points <= 0:
            raise ValidationError(
                {"points": f"{self.get_type_display()}는 양수 포인트여야 합니다."}
            )

        if self.type in negative_types and self.points >= 0:
            raise ValidationError(
                {"points": f"{self.get_type_display()}는 음수 포인트여야 합니다."}
            )

        # 잔액은 항상 0 이상이어야 함
        if self.balance < 0:
            raise ValidationError({"balance": "잔액은 음수가 될 수 없습니다."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        포인트 이력을 직접 저장하지 마세요.
        반드시 PointHistory.create_history() 또는 PointService를 사용하세요.

        create_history() 메서드는 balance를 필수 파라미터로 요구하여
        잔액이 항상 명시적으로 기록되도록 보장합니다.
        """
        super().save(*args, **kwargs)

    @classmethod
    def create_history(
        cls,
        user: User,
        points: int,
        balance: int,
        type: str,
        order: Order | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> PointHistory:
        """
        포인트 이력 생성 헬퍼 메서드

        Args:
            user: 사용자
            points: 포인트 변동량
            balance: 변경 후 잔액 (명시적 전달 필수)
            type: 이력 타입
            order: 관련 주문 (선택)
            description: 설명 (선택)
            **kwargs: 추가 필드

        Returns:
            PointHistory: 생성된 이력 객체
        """

        # 설명 자동 생성
        if not description:
            type_display = dict(cls.TYPE_CHOICES).get(type, type)
            if order:
                description = f"주문 #{order.order_number} {type_display}"
            else:
                description = type_display

        # 유효기간 설정 (적립의 경우 1년)
        expires_at = kwargs.pop("expires_at", None)
        if type == "earn" and not expires_at:
            from datetime import timedelta

            from django.utils import timezone

            expires_at = timezone.now() + timedelta(days=365)

        return cls.objects.create(
            user=user,
            points=points,
            balance=balance,
            type=type,
            order=order,
            description=description,
            expires_at=expires_at,
            **kwargs,
        )

    @classmethod
    def get_user_balance(cls, user: User) -> int:
        """
        사용자의 현재 포인트 잔액을 계산합니다.

        가장 최근 이력의 balance를 반환하며, 이력이 없는 경우 0을 반환합니다.
        이는 최적화된 방법으로, 모든 이력을 합산하는 것보다 효율적입니다.

        Args:
            user: 포인트 잔액을 조회할 사용자

        Returns:
            int: 현재 포인트 잔액
        """
        latest_history = (
            cls.objects.filter(user=user).order_by("-created_at").only("balance").first()
        )
        return latest_history.balance if latest_history else 0

    @classmethod
    def get_expiring_points(cls, user: User, days: int = 30) -> dict[str, Any]:
        """
        사용자의 만료 예정 포인트를 조회합니다.

        Args:
            user: 조회할 사용자
            days: 앞으로 며칠 이내 만료 포인트를 조회할지 (기본: 30일)

        Returns:
            dict: {
                'total_expiring_points': 만료 예정 총 포인트,
                'expiring_histories': 만료 예정 이력 QuerySet,
                'earliest_expire_date': 가장 빠른 만료일
            }
        """
        from datetime import timedelta

        from django.db.models import Sum
        from django.utils import timezone

        now = timezone.now()
        expire_threshold = now + timedelta(days=days)

        # 만료 예정이면서 아직 사용되지 않은 적립 포인트만 조회
        # (음수 포인트로 상쇄되지 않은 것)
        expiring_histories = cls.objects.filter(
            user=user,
            type="earn",
            expires_at__isnull=False,
            expires_at__lte=expire_threshold,
            expires_at__gte=now,
        ).order_by("expires_at")

        # 만료 예정 포인트 총합
        total_expiring = expiring_histories.aggregate(total=Sum("points"))["total"] or 0

        # 가장 빠른 만료일
        earliest_expire = (
            expiring_histories.values_list("expires_at", flat=True).first()
        )

        return {
            "total_expiring_points": total_expiring,
            "expiring_histories": expiring_histories,
            "earliest_expire_date": earliest_expire,
        }
