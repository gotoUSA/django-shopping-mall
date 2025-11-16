from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
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
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.get_type_display()} {self.points:+d}P"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        저장 시 자동 처리는 서비스 레이어에서 담당합니다.
        포인트 이력 생성: PointHistory.create_history() 또는 PointService 사용
        balance는 항상 명시적으로 전달되어야 합니다.
        """
        super().save(*args, **kwargs)

    @classmethod
    def create_history(
        cls,
        user: User,
        points: int,
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
            balance=user.points,  # 현재 잔액
            type=type,
            order=order,
            description=description,
            expires_at=expires_at,
            **kwargs,
        )
