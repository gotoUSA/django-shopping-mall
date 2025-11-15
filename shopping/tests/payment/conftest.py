"""
Payment 테스트 전용 Fixture

전역 conftest.py의 fixture는 그대로 사용하고,
payment 테스트에만 필요한 특화된 fixture를 정의합니다.

사용 가능한 전역 fixture:
- api_client: DRF APIClient
- user: 기본 사용자 (이메일 인증 완료, 포인트 5000)
- unverified_user: 이메일 미인증 사용자
- authenticated_client: 인증된 클라이언트
- product: 기본 상품 (10,000원, 재고 10)
- multiple_products: 여러 상품 리스트
- order: pending 상태 기본 주문
- paid_order: 결제 완료된 주문
- payment: pending 상태 결제
"""

from decimal import Decimal

import pytest

from shopping.models.order import Order, OrderItem
from shopping.models.payment import Payment
from shopping.models.product import Product


# ==========================================
# 1. 주문 관련 Fixture
# ==========================================


@pytest.fixture
def order_with_multiple_items(db, user, category):
    """
    여러 상품이 포함된 주문 (주문명 테스트용)

    - 상품 3개 포함
    - 총 금액: 60,000원
    - pending 상태
    """
    # 여러 상품 생성 (고유한 SKU 할당)
    products = [
        Product.objects.create(
            name=f"테스트 상품 {i+1}",
            category=category,
            price=Decimal("10000") * (i + 1),
            stock=10,
            sku=f"TEST-MULTI-{i+1:03d}",  # 고유한 SKU 추가
            is_active=True,
        )
        for i in range(3)
    ]

    total = sum(p.price for p in products)
    order = Order.objects.create(
        user=user,
        status="pending",
        total_amount=total,
        final_amount=total,
        shipping_name="홍길동",
        shipping_phone="010-1234-5678",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
        order_number="20250115000001",
    )

    for product in products:
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            quantity=1,
            price=product.price,
        )

    return order


@pytest.fixture
def order_with_points(db, user, product):
    """
    포인트 사용 주문

    - total_amount: 10,000원
    - used_points: 2,000P
    - final_amount: 8,000원
    """
    order = Order.objects.create(
        user=user,
        status="pending",
        total_amount=product.price,
        used_points=2000,
        final_amount=product.price - Decimal("2000"),
        shipping_name="홍길동",
        shipping_phone="010-1234-5678",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
        order_number="20250115000002",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=1,
        price=product.price,
    )

    return order


@pytest.fixture
def order_with_long_product_name(db, user, category):
    """
    긴 상품명을 가진 주문

    - 상품명 100자 이상
    - pending 상태
    """
    long_name = "아주 긴 상품명 테스트 " * 10  # 100자 이상

    product = Product.objects.create(
        name=long_name,
        category=category,
        price=Decimal("10000"),
        stock=10,
        sku="TEST-LONG-NAME-001",  # 고유한 SKU 추가
        is_active=True,
    )

    order = Order.objects.create(
        user=user,
        status="pending",
        total_amount=product.price,
        final_amount=product.price,
        shipping_name="홍길동",
        shipping_phone="010-1234-5678",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
        order_number="20250115000003",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=1,
        price=product.price,
    )

    return order


@pytest.fixture
def paid_order_with_payment(db, user, product):
    """
    이미 결제 완료된 주문 + Payment

    - 주문: paid 상태
    - Payment: done 상태, is_paid=True
    """
    from django.utils import timezone

    order = Order.objects.create(
        user=user,
        status="paid",
        total_amount=product.price,
        final_amount=product.price,
        payment_method="card",
        shipping_name="홍길동",
        shipping_phone="010-1234-5678",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
        order_number="20250115000004",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=1,
        price=product.price,
    )

    payment = Payment.objects.create(
        order=order,
        amount=order.total_amount,
        status="done",
        toss_order_id=order.order_number,
        payment_key="test_payment_key_already_paid",
        method="카드",
        approved_at=timezone.now(),
    )

    return order


@pytest.fixture
def canceled_order(db, user, product):
    """
    취소된 주문

    - 주문: canceled 상태
    - pending이 아니므로 결제 불가
    """
    order = Order.objects.create(
        user=user,
        status="canceled",
        total_amount=product.price,
        final_amount=product.price,
        shipping_name="홍길동",
        shipping_phone="010-1234-5678",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
        order_number="20250115000005",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=1,
        price=product.price,
    )

    return order


@pytest.fixture
def order_with_existing_payment(db, user, product):
    """
    기존 Payment가 있는 주문 (재시도 테스트용)

    - 주문: pending
    - 기존 Payment: ready 상태 (미완료)
    """
    order = Order.objects.create(
        user=user,
        status="pending",
        total_amount=product.price,
        final_amount=product.price,
        shipping_name="홍길동",
        shipping_phone="010-1234-5678",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
        order_number="20250115000006",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=1,
        price=product.price,
    )

    # 기존 Payment (미완료)
    old_payment = Payment.objects.create(
        order=order,
        amount=order.total_amount,
        status="ready",
        toss_order_id=order.order_number,
    )

    return order


# ==========================================
# 2. 다른 사용자 Fixture
# ==========================================


@pytest.fixture
def other_user(db):
    """
    다른 사용자

    권한 테스트용 - 다른 사용자의 주문 접근 차단 확인
    """
    from shopping.models.user import User

    return User.objects.create_user(
        username="otheruser",
        email="other@example.com",
        password="testpass123",
        phone_number="010-9999-9999",
        is_email_verified=True,
    )


@pytest.fixture
def other_user_order(db, other_user, product):
    """
    다른 사용자의 주문

    - 주문: pending
    - 소유자: other_user
    """
    order = Order.objects.create(
        user=other_user,
        status="pending",
        total_amount=product.price,
        final_amount=product.price,
        shipping_name="김철수",
        shipping_phone="010-8888-8888",
        shipping_postal_code="54321",
        shipping_address="부산시 해운대구 테스트로 456",
        shipping_address_detail="202동 303호",
        order_number="20250115000007",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=1,
        price=product.price,
    )

    return order
