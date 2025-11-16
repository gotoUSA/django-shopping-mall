"""PaymentService 단위 테스트"""

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from shopping.models.cart import Cart, CartItem
from shopping.models.order import Order
from shopping.models.payment import Payment, PaymentLog
from shopping.models.product import Category, Product
from shopping.models.user import User
from shopping.services.order_service import OrderService
from shopping.services.payment_service import PaymentCancelError, PaymentConfirmError, PaymentService
from shopping.utils.toss_payment import TossPaymentError


@pytest.fixture
def category(db):
    """테스트용 카테고리"""
    return Category.objects.create(name="테스트 카테고리", slug="test-category")


@pytest.fixture
def product(db, category):
    """테스트용 상품"""
    return Product.objects.create(
        name="테스트 상품",
        price=Decimal("50000"),
        stock=100,
        category=category,
        description="테스트 상품 설명",
    )


@pytest.fixture
def test_user(db):
    """테스트용 사용자"""
    return User.objects.create_user(
        username="paytest",
        email="paytest@example.com",
        password="testpass123",
        phone_number="010-1234-5678",
        points=10000,
        is_email_verified=True,
        membership_level="silver",  # 2% 적립률
    )


@pytest.fixture
def test_order(db, test_user, product):
    """테스트용 주문"""
    cart = Cart.objects.create(user=test_user, is_active=True)
    CartItem.objects.create(cart=cart, product=product, quantity=1)

    shipping_info = {
        "shipping_name": "홍길동",
        "shipping_phone": "010-1234-5678",
        "shipping_postal_code": "12345",
        "shipping_address": "서울시 강남구",
        "shipping_address_detail": "101동 101호",
        "order_memo": "문 앞에 놓아주세요",
    }

    order = OrderService.create_order_from_cart(
        user=test_user,
        cart=cart,
        use_points=0,
        **shipping_info,
    )

    return order


@pytest.fixture
def mock_toss_client():
    """TossPaymentClient 모킹"""
    with patch("shopping.services.payment_service.TossPaymentClient") as mock:
        yield mock


@pytest.mark.django_db
class TestPaymentServiceCreatePayment:
    """결제 정보 생성 테스트"""

    def test_create_payment_success(self, test_order):
        """결제 정보 생성 성공"""
        # Act
        payment = PaymentService.create_payment(
            order=test_order,
            payment_method="card",
        )

        # Assert
        assert payment is not None
        assert payment.order == test_order
        assert payment.amount == test_order.final_amount
        assert payment.method == "card"
        assert payment.status == "ready"
        assert payment.toss_order_id == test_order.order_number

        # PaymentLog 확인
        log = PaymentLog.objects.filter(payment=payment, log_type="request").first()
        assert log is not None

    def test_create_payment_with_existing_payment(self, test_order):
        """기존 결제 정보가 있을 때 새로 생성 (재시도)"""
        # Arrange
        existing_payment = PaymentService.create_payment(test_order, "card")

        # Act
        new_payment = PaymentService.create_payment(test_order, "card")

        # Assert
        assert Payment.objects.filter(order=test_order).count() == 1
        assert new_payment.id != existing_payment.id  # 새로운 객체
        assert not Payment.objects.filter(id=existing_payment.id).exists()  # 기존 것은 삭제됨

    def test_create_payment_logging(self, test_order, caplog):
        """결제 정보 생성 시 로깅 확인"""
        import logging

        # logger 이름을 명시하여 로그 캡처
        caplog.set_level(logging.INFO, logger="shopping.services.payment_service")

        # Act
        payment = PaymentService.create_payment(test_order, "card")

        # Assert - caplog.records를 사용하여 로그 메시지 확인
        log_messages = [record.message for record in caplog.records]
        assert any("결제 정보 생성 시작" in msg for msg in log_messages)
        assert any("결제 정보 생성 완료" in msg for msg in log_messages)
        assert any(f"payment_id={payment.id}" in msg for msg in log_messages)


@pytest.mark.django_db
class TestPaymentServiceConfirmPayment:
    """결제 승인 테스트"""

    def test_confirm_payment_success(self, test_user, test_order, product, mock_toss_client):
        """결제 승인 성공"""
        # Arrange
        # 주문 생성 후 재고를 확인 (주문 생성 시 이미 재고가 차감됨)
        product.refresh_from_db()
        stock_after_order = product.stock
        initial_sold_count = product.sold_count
        initial_points = test_user.points

        payment = PaymentService.create_payment(test_order, "card")

        # TossPaymentClient 모킹
        mock_instance = mock_toss_client.return_value
        mock_instance.confirm_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "orderId": test_order.order_number,
            "status": "DONE",
            "totalAmount": int(test_order.final_amount),
            "method": "카드",
            "receiptUrl": "http://receipt.url",
        }

        # Act
        result = PaymentService.confirm_payment(
            payment=payment,
            payment_key="test_payment_key_123",
            order_id=test_order.order_number,
            amount=int(test_order.final_amount),
            user=test_user,
        )

        # Assert
        payment.refresh_from_db()
        assert payment.status == "done"
        assert payment.payment_key == "test_payment_key_123"

        # 주문 상태 확인
        test_order.refresh_from_db()
        assert test_order.status == "paid"

        # sold_count 증가 확인 (재고는 주문 생성 시 이미 차감되어 변하지 않음)
        product.refresh_from_db()
        assert product.stock == stock_after_order  # 재고는 변하지 않음
        assert product.sold_count == initial_sold_count + 1

        # 포인트 적립 확인 (silver: 2% 적립)
        test_user.refresh_from_db()
        expected_points = initial_points + int(test_order.final_amount * Decimal("0.02"))
        assert test_user.points == expected_points
        assert result["points_earned"] > 0

    def test_confirm_payment_with_points_only(self, test_user, product, mock_toss_client):
        """포인트로만 결제한 경우 (final_amount = 0)"""
        # Arrange
        cart = Cart.objects.create(user=test_user, is_active=True)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        shipping_info = {
            "shipping_name": "홍길동",
            "shipping_phone": "010-1234-5678",
            "shipping_postal_code": "12345",
            "shipping_address": "서울시 강남구",
            "shipping_address_detail": "101동 101호",
            "order_memo": "",
        }

        # 포인트 충분하게 설정 (주문 생성 전에 설정 필요)
        test_user.points = 70000
        test_user.save()

        # 포인트로 전액 결제 (상품 50000원 = 총 결제 금액과 동일)
        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart,
            use_points=50000,  # 주문 금액과 정확히 일치
            **shipping_info,
        )

        payment = PaymentService.create_payment(order, "card")

        # TossPaymentClient 모킹
        mock_instance = mock_toss_client.return_value
        mock_instance.confirm_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "orderId": order.order_number,
            "status": "DONE",
            "totalAmount": 0,  # 포인트로만 결제
            "method": "카드",
            "receiptUrl": "http://receipt.url",
        }

        # Act
        result = PaymentService.confirm_payment(
            payment=payment,
            payment_key="test_payment_key_123",
            order_id=order.order_number,
            amount=0,
            user=test_user,
        )

        # Assert
        assert result["points_earned"] == 0  # 포인트 적립 없음

    def test_confirm_payment_logging(self, test_user, test_order, mock_toss_client, caplog):
        """결제 승인 시 로깅 확인"""
        import logging

        # logger 이름을 명시하여 로그 캡처
        caplog.set_level(logging.INFO, logger="shopping.services.payment_service")

        # Arrange
        payment = PaymentService.create_payment(test_order, "card")

        mock_instance = mock_toss_client.return_value
        mock_instance.confirm_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "orderId": test_order.order_number,
            "status": "DONE",
            "totalAmount": int(test_order.final_amount),
            "method": "카드",
            "receiptUrl": "http://receipt.url",
        }

        # Act
        PaymentService.confirm_payment(
            payment=payment,
            payment_key="test_payment_key_123",
            order_id=test_order.order_number,
            amount=int(test_order.final_amount),
            user=test_user,
        )

        # Assert - caplog.records를 사용하여 로그 메시지 확인
        log_messages = [record.message for record in caplog.records]
        assert any("결제 승인 시작" in msg for msg in log_messages)
        assert any("토스페이먼츠 결제 승인 요청" in msg for msg in log_messages)
        assert any("토스페이먼츠 결제 승인 성공" in msg for msg in log_messages)
        assert any("판매량 증가" in msg for msg in log_messages)
        assert any("포인트 적립" in msg for msg in log_messages)
        assert any("결제 승인 완료" in msg for msg in log_messages)


@pytest.mark.django_db
class TestPaymentServiceCancelPayment:
    """결제 취소 테스트"""

    def test_cancel_payment_success(self, test_user, test_order, product, mock_toss_client):
        """결제 취소 성공"""
        # Arrange
        # 주문 생성 후 재고 확인 (주문 생성 시 이미 재고가 차감됨)
        product.refresh_from_db()
        stock_after_order = product.stock
        initial_sold_count = product.sold_count

        payment = PaymentService.create_payment(test_order, "card")

        # 먼저 결제 승인
        mock_instance = mock_toss_client.return_value
        mock_instance.confirm_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "orderId": test_order.order_number,
            "status": "DONE",
            "totalAmount": int(test_order.final_amount),
            "method": "카드",
            "receiptUrl": "http://receipt.url",
        }

        PaymentService.confirm_payment(
            payment=payment,
            payment_key="test_payment_key_123",
            order_id=test_order.order_number,
            amount=int(test_order.final_amount),
            user=test_user,
        )

        # 취소 API 모킹
        mock_instance.cancel_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "status": "CANCELED",
            "canceledAmount": int(test_order.final_amount),
        }

        # 결제 승인 후 sold_count 확인
        product.refresh_from_db()
        sold_count_after_confirm = product.sold_count
        test_order.refresh_from_db()
        earned_points = test_order.earned_points

        # Act
        result = PaymentService.cancel_payment(
            payment_id=payment.id,
            user=test_user,
            cancel_reason="단순 변심",
        )

        # Assert
        payment.refresh_from_db()
        assert payment.status == "canceled"
        assert payment.is_canceled

        # 주문 상태 확인
        test_order.refresh_from_db()
        assert test_order.status == "canceled"

        # 재고 복구 및 sold_count 차감 확인
        product.refresh_from_db()
        assert product.stock == stock_after_order + 1  # 주문 시 차감된 재고가 복구됨
        assert product.sold_count == sold_count_after_confirm - 1  # 승인 시 증가한 sold_count 차감

        # 적립 포인트 차감 확인
        assert result["points_deducted"] == earned_points

    def test_cancel_payment_with_used_points(self, test_user, product, mock_toss_client):
        """포인트 사용한 결제 취소 (포인트 환불)"""
        # Arrange
        cart = Cart.objects.create(user=test_user, is_active=True)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        shipping_info = {
            "shipping_name": "홍길동",
            "shipping_phone": "010-1234-5678",
            "shipping_postal_code": "12345",
            "shipping_address": "서울시 강남구",
            "shipping_address_detail": "101동 101호",
            "order_memo": "",
        }

        use_points = 5000
        order = OrderService.create_order_from_cart(
            user=test_user,
            cart=cart,
            use_points=use_points,
            **shipping_info,
        )

        payment = PaymentService.create_payment(order, "card")

        # 결제 승인
        mock_instance = mock_toss_client.return_value
        mock_instance.confirm_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "orderId": order.order_number,
            "status": "DONE",
            "totalAmount": int(order.final_amount),
            "method": "카드",
            "receiptUrl": "http://receipt.url",
        }

        PaymentService.confirm_payment(
            payment=payment,
            payment_key="test_payment_key_123",
            order_id=order.order_number,
            amount=int(order.final_amount),
            user=test_user,
        )

        # 결제 승인 후 포인트 확인
        test_user.refresh_from_db()
        points_after_confirm = test_user.points
        order.refresh_from_db()
        earned_points = order.earned_points

        # 취소 API 모킹
        mock_instance.cancel_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "status": "CANCELED",
            "canceledAmount": int(order.final_amount),
        }

        # Act
        result = PaymentService.cancel_payment(
            payment_id=payment.id,
            user=test_user,
            cancel_reason="단순 변심",
        )

        # Assert
        # 사용한 포인트 환불 확인
        assert result["points_refunded"] == use_points
        assert result["points_deducted"] == earned_points

        test_user.refresh_from_db()
        # points_after_confirm + 환불포인트 - 적립포인트차감
        expected_points = points_after_confirm + use_points - earned_points
        assert test_user.points == expected_points

    def test_cancel_payment_already_canceled(self, test_user, test_order, mock_toss_client):
        """이미 취소된 결제 재취소 시도"""
        # Arrange
        payment = PaymentService.create_payment(test_order, "card")

        # 결제 승인
        mock_instance = mock_toss_client.return_value
        mock_instance.confirm_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "orderId": test_order.order_number,
            "status": "DONE",
            "totalAmount": int(test_order.final_amount),
            "method": "카드",
            "receiptUrl": "http://receipt.url",
        }

        PaymentService.confirm_payment(
            payment=payment,
            payment_key="test_payment_key_123",
            order_id=test_order.order_number,
            amount=int(test_order.final_amount),
            user=test_user,
        )

        # 첫 번째 취소
        mock_instance.cancel_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "status": "CANCELED",
            "canceledAmount": int(test_order.final_amount),
        }

        PaymentService.cancel_payment(
            payment_id=payment.id,
            user=test_user,
            cancel_reason="단순 변심",
        )

        # Act & Assert - 두 번째 취소 시도
        with pytest.raises(PaymentCancelError) as exc_info:
            PaymentService.cancel_payment(
                payment_id=payment.id,
                user=test_user,
                cancel_reason="단순 변심",
            )

        assert "이미 취소된 결제입니다" in str(exc_info.value)

    def test_cancel_payment_invalid_status(self, test_user, test_order):
        """취소 불가능한 상태의 결제 취소 시도"""
        # Arrange
        payment = PaymentService.create_payment(test_order, "card")
        # payment 상태가 "ready"인 상태 (아직 승인되지 않음)

        # Act & Assert
        with pytest.raises(PaymentCancelError) as exc_info:
            PaymentService.cancel_payment(
                payment_id=payment.id,
                user=test_user,
                cancel_reason="단순 변심",
            )

        assert "취소할 수 없는 결제 상태입니다" in str(exc_info.value)

    def test_cancel_payment_toss_error(self, test_user, test_order, mock_toss_client):
        """토스페이먼츠 API 에러 시 처리"""
        # Arrange
        payment = PaymentService.create_payment(test_order, "card")

        # 결제 승인
        mock_instance = mock_toss_client.return_value
        mock_instance.confirm_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "orderId": test_order.order_number,
            "status": "DONE",
            "totalAmount": int(test_order.final_amount),
            "method": "카드",
            "receiptUrl": "http://receipt.url",
        }

        PaymentService.confirm_payment(
            payment=payment,
            payment_key="test_payment_key_123",
            order_id=test_order.order_number,
            amount=int(test_order.final_amount),
            user=test_user,
        )

        # 취소 시 에러 발생
        mock_instance.cancel_payment.side_effect = TossPaymentError(
            code="CANCEL_FAILED",
            message="취소 실패",
        )

        # Act & Assert
        with pytest.raises(PaymentCancelError) as exc_info:
            PaymentService.cancel_payment(
                payment_id=payment.id,
                user=test_user,
                cancel_reason="단순 변심",
            )

        assert "결제 취소 실패" in str(exc_info.value)

    def test_cancel_payment_logging(self, test_user, test_order, mock_toss_client, caplog):
        """결제 취소 시 로깅 확인"""
        import logging

        # logger 이름을 명시하여 로그 캡처
        caplog.set_level(logging.INFO, logger="shopping.services.payment_service")

        # Arrange
        payment = PaymentService.create_payment(test_order, "card")

        mock_instance = mock_toss_client.return_value
        mock_instance.confirm_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "orderId": test_order.order_number,
            "status": "DONE",
            "totalAmount": int(test_order.final_amount),
            "method": "카드",
            "receiptUrl": "http://receipt.url",
        }

        PaymentService.confirm_payment(
            payment=payment,
            payment_key="test_payment_key_123",
            order_id=test_order.order_number,
            amount=int(test_order.final_amount),
            user=test_user,
        )

        mock_instance.cancel_payment.return_value = {
            "paymentKey": "test_payment_key_123",
            "status": "CANCELED",
            "canceledAmount": int(test_order.final_amount),
        }

        # Act
        PaymentService.cancel_payment(
            payment_id=payment.id,
            user=test_user,
            cancel_reason="단순 변심",
        )

        # Assert - caplog.records를 사용하여 로그 메시지 확인
        log_messages = [record.message for record in caplog.records]
        assert any("결제 취소 시작" in msg for msg in log_messages)
        assert any("결제 취소 검증 완료" in msg for msg in log_messages)
        assert any("토스페이먼츠 결제 취소 요청" in msg for msg in log_messages)
        assert any("토스페이먼츠 결제 취소 성공" in msg for msg in log_messages)
        assert any("재고 복구" in msg for msg in log_messages)
        assert any("결제 취소 완료" in msg for msg in log_messages)
