"""
Order 테스트 전용 Fixture

전역 conftest.py의 fixture는 그대로 사용하고,
order 테스트에만 필요한 특화된 fixture를 정의합니다.

사용 가능한 전역 fixture:
- api_client: DRF APIClient
- user: 기본 사용자 (포인트 5000)
- seller_user: 판매자 사용자
- authenticated_client: 인증된 클라이언트
- category: 카테고리
- product: 기본 상품 (10,000원, 재고 10)
- out_of_stock_product: 품절 상품
- multiple_products: 여러 상품 리스트
- shipping_data: 기본 배송 정보
"""

from decimal import Decimal

import pytest

from shopping.models.cart import Cart, CartItem
from shopping.models.product import Product
from shopping.models.user import User

# ==========================================
# 1. 포인트 보유 사용자 Fixture
# ==========================================


@pytest.fixture
def user_with_points(db):
    """
    포인트 보유 사용자 (5,000P)

    기본 포인트 사용 테스트에 사용
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
        phone_number="010-5555-5555",
        is_email_verified=False,
    )


# ==========================================
# 2. 배송지 정보 Fixture
# ==========================================


@pytest.fixture
def remote_shipping_data():
    """
    도서산간 배송지 정보 (제주)

    추가 배송비 테스트용
    """
    return {
        "shipping_name": "김제주",
        "shipping_phone": "010-6300-0000",
        "shipping_postal_code": "63000",  # 제주 우편번호
        "shipping_address": "제주특별자치도 제주시 연동",
        "shipping_address_detail": "301호",
        "order_memo": "제주 배송 테스트",
    }


@pytest.fixture
def invalid_shipping_data():
    """
    잘못된 배송지 정보

    유효성 검증 테스트용
    """
    return {
        "shipping_name": "",  # 빈 이름
        "shipping_phone": "invalid-phone",  # 잘못된 전화번호
        "shipping_postal_code": "",
        "shipping_address": "",
        "shipping_address_detail": "",
    }


# ==========================================
# 3. 재고 관련 Fixture
# ==========================================


@pytest.fixture
def low_stock_product(db, category, seller_user):
    """
    재고 1개 상품

    재고 경계값 테스트용
    """
    return Product.objects.create(
        name="재고1개 상품",
        slug="low-stock-product",
        category=category,
        seller=seller_user,
        price=Decimal("10000"),
        stock=1,
        sku="LOW-STOCK-001",
        is_active=True,
    )


@pytest.fixture
def inactive_product(db, category, seller_user):
    """
    비활성화된 상품

    판매 중단 상품 테스트용
    """
    return Product.objects.create(
        name="판매중단 상품",
        slug="inactive-product",
        category=category,
        seller=seller_user,
        price=Decimal("15000"),
        stock=10,
        sku="INACTIVE-001",
        is_active=False,
    )


# ==========================================
# 4. 헬퍼 함수 Fixture
# ==========================================


@pytest.fixture
def add_to_cart_helper(db):
    """
    장바구니에 상품을 추가하는 헬퍼 함수

    테스트용이므로 재고 검증을 완전히 우회합니다.
    bulk_create를 사용하여 save() 메서드를 호출하지 않습니다.

    사용 예시:
        add_to_cart_helper(user, product, quantity=2)
    """

    def _add_to_cart(user, product, quantity=1):
        from django.db import transaction
        from django.utils import timezone

        with transaction.atomic():
            cart, created = Cart.objects.get_or_create(user=user, is_active=True)

            # 기존 아이템이 있는지 확인
            try:
                cart_item = CartItem.objects.get(cart=cart, product=product)
                # update()를 사용하여 full_clean() 우회
                cart_item.quantity += quantity
                CartItem.objects.filter(pk=cart_item.pk).update(quantity=cart_item.quantity, updated_at=timezone.now())
                cart_item.refresh_from_db()
            except CartItem.DoesNotExist:
                # bulk_create를 사용하여 save() 및 full_clean() 완전 우회
                cart_item = CartItem(
                    cart=cart, product=product, quantity=quantity, added_at=timezone.now(), updated_at=timezone.now()
                )
                CartItem.objects.bulk_create([cart_item])
                # bulk_create 후에는 pk가 설정되므로 다시 조회
                cart_item = CartItem.objects.get(cart=cart, product=product)

        return cart_item

    return _add_to_cart
