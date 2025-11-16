"""OrderService 단위 테스트"""

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.db import transaction

from shopping.models.cart import Cart, CartItem
from shopping.models.order import Order, OrderItem
from shopping.models.product import Category, Product
from shopping.models.user import User
from shopping.services.order_service import OrderService, OrderServiceError


@pytest.fixture
def category(db):
    """테스트용 카테고리"""
    return Category.objects.create(name="테스트 카테고리", slug="test-category")


@pytest.fixture
def product_with_stock(db, category):
    """재고가 있는 상품"""
    return Product.objects.create(
        name="테스트 상품",
        price=Decimal("10000"),
        stock=100,
        category=category,
        description="테스트 상품 설명",
    )


@pytest.fixture
def test_user(db):
    """테스트용 사용자"""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
        phone_number="010-1234-5678",
        points=10000,
        is_email_verified=True,
    )


@pytest.fixture
def cart_with_items(db, test_user, product_with_stock):
    """상품이 담긴 장바구니"""
    cart = Cart.objects.create(user=test_user, is_active=True)
    CartItem.objects.create(cart=cart, product=product_with_stock, quantity=2)
    return cart


@pytest.fixture
def shipping_info():
    """배송 정보"""
    return {
        "shipping_name": "홍길동",
        "shipping_phone": "010-1234-5678",
        "shipping_postal_code": "12345",
        "shipping_address": "서울시 강남구",
        "shipping_address_detail": "101동 101호",
        "order_memo": "문 앞에 놓아주세요",
    }


@pytest.mark.django_db
class TestOrderServiceCreateOrder:
    """주문 생성 테스트"""

    def test_create_order_from_cart_success(self, test_user, cart_with_items, product_with_stock, shipping_info):
        """장바구니에서 주문 생성 성공"""
        # Arrange
        initial_stock = product_with_stock.stock
        cart = cart_with_items

        # Act
        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart,
            use_points=0,
            **shipping_info,
        )

        # Assert
        assert order is not None
        assert order.user == test_user
        assert order.status == "pending"
        assert order.total_amount == Decimal("20000")  # 10000 * 2
        assert order.shipping_name == "홍길동"
        assert order.order_number is not None

        # 주문 아이템 확인
        assert order.order_items.count() == 1
        order_item = order.order_items.first()
        assert order_item.product == product_with_stock
        assert order_item.quantity == 2

        # 재고 차감 확인
        product_with_stock.refresh_from_db()
        assert product_with_stock.stock == initial_stock - 2

        # 장바구니 비우기 확인
        assert cart.items.count() == 0

    def test_create_order_with_points(self, test_user, cart_with_items, shipping_info):
        """포인트 사용하여 주문 생성"""
        # Arrange
        use_points = 5000
        initial_points = test_user.points

        # Act
        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart_with_items,
            use_points=use_points,
            **shipping_info,
        )

        # Assert
        assert order.used_points == use_points
        # 배송비 포함해서 계산해야 함 (20000 + 배송비 - 5000)
        assert order.final_amount < order.total_amount + order.shipping_fee

        # 포인트 차감 확인
        test_user.refresh_from_db()
        assert test_user.points == initial_points - use_points

    def test_create_order_stock_shortage(self, test_user, cart_with_items, product_with_stock, shipping_info):
        """재고 부족 시 주문 생성 실패"""
        # Arrange
        product_with_stock.stock = 1  # 재고를 1개로 설정 (주문 수량 2개보다 적음)
        product_with_stock.save()

        # Act & Assert
        with pytest.raises(OrderServiceError) as exc_info:
            OrderService.create_order_from_cart(
                user=test_user,
                cart=cart_with_items,
                use_points=0,
                **shipping_info,
            )

        assert "재고가 부족합니다" in str(exc_info.value)

        # 트랜잭션 롤백 확인 (주문이 생성되지 않아야 함)
        assert Order.objects.filter(user=test_user).count() == 0

    def test_create_order_multiple_products(self, test_user, category, shipping_info):
        """여러 상품으로 주문 생성"""
        # Arrange
        import uuid
        product1 = Product.objects.create(
            name="상품1",
            price=Decimal("10000"),
            stock=10,
            category=category,
            sku=f"SKU-{uuid.uuid4().hex[:8]}",
        )
        product2 = Product.objects.create(
            name="상품2",
            price=Decimal("20000"),
            stock=10,
            category=category,
            sku=f"SKU-{uuid.uuid4().hex[:8]}",
        )

        cart = Cart.objects.create(user=test_user, is_active=True)
        CartItem.objects.create(cart=cart, product=product1, quantity=1)
        CartItem.objects.create(cart=cart, product=product2, quantity=2)

        # Act
        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart,
            use_points=0,
            **shipping_info,
        )

        # Assert
        assert order.order_items.count() == 2
        assert order.total_amount == Decimal("50000")  # 10000*1 + 20000*2

        # 각 상품의 재고 차감 확인
        product1.refresh_from_db()
        product2.refresh_from_db()
        assert product1.stock == 9
        assert product2.stock == 8

    def test_create_order_with_shipping_fee(self, test_user, cart_with_items, shipping_info):
        """배송비가 포함된 주문 생성"""
        # Act
        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart_with_items,
            use_points=0,
            **shipping_info,
        )

        # Assert
        # 배송비는 ShippingService에 의해 계산됨
        assert order.shipping_fee >= 0
        assert order.final_amount == order.total_amount + order.shipping_fee + order.additional_shipping_fee

    def test_create_order_logging(self, test_user, cart_with_items, shipping_info, caplog):
        """주문 생성 시 로깅 확인"""
        import logging

        # logger 이름을 명시하여 로그 캡처
        caplog.set_level(logging.INFO, logger="shopping.services.order_service")

        # Act
        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart_with_items,
            use_points=0,
            **shipping_info,
        )

        # Assert
        assert "주문 생성 시작" in caplog.text
        assert "주문 생성 완료" in caplog.text
        assert "재고 차감" in caplog.text
        assert "주문 생성 프로세스 완료" in caplog.text
        assert f"order_id={order.id}" in caplog.text


@pytest.mark.django_db
class TestOrderServiceCancelOrder:
    """주문 취소 테스트"""

    def test_cancel_pending_order(self, test_user, product_with_stock, shipping_info):
        """pending 상태 주문 취소"""
        # Arrange
        initial_stock = product_with_stock.stock  # 주문 생성 전 재고 저장

        cart = Cart.objects.create(user=test_user, is_active=True)
        CartItem.objects.create(cart=cart, product=product_with_stock, quantity=2)

        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart,
            use_points=0,
            **shipping_info,
        )

        # 주문 생성 후 재고가 차감되었는지 확인
        product_with_stock.refresh_from_db()
        assert product_with_stock.stock == initial_stock - 2

        # Act
        OrderService.cancel_order(order)

        # Assert
        order.refresh_from_db()
        assert order.status == "canceled"

        # 재고 복구 확인 (원래 재고로 돌아와야 함)
        product_with_stock.refresh_from_db()
        assert product_with_stock.stock == initial_stock

    def test_cancel_paid_order(self, test_user, product_with_stock, shipping_info):
        """paid 상태 주문 취소 (sold_count도 차감)"""
        # Arrange
        cart = Cart.objects.create(user=test_user, is_active=True)
        CartItem.objects.create(cart=cart, product=product_with_stock, quantity=2)

        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart,
            use_points=0,
            **shipping_info,
        )

        # paid 상태로 변경하고 sold_count 증가 시뮬레이션
        order.status = "paid"
        order.save()
        product_with_stock.sold_count = 2
        product_with_stock.save()

        initial_stock = product_with_stock.stock
        initial_sold_count = product_with_stock.sold_count

        # Act
        OrderService.cancel_order(order)

        # Assert
        order.refresh_from_db()
        assert order.status == "canceled"

        # 재고 복구 및 sold_count 차감 확인
        product_with_stock.refresh_from_db()
        assert product_with_stock.stock == initial_stock + 2
        assert product_with_stock.sold_count == initial_sold_count - 2

    def test_cancel_order_not_allowed(self, test_user, product_with_stock, shipping_info):
        """취소 불가능한 주문 (shipped 상태)"""
        # Arrange
        cart = Cart.objects.create(user=test_user, is_active=True)
        CartItem.objects.create(cart=cart, product=product_with_stock, quantity=1)

        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart,
            use_points=0,
            **shipping_info,
        )

        order.status = "shipped"  # 배송 중 상태로 변경
        order.save()

        # Act & Assert
        with pytest.raises(OrderServiceError) as exc_info:
            OrderService.cancel_order(order)

        assert "취소할 수 없는 주문입니다" in str(exc_info.value)

    def test_cancel_order_logging(self, test_user, product_with_stock, shipping_info, caplog):
        """주문 취소 시 로깅 확인"""
        import logging

        # logger 이름을 명시하여 로그 캡처
        caplog.set_level(logging.INFO, logger="shopping.services.order_service")

        # Arrange
        cart = Cart.objects.create(user=test_user, is_active=True)
        CartItem.objects.create(cart=cart, product=product_with_stock, quantity=1)

        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart,
            use_points=0,
            **shipping_info,
        )

        # Act
        OrderService.cancel_order(order)

        # Assert
        assert "주문 취소 시작" in caplog.text
        assert "재고 복구" in caplog.text
        assert "주문 취소 완료" in caplog.text


@pytest.mark.django_db
class TestOrderServiceConcurrency:
    """동시성 제어 테스트"""

    def test_concurrent_order_creation_stock_management(self, test_user, category):
        """동시 주문 생성 시 재고 관리"""
        # Arrange
        product = Product.objects.create(
            name="재고 테스트 상품",
            price=Decimal("10000"),
            stock=5,  # 재고 5개
            category=category,
        )

        # 두 개의 장바구니 생성 (각각 3개씩 주문)
        cart1 = Cart.objects.create(user=test_user, is_active=True)
        CartItem.objects.create(cart=cart1, product=product, quantity=3)

        user2 = User.objects.create_user(
            username="testuser2",
            email="test2@example.com",
            password="testpass123",
            points=10000,
        )
        cart2 = Cart.objects.create(user=user2, is_active=True)
        CartItem.objects.create(cart=cart2, product=product, quantity=3)

        shipping_info = {
            "shipping_name": "홍길동",
            "shipping_phone": "010-1234-5678",
            "shipping_postal_code": "12345",
            "shipping_address": "서울시",
            "shipping_address_detail": "101호",
            "order_memo": "",
        }

        # Act & Assert
        # 첫 번째 주문은 성공해야 함
        order1 = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart1,
            use_points=0,
            **shipping_info,
        )
        assert order1 is not None

        # 두 번째 주문은 재고 부족으로 실패해야 함
        with pytest.raises(OrderServiceError):
            OrderService.create_order_from_cart(
                user=user2,
                cart=cart2,
                use_points=0,
                **shipping_info,
            )

        # 재고 확인 (첫 번째 주문만 차감됨)
        product.refresh_from_db()
        assert product.stock == 2  # 5 - 3
