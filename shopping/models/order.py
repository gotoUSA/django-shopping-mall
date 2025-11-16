from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Order(models.Model):
    """
    주문 정보를 저장하는 모델
    - 한 명의 사용자가 여러 개의 주문을 할 수 있음
    - 하나의 주문에는 여러 개의 상품이 포함될 수 있음
    """

    # 주문 상태 선택지 정의
    STATUS_CHOICES = [
        ("pending", "결제대기"),  # 주문은 했지만 아직 결제 안함
        ("paid", "결제완료"),  # 결제까지 완료
        ("preparing", "배송준비중"),  # 상품 포장 중
        ("shipped", "배송중"),  # 택배 발송됨
        ("delivered", "배송완료"),  # 고객이 받음
        ("canceled", "주문취소"),  # 주문 취소됨
        ("refunded", "환불완료"),  # 환불 처리됨
    ]

    # 결제 방법 선택지
    PAYMENT_METHOD_CHOICES = [
        ("card", "신용/체크카드"),
        ("bank_transfer", "무통장입금"),
        ("kakao_pay", "카카오페이"),
        ("naver_pay", "네이버페이"),
        ("toss", "토스"),
    ]

    # 주문한 사용자 (User가 삭제되어도 주문 기록은 남김)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="orders",
        verbose_name="주문자",
    )

    # 주문 상태
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",  # 기본값은 '결제대기'
        verbose_name="주문상태",
    )

    # 배송 정보
    shipping_name = models.CharField(
        max_length=100,
        verbose_name="받는분 성함",
        help_text="배송받으실 분의 이름",
    )

    shipping_phone = models.CharField(
        max_length=20,
        verbose_name="받는분 연락처",
        help_text="배송 시 연락 가능한 번호",
    )

    shipping_postal_code = models.CharField(max_length=10, verbose_name="우편번호")

    shipping_address = models.CharField(
        max_length=200,
        verbose_name="배송 주소",
        help_text="기본 주소 (도로명 또는 지번)",
    )

    shipping_address_detail = models.CharField(max_length=255, verbose_name="상세주소", help_text="동/호수 등 상세 주소")

    # 주문 메모
    order_memo = models.TextField(blank=True, verbose_name="주문메모", help_text="배송 시 요청사항")  # 빈 값 허용

    # 결제 정보
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,  # 결제 전에는 비어있을 수 있음
        verbose_name="결제방법",
    )

    # 금액 정보 (자동 계산되지만 기록 보존을 위해 저장)
    total_amount = models.DecimalField(
        max_digits=10,  # 최대 10자리
        decimal_places=0,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],  # 음수 방지
        verbose_name="총 주문금액",
    )

    # 포인트 사용 관련 필드
    used_points = models.PositiveIntegerField(default=0, verbose_name="사용 포인트", help_text="이 주문에서 사용한 포인트")

    final_amount = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="최종 결제금액",
        help_text="총 주문 금액 - 사용 포인트",
    )

    earned_points = models.PositiveIntegerField(default=0, verbose_name="적립 포인트", help_text="이 주문으로 적립된 포인트")

    # 배송비 관련 필드 추가
    shipping_fee = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="배송비",
        help_text="기본 배송비",
    )

    additional_shipping_fee = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="추가 배송비",
        help_text="제주/도서산간 등 추가 배송비",
    )

    is_free_shipping = models.BooleanField(
        default=False,
        verbose_name="무료배송 여부",
        help_text="무료배송 적용 여부",
    )

    # 주문번호 필드 추가
    order_number = models.CharField(
        max_length=20,
        unique=True,
        null=True,  # 처음엔 null 허용
        verbose_name="주문번호",
    )

    # 시간 정보
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="주문일시")  # 생성시 자동 설정

    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일시")  # 수정시 자동 갱신

    class Meta:
        db_table = "shopping_orders"
        verbose_name = "주문"
        verbose_name_plural = "주문 목록"
        ordering = ["-created_at"]  # 최신 주문이 먼저 나오도록

    def __str__(self) -> str:
        # 주문번호는 pk에 날짜를 조합해서 표시
        return f'주문#{self.pk} - {self.user.username if self.user else "비회원"}'

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        주문 저장

        주문번호는 post_save signal에서 자동으로 생성됩니다.
        (signals.py의 generate_order_number 참조)
        """
        super().save(*args, **kwargs)

    @property
    def get_full_shipping_address(self) -> str:
        """전체 배송 주소 반환"""
        return f"{self.shipping_address} {self.shipping_address_detail}"

    @property
    def is_paid(self) -> bool:
        """결제 완료 여부"""
        return self.status in ["paid", "preparing", "shipped", "delivered"]

    @property
    def can_cancel(self) -> bool:
        """취소 가능 여부"""
        return self.status in ["pending", "paid"]

    def get_total_shipping_fee(self) -> Decimal:
        """전체 배송비 반환 (기본 + 추가)"""
        return self.shipping_fee + self.additional_shipping_fee


class OrderItem(models.Model):
    """
    주문에 포함된 개별 상품 정보
    - Order와 Product를 연결하는 중간 테이블
    - 주문 당시의 가격을 별도로 저장 (상품 가격이 변해도 주문 기록은 유지)
    """

    # 주문 참조
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,  # 주문 삭제시 함께 삭제
        related_name="order_items",  # order.order_items.all()로 조회
        verbose_name="주문",
    )

    # 상품 참조
    product = models.ForeignKey(
        "product",  # 문자열로 참조 (순환 import 방지)
        on_delete=models.SET_NULL,  # 상품이 삭제되어도 주문기록은 유지
        null=True,
        verbose_name="상품",
    )

    # 주문 당시 상품정보 (상품이 삭제되거나 이름이 바뀌어도 주문 정보는 유지)
    product_name = models.CharField(max_length=255, verbose_name="상품명(주문당시)")

    # 주문 수량
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)], verbose_name="수량")  # 최소 1개

    # 주문 당시 가격 (상품 가격이 변경되어도 주문 기록은 유지)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="단가(주문당시)",
    )

    class Meta:
        db_table = "shopping_order_items"
        verbose_name = "주문 상품"
        verbose_name_plural = "주문 상품 목록"

    def __str__(self) -> str:
        return f"{self.product_name} x {self.quantity}개"

    def get_subtotal(self) -> Decimal:
        """해당 상품의 소계 계산 (단가 x 수량)"""
        return self.price * self.quantity

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        저장 시 자동 처리:
        1. product_name이 없으면 현재 상품명으로 설정
        2. price가 없으면 현재 상품 가격으로 설정

        Note: OrderItem은 OrderService를 통해서만 생성되어야 합니다.
              주문 총액 업데이트 등의 부수 효과(side effect)는 서비스 레이어에서 명시적으로 처리합니다.
        """
        if not self.product_name and self.product:
            self.product_name = self.product.name

        if not self.price and self.product:
            self.price = self.product.price

        super().save(*args, **kwargs)
