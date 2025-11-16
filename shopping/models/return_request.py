from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from .order import Order, OrderItem
from .product import Product

if TYPE_CHECKING:
    from shopping.models.user import User


class Return(models.Model):
    """
    교환/환불 신청 모델

    하나의 모델로 교환과 환불을 모두 처리합니다.
    프로세스: 신청 → 승인 → 반품 배송 → 수령 확인 → 완료
    """

    # 교환/환불 타입
    TYPE_CHOICES = [
        ("refund", "환불"),
        ("exchange", "교환"),
    ]

    # 처리 상태
    STATUS_CHOICES = [
        ("requested", "신청"),  # 고객이 신청함
        ("approved", "승인"),  # 판매자가 승인함
        ("rejected", "거부"),  # 판매자가 거부함
        ("shipping", "반품배송중"),  # 고객이 반품 발송함
        ("received", "반품도착"),  # 판매자가 반품 받음
        ("completed", "완료"),  # 환불/교환 완료
    ]

    # 신청 사유
    REASON_CHOICES = [
        ("change_of_mind", "단순변심"),
        ("defective", "상품불량"),
        ("wrong_product", "오배송"),
        ("description_mismatch", "상세페이지와 다름"),
        ("size_issue", "사이즈 문제"),
        ("other", "기타"),
    ]

    # 기본 정보
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="returns",
        verbose_name="원본 주문",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="returns",
        verbose_name="신청자",
    )

    return_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="교환/환불 번호",
        help_text="자동 생성됨 (예: RET20250115001)",
    )

    # 타입 및 상태
    type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        verbose_name="타입",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="requested",
        verbose_name="처리 상태",
    )

    # 사유
    reason = models.CharField(
        max_length=30,
        choices=REASON_CHOICES,
        verbose_name="사유",
    )

    reason_detail = models.TextField(
        verbose_name="상세 사유",
        help_text="교환/환불 사유를 구체적으로 작성해주세요",
    )

    # 반품 배송 정보
    return_shipping_company = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="반품 택배사",
        help_text="예: CJ대한통운, 우체국택배",
    )

    return_tracking_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="반품 송장번호",
    )

    return_shipping_fee = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="반품 배송비",
        help_text="고객 부담인 경우 금액 입력",
    )

    # 환불 정보 (type='refund'일 때만 사용)
    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="환불 금액",
    )

    refund_method = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="환불 방법",
        help_text="원결제수단 또는 계좌환불",
    )

    refund_account_bank = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="환불 계좌 은행",
    )

    refund_account_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="환불 계좌번호",
    )

    refund_account_holder = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="예금주",
    )

    # 교환 정보 (type='exchange'일 때만 사용)
    exchange_product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exchange_returns",
        verbose_name="교환 상품",
        help_text="교환받을 상품 (같은 상품일 수도 있음)",
    )

    exchange_shipping_company = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="교환 상품 택배사",
    )

    exchange_tracking_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="교환 상품 송장번호",
    )

    # 처리 정보
    admin_memo = models.TextField(
        blank=True,
        verbose_name="관리자 메모",
        help_text="내부용 메모",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="승인 시각",
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="완료 시각",
    )

    rejected_reason = models.TextField(
        blank=True,
        verbose_name="거부 사유",
    )

    # 타임스탬프
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="신청일",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="수정일",
    )

    class Meta:
        db_table = "shopping_returns"
        verbose_name = "교환/환불"
        verbose_name_plural = "교환/환불 목록"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["return_number"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["order"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} - {self.return_number}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        저장 시 자동 처리는 서비스 레이어에서 담당합니다.
        교환/환불 생성: ReturnService.create_return() 사용
        """
        super().save(*args, **kwargs)

    def generate_return_number(self) -> str:
        """
        교환/환불 번호 자동 생성

        DEPRECATED: ReturnService.generate_return_number() 사용 권장
        """
        from shopping.services.return_service import ReturnService
        return ReturnService.generate_return_number()

    def calculate_refund_amount(self) -> Decimal:
        """
        환불 금액 계산

        DEPRECATED: ReturnService.calculate_refund_amount() 사용 권장
        """
        from shopping.services.return_service import ReturnService
        return ReturnService.calculate_refund_amount(self.return_items.all())

    def can_request(self) -> tuple[bool, str]:
        """
        교환/환불 신청 가능 여부 확인

        조건:
        1. 주문 상태가 'delivered' (배송 완료)
        2. 배송 완료 후 7일 이내
        3. 이미 교환/환불 신청한 주문이 아니어야 함
        """
        # 주문 상태 확인
        if self.order.status != "delivered":
            return False, "배송 완료된 주문만 신청 가능합니다."

        #  배송 완료 후 7일 이내 확인
        # (실제로는 Order 모델에 delivered_at 필드가 있어야 함)
        # 여기서는 간단히 created_at 기준으로 체크
        days_passed = (timezone.now() - self.order.created_at).days
        if days_passed > 7:
            return False, "배송 완료 후 7일이 지나 신청할 수 없습니다."

        # 이미 신청한 교환/환불이 있는지 확인
        existing_returns = Return.objects.filter(
            order=self.order, status__in=["requested", "approved", "shipping", "received"]
        ).exists()

        if existing_returns:
            return False, "이미 처리 중인 교환/환불이 있습니다."

        return True, "신청 가능"

    def approve(self, admin_user: User | None = None) -> None:
        """
        판매자 승인 처리

        Args:
            admin_user: 승인한 관리자 (향후 이력 관리용)
        """
        if self.status != "requested":
            raise ValueError("신청 상태에서만 승인할 수 있습니다.")

        self.status = "approved"
        self.approved_at = timezone.now()
        self.save()

        # 알림 발송 (기존 알림 시스템 활용)
        from .notification import Notification

        Notification.objects.create(
            user=self.user,
            type="return",
            title=f"{self.get_type_display()} 승인",
            message=f"{self.return_number} 신청이 승인되었습니다. 반품 상품을 발송해주세요.",
            metadata={"return_id": self.id, "return_number": self.return_number},
        )

    def reject(self, reason: str) -> None:
        """
        판매자 거부 처리

        Args:
            reason: 거부 사유
        """
        if self.status != "requested":
            raise ValueError("신청 상태에서만 거부할 수 있습니다.")

        self.status = "rejected"
        self.rejected_reason = reason
        self.save()

        # 알림 발송
        from .notification import Notification

        Notification.objects.create(
            user=self.user,
            type="return",
            title=f"{self.get_type_display()} 거부",
            message=f"{self.return_number} 신청이 거부되었습니다. 사유: {reason}",
            metadata={"return_id": self.id, "return_number": self.return_number, "reason": reason},
        )

    def confirm_receive(self) -> None:
        """
        반품 도착 확인 (판매자)

        반품 상품을 수령했음을 확인
        """
        if self.status != "shipping":
            raise ValueError("배송 중 상태에서만 수령 확인할 수 있습니다.")

        self.status = "received"
        self.save()

        # 알림 발송
        from .notification import Notification

        Notification.objects.create(
            user=self.user,
            type="return",
            title="반품 도착 확인",
            message=f"{self.return_number} 반품 상품이 도착했습니다. 곧 처리될 예정입니다.",
            metadata={"return_id": self.id, "return_number": self.return_number},
        )

    def complete_refund(self) -> None:
        """
        환불 완료 처리

        실제 환불 처리:
        1. 토스페이먼츠 API 호출하여 환불
        2. 재고 복구
        3. 포인트 처리
        4. 상태 변경
        """
        if self.type != "refund":
            raise ValueError("환불 타입에서만 사용 가능합니다.")

        if self.status != "received":
            raise ValueError("반품 도착 상태에서만 환불 처리할 수 있습니다.")

        from django.db import transaction

        with transaction.atomic():
            # 1. 토스페이먼츠 환불 처리
            if hasattr(self.order, "payment") and self.order.payment:
                from shopping.utils.toss_payment import TossPaymentClient

                toss_client = TossPaymentClient()

                # 환불 금액 계산 (반품 배송비 차감)
                actual_refund_amount = self.refund_amount - self.return_shipping_fee

                if actual_refund_amount > 0:
                    refund_account = None
                    if self.refund_account_number:
                        refund_account = {
                            "bank": self.refund_account_bank,
                            "accountNumber": self.refund_account_number,
                            "holderName": self.refund_account_holder,
                        }

                    toss_client.cancel_payment(
                        payment_key=self.order.payment.payment_key,
                        cancel_reason=f"{self.get_reason_display()} - {self.reason_detail}",
                        cancel_amount=int(actual_refund_amount),
                        refund_account=refund_account,
                    )

            # 2. 재고 복구
            for return_item in self.return_items.all():
                if return_item.order_item.product:
                    product = return_item.order_item.product
                    product.stock += return_item.quantity
                    product.save(update_fields=["stock"])

            # 3. 포인트 처리 (향후 구현)
            # - 사용한 포인트 환불
            # - 적립된 포인트 회수

            # 4. 상태 변경
            self.status = "completed"
            self.completed_at = timezone.now()
            self.save()

            # 5. 주문 상태 변경
            self.order.status = "refunded"
            self.order.save(update_fields=["status"])

        # 알림 발송
        from .notification import Notification

        Notification.objects.create(
            user=self.user,
            type="return",
            title="환불 완료",
            message=f"{self.return_number} 환불이 완료되었습니다. 환불 금액: {actual_refund_amount:,}원",
            metadata={
                "return_id": self.id,
                "return_number": self.return_number,
                "refund_amount": str(actual_refund_amount),
            },
        )

    def complete_exchange(self) -> None:
        """
        교환 완료 처리

        교환 상품 발송 후 호출:
        1. 재고 조정 (반품 +1, 교환 -1)
        2. 상태 변경
        """
        if self.type != "exchange":
            raise ValueError("교환 타입에서만 사용 가능합니다.")

        if self.status != "received":
            raise ValueError("반품 도착 상태에서만 교환 처리할 수 있습니다.")

        from django.db import transaction

        with transaction.atomic():
            # 1. 재고 조정
            for return_item in self.return_items.all():
                # 반품 상품 재고 증가
                if return_item.order_item.product:
                    product = return_item.order_item.product
                    product.stock += return_item.quantity
                    product.save(update_fields=["stock"])

            # 교환 상품 재고 감소
            if self.exchange_product:
                self.exchange_product.stock -= 1
                self.exchange_product.save(update_fields=["stock"])

            # 2. 상태 변경
            self.status = "completed"
            self.completed_at = timezone.now()
            self.save()

        # 알림 발송
        from .notification import Notification

        Notification.objects.create(
            user=self.user,
            type="return",
            title="교환 완료",
            message=f"{self.return_number} 교환 상품이 발송되었습니다. 송장번호: {self.exchange_tracking_number}",
            metadata={
                "return_id": self.id,
                "return_number": self.return_number,
                "tracking_number": self.exchange_tracking_number,
            },
        )


class ReturnItem(models.Model):
    """
    교환/환불하는 상품 항목

    하나의 Return에 여러 상품이 포함될 수 있음 (부분 환불/교환)
    """

    return_request = models.ForeignKey(
        Return,
        on_delete=models.CASCADE,
        related_name="return_items",
        verbose_name="교환/환불 신청",
    )

    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="return_items",
        verbose_name="주문 상품",
    )

    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="반품 수량",
    )

    # 상품 정보 스냅샷 (주문 당시 정보 유지)
    product_name = models.CharField(
        max_length=255,
        verbose_name="상품명",
    )

    product_price = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="단가",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="등록일",
    )

    class Meta:
        db_table = "shopping_return_items"
        verbose_name = "반품 상품"
        verbose_name_plural = "반품 상품 목록"
        # 같은 주문 상품을 중복으로 반품할 수 없음
        unique_together = [["return_request", "order_item"]]

    def __str__(self) -> str:
        return f"{self.product_name} x {self.quantity}개"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        저장 시 자동 처리:
        1. product_name이 없으면 order_item에서 가져오기
        2. product_price가 없으면 order_item에서 가져오기
        """
        if not self.product_name:
            self.product_name = self.order_item.product_name

        if not self.product_price:
            self.product_price = self.order_item.price

        super().save(*args, **kwargs)

    def get_subtotal(self) -> Decimal:
        """해당 상품의 반품 금액 계산"""
        return self.product_price * self.quantity

    def clean(self) -> None:
        """
        데이터 유효성 검증

        반품 수량이 주문 수량을 초과할 수 없음
        """
        from django.core.exceptions import ValidationError

        if self.quantity > self.order_item.quantity:
            raise ValidationError(f"반품 수량({self.quantity})이 주문 수량({self.order_item.quantity})을 초과할 수 없습니다.")
