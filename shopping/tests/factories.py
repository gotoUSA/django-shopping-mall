"""
Test factories for shopping app

Factory Boy를 사용하여 테스트 데이터를 생성합니다.
- 재사용 가능한 테스트 객체 생성
- 기본값 제공 및 필요시 오버라이드 가능
- 관계형 데이터 자동 처리
"""

from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from shopping.models.order import Order, OrderItem
from shopping.models.payment import Payment
from shopping.models.point import PointHistory
from shopping.models.product import Category, Product
from shopping.models.user import User


# ==========================================
# 상수 정의
# ==========================================

class TestConstants:
    """테스트에서 사용하는 상수"""

    # 금액
    DEFAULT_PRODUCT_PRICE = Decimal("10000")
    DEFAULT_SHIPPING_FEE = Decimal("3000")
    DEFAULT_TOTAL_AMOUNT = Decimal("13000")

    # 포인트
    DEFAULT_POINTS = 5000
    DEFAULT_EARN_POINTS = 100

    # 배송 정보
    DEFAULT_SHIPPING_NAME = "홍길동"
    DEFAULT_SHIPPING_PHONE = "010-1234-5678"
    DEFAULT_SHIPPING_POSTAL_CODE = "12345"
    DEFAULT_SHIPPING_ADDRESS = "서울시 강남구"
    DEFAULT_SHIPPING_ADDRESS_DETAIL = "101동"

    # Toss 응답 날짜
    DEFAULT_APPROVED_AT = "2025-01-15T10:00:00+09:00"
    DEFAULT_CANCELED_AT = "2025-01-15T11:00:00+09:00"


# ==========================================
# Factory 클래스
# ==========================================


class UserFactory(DjangoModelFactory):
    """User factory"""

    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"testuser{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@test.com")
    phone_number = factory.Sequence(lambda n: f"010-{1000+n:04d}-{5678+n:04d}")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    points = 0
    membership_level = "bronze"


class CategoryFactory(DjangoModelFactory):
    """Category factory"""

    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"테스트 카테고리 {n}")
    slug = factory.Sequence(lambda n: f"test-category-{n}")


class ProductFactory(DjangoModelFactory):
    """Product factory"""

    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"테스트 상품 {n}")
    category = factory.SubFactory(CategoryFactory)
    price = TestConstants.DEFAULT_PRODUCT_PRICE
    stock = 100
    sku = factory.Sequence(lambda n: f"TEST-SKU-{n:06d}")
    is_active = True
    description = "테스트 상품 설명"


class OrderFactory(DjangoModelFactory):
    """
    Order factory

    기본적으로 pending 상태의 주문을 생성합니다.
    배송 정보는 TestConstants의 기본값을 사용합니다.
    """

    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    status = "pending"
    total_amount = TestConstants.DEFAULT_PRODUCT_PRICE
    shipping_fee = TestConstants.DEFAULT_SHIPPING_FEE
    final_amount = TestConstants.DEFAULT_TOTAL_AMOUNT
    used_points = 0
    earned_points = 0

    # 배송 정보
    shipping_name = TestConstants.DEFAULT_SHIPPING_NAME
    shipping_phone = TestConstants.DEFAULT_SHIPPING_PHONE
    shipping_postal_code = TestConstants.DEFAULT_SHIPPING_POSTAL_CODE
    shipping_address = TestConstants.DEFAULT_SHIPPING_ADDRESS
    shipping_address_detail = TestConstants.DEFAULT_SHIPPING_ADDRESS_DETAIL

    # 주문 번호 자동 생성
    order_number = factory.Sequence(
        lambda n: f"{timezone.now().strftime('%Y%m%d')}{n:06d}"
    )


class OrderItemFactory(DjangoModelFactory):
    """OrderItem factory"""

    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    product = factory.SubFactory(ProductFactory)
    product_name = factory.LazyAttribute(lambda obj: obj.product.name)
    quantity = 1
    price = factory.LazyAttribute(lambda obj: obj.product.price)


class PaymentFactory(DjangoModelFactory):
    """
    Payment factory

    Order와 연결된 Payment를 생성합니다.
    기본값은 ready 상태입니다.
    """

    class Meta:
        model = Payment

    order = factory.SubFactory(OrderFactory)
    amount = factory.LazyAttribute(lambda obj: obj.order.final_amount)
    status = "ready"
    toss_order_id = factory.LazyAttribute(lambda obj: obj.order.order_number)
    payment_key = factory.Sequence(lambda n: f"test_payment_key_{n}")
    method = "카드"


class PointHistoryFactory(DjangoModelFactory):
    """
    PointHistory factory

    포인트 이력을 생성합니다.
    기본적으로 earn 타입의 이력을 생성합니다.
    """

    class Meta:
        model = PointHistory

    user = factory.SubFactory(UserFactory)
    points = TestConstants.DEFAULT_EARN_POINTS
    balance = factory.LazyAttribute(lambda obj: obj.user.points + obj.points)
    type = "earn"
    description = "테스트 적립"
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=365))


# ==========================================
# Trait 및 Helper Factory
# ==========================================


class PaidOrderFactory(OrderFactory):
    """
    결제 완료된 주문 Factory

    status='paid'이며 earned_points가 자동 계산됩니다.
    """

    status = "paid"
    earned_points = factory.LazyAttribute(
        lambda obj: int(obj.total_amount * Decimal("0.01"))  # 1% 적립
    )


class CompletedPaymentFactory(PaymentFactory):
    """
    완료된 Payment Factory

    status='done'이며 approved_at이 설정됩니다.
    """

    status = "done"
    approved_at = factory.LazyFunction(timezone.now)
    is_paid = True


class OrderWithItemsFactory(OrderFactory):
    """
    OrderItem이 포함된 Order Factory

    주문과 함께 OrderItem을 자동 생성합니다.
    """

    @factory.post_generation
    def items(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            # items가 명시적으로 전달된 경우
            for item_data in extracted:
                OrderItemFactory(order=self, **item_data)
        else:
            # 기본적으로 1개의 아이템 생성
            OrderItemFactory(order=self)


# ==========================================
# Toss API 응답 빌더
# ==========================================


class TossResponseBuilder:
    """
    Toss API 응답 빌더

    재사용 가능한 Toss API 응답을 생성합니다.
    """

    @staticmethod
    def success_response(
        payment_key="test_payment_key_123",
        order_id="ORDER_20250115_001",
        amount=13000,
        method="카드",
        approved_at=None,
    ):
        """결제 승인 성공 응답"""
        return {
            "paymentKey": payment_key,
            "orderId": order_id,
            "status": "DONE",
            "totalAmount": amount,
            "method": method,
            "approvedAt": approved_at or TestConstants.DEFAULT_APPROVED_AT,
            "card": {
                "company": "신한카드",
                "number": "1234****5678",
                "installmentPlanMonths": 0,
                "cardType": "신용",
                "ownerType": "개인",
            },
        }

    @staticmethod
    def cancel_response(
        payment_key="test_payment_key_123",
        cancel_reason="고객 변심",
        canceled_at=None,
    ):
        """결제 취소 성공 응답"""
        return {
            "paymentKey": payment_key,
            "status": "CANCELED",
            "cancelReason": cancel_reason,
            "canceledAt": canceled_at or TestConstants.DEFAULT_CANCELED_AT,
        }

    @staticmethod
    def error_response(code="INVALID_REQUEST", message="잘못된 요청입니다."):
        """에러 응답"""
        return {"code": code, "message": message}
