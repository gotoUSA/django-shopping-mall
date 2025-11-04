"""
Order 테스트 전용 Fixture

전역 conftest.py의 fixture는 그대로 사용하고,
order 테스트에만 필요한 특화된 fixture를 정의합니다.

사용 가능한 전역 fixture:
- api_client: DRF APIClient
- user: 기본 사용자 (포인트 0)
- seller_user: 판매자 사용자
- authenticated_client: 인증된 클라이언트
- category: 카테고리
- product: 기본 상품 (10,000원, 재고 10)
- out_of_stock_product: 품절 상품
- multiple_products: 여러 상품 리스트
- cart: 빈 장바구니
- cart_with_items: 상품 담긴 장바구니
- shipping_data: 기본 배송 정보
- order: 기본 주문 (pending)
- paid_order: 결제 완료 주문
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from shopping.models.user import User
from shopping.models.product import Category, Product
from shopping.models.cart import Cart, CartItem
from shopping.models.order import Order, OrderItem
from shopping.models.point import PointHistory


# ==========================================
# 1. 포인트 보유 사용자 Fixture
# ==========================================


@pytest.fixture
def user_with_points(db):
    """
    포인트 보유 사용자 (5,000P)

    기본 주문 테스트에 사용
    """
    return User.objects.create_user(
        username="pointuser",
        email="pointuser@example.com",
        password="testpass123",
        phone_number="010-1234-5678",
        points=5000,
        is_email_verified=True,
    )


@pytest.fixture
def user_with_high_points(db):
    """
    많은 포인트 보유 사용자 (50,000P)

    전액 포인트 결제 테스트용
    """
    return User.objects.create_user(
        username="richuser",
        email="richuser@example.com",
        password="testpass123",
        phone_number="010-9999-8888",
        points=50000,
        is_email_verified=True,
    )


@pytest.fixture
def user_no_points(db):
    """
    포인트 없는 사용자 (0P)

    포인트 부족 테스트용
    """
    return User.objects.create_user(
        username="nopoint",
        email="nopoint@example.com",
        password="testpass123",
        phone_number="010-0000-0000",
        points=0,
        is_email_verified=True,
    )


@pytest.fixture
def unverified_user(db):
    """
    이메일 미인증 사용자

    주문 권한 테스트용
    """
    return User.objects.create_user(
        username="unverified",
        email="unverified@example.com",
        password="testpass123",
        is_email_verified=False,  # 이메일 미인증
    )


# ==========================================
# 2. 다양한 상태의 주문 Fixture
# ==========================================


@pytest.fixture
def pending_order(db, user, product):
    """
    결제 대기 주문 (pending)

    기본 주문 취소 테스트용
    """
    order = Order.objects.create(
        user=user,
        status="pending",
        total_amount=product.price,
        shipping_name="홍길동",
        shipping_phone="010-9999-8888",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
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
def shipped_order(db, user, product):
    """
    배송중 주문 (shipped)

    취소 불가 테스트용
    """
    order = Order.objects.create(
        user=user,
        status="shipped",
        total_amount=product.price,
        payment_method="card",
        shipping_name="홍길동",
        shipping_phone="010-9999-8888",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
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
def delivered_order(db, user, product):
    """
    배송완료 주문 (delivered)

    완료된 주문 테스트용
    """
    order = Order.objects.create(
        user=user,
        status="delivered",
        total_amount=product.price,
        payment_method="card",
        shipping_name="홍길동",
        shipping_phone="010-9999-8888",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
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
def canceled_order(db, user, product):
    """
    취소된 주문 (canceled)

    취소 완료 상태 테스트용
    """
    order = Order.objects.create(
        user=user,
        status="canceled",
        total_amount=product.price,
        shipping_name="홍길동",
        shipping_phone="010-9999-8888",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
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
def order_with_points(db, user_with_points, product):
    """
    포인트 사용한 주문 (2,000P 사용)

    포인트 환불 테스트용
    """
    order = Order.objects.create(
        user=user_with_points,
        status="paid",
        total_amount=product.price,
        used_points=2000,
        final_amount=product.price - Decimal("2000"),
        payment_method="card",
        shipping_name="홍길동",
        shipping_phone="010-9999-8888",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=1,
        price=product.price,
    )

    # 포인트 사용 이력 생성
    PointHistory.create_history(
        user=user_with_points,
        points=-2000,
        type="use",
        order=order,
        description=f"주문 #{order.order_number} 결제시 사용",
    )

    # 사용자 포인트 차감
    user_with_points.points -= 2000
    user_with_points.save()

    return order


# ==========================================
# 3. 특수 배송지 정보 Fixture
# ==========================================


@pytest.fixture
def remote_shipping_data():
    """
    제주/도서산간 배송 정보

    추가 배송비 테스트용
    """
    return {
        "shipping_name": "제주거주자",
        "shipping_phone": "010-6300-0000",
        "shipping_postal_code": "63000",  # 제주
        "shipping_address": "제주특별자치도 제주시 테스트로 123",
        "shipping_address_detail": "제주 101호",
        "order_memo": "도서산간 배송비 테스트",
    }


@pytest.fixture
def ulleung_shipping_data():
    """
    울릉도 배송 정보

    추가 배송비 테스트용
    """
    return {
        "shipping_name": "울릉거주자",
        "shipping_phone": "010-5900-0000",
        "shipping_postal_code": "59000",  # 울릉도
        "shipping_address": "경상북도 울릉군 테스트로 456",
        "shipping_address_detail": "울릉 202호",
        "order_memo": "도서산간 배송비 테스트",
    }


# ==========================================
# 4. 재고 관련 Fixture
# ==========================================


@pytest.fixture
def low_stock_product(db, category, seller_user):
    """
    재고 1개 상품

    동시 주문 경쟁 테스트용
    """
    return Product.objects.create(
        name="재고1개 상품",
        slug="low-stock-product",
        category=category,
        seller=seller_user,
        price=Decimal("10000"),
        stock=1,  # 재고 1개
        sku="LOW-STOCK-001",
        description="동시성 테스트용 상품",
        is_active=True,
    )


@pytest.fixture
def product_factory_with_stock(db, category, seller_user):
    """
    특정 재고량 상품 생성 Factory

    사용 예시:
        product = product_factory_with_stock(stock=5)
    """

    def _create_product(stock=10, **kwargs):
        defaults = {
            "name": f"재고{stock}개 상품",
            "slug": f"stock-{stock}-product",
            "category": category,
            "seller": seller_user,
            "price": Decimal("10000"),
            "stock": stock,
            "sku": f"STOCK-{stock:03d}",
            "is_active": True,
        }
        defaults.update(kwargs)

        # slug 중복 방지
        slug = defaults.pop("slug")
        counter = 1
        original_slug = slug
        while Product.objects.filter(slug=slug).exists():
            slug = f"{original_slug}-{counter}"
            counter += 1

        return Product.objects.create(slug=slug, **defaults)

    return _create_product


# ==========================================
# 5. 주문 생성 헬퍼 Fixture
# ==========================================


@pytest.fixture
def create_order_helper(db):
    """
    주문 빠르게 생성하는 헬퍼 함수

    사용 예시:
        order = create_order_helper(
            user=user,
            products=[(product1, 2), (product2, 1)],
            status="paid"
        )
    """

    def _create_order(user, products, status="pending", use_points=0, **shipping_kwargs):
        """
        Args:
            user: 주문 사용자
            products: [(product, quantity), ...] 형태의 리스트
            status: 주문 상태
            use_points: 사용 포인트
            **shipping_kwargs: 배송 정보 (선택)
        """
        # 기본 배송 정보
        shipping_defaults = {
            "shipping_name": "홍길동",
            "shipping_phone": "010-9999-8888",
            "shipping_postal_code": "12345",
            "shipping_address": "서울시 강남구 테스트로 123",
            "shipping_address_detail": "101동 202호",
        }
        shipping_defaults.update(shipping_kwargs)

        # 총 금액 계산
        total_amount = sum(product.price * quantity for product, quantity in products)

        # 주문 생성
        order = Order.objects.create(
            user=user,
            status=status,
            total_amount=total_amount,
            used_points=use_points,
            final_amount=max(Decimal("0"), total_amount - Decimal(str(use_points))),
            **shipping_defaults,
        )

        # OrderItem 생성
        for product, quantity in products:
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                quantity=quantity,
                price=product.price,
            )

        return order

    return _create_order


@pytest.fixture
def add_to_cart_helper(db):
    """
    장바구니에 상품 추가하는 헬퍼 함수

    사용 예시:
        add_to_cart_helper(user, product, quantity=2)
    """

    def _add_to_cart(user, product, quantity=1):
        """
        Args:
            user: 사용자
            product: 상품
            quantity: 수량
        """
        from shopping.models.cart import Cart, CartItem

        # 활성 장바구니 가져오기 또는 생성
        cart, created = Cart.objects.get_or_create(user=user, is_active=True)

        # 기존 장바구니 아이템 확인
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={"quantity": quantity},
        )

        if not created:
            # 이미 존재하면 수량 증가
            cart_item.quantity += quantity
            cart_item.save()

        return cart_item

    return _add_to_cart


# ==========================================
# 6. 여러 주문 생성 Fixture
# ==========================================


@pytest.fixture
def multiple_orders(db, user, multiple_products):
    """
    여러 주문 생성 (3개)

    주문 목록/필터링 테스트용
    """
    orders = []

    statuses = ["pending", "paid", "shipped"]

    for i, product in enumerate(multiple_products):
        order = Order.objects.create(
            user=user,
            status=statuses[i],
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-9999-8888",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구 테스트로 123",
            shipping_address_detail="101동 202호",
        )

        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            quantity=1,
            price=product.price,
        )

        orders.append(order)

    return orders


@pytest.fixture
def orders_different_dates(db, user, product):
    """
    서로 다른 날짜의 주문들 (3개)

    날짜 필터링 테스트용
    """
    from unittest.mock import patch
    from datetime import timedelta

    orders = []
    now = timezone.now()

    # 3일 전, 2일 전, 오늘
    dates = [now - timedelta(days=3), now - timedelta(days=2), now]

    for date in dates:
        with patch("django.utils.timezone.now", return_value=date):
            order = Order.objects.create(
                user=user,
                status="paid",
                total_amount=product.price,
                shipping_name="홍길동",
                shipping_phone="010-9999-8888",
                shipping_postal_code="12345",
                shipping_address="서울시 강남구 테스트로 123",
                shipping_address_detail="101동 202호",
            )

            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                quantity=1,
                price=product.price,
            )

            orders.append(order)

    return orders


# ==========================================
# 7. 타임스탬프 제어 Fixture
# ==========================================


@pytest.fixture
def freeze_time_helper(mocker):
    """
    시간 고정 헬퍼

    사용 예시:
        with freeze_time_helper(datetime(2025, 1, 1)):
            # 테스트 코드
    """
    from django.utils import timezone
    from contextlib import contextmanager

    @contextmanager
    def _freeze(dt):
        mock = mocker.patch("django.utils.timezone.now", return_value=dt)
        try:
            yield mock
        finally:
            mock.stop()

    return _freeze
