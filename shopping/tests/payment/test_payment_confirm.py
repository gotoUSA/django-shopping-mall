from decimal import Decimal
from unittest.mock import Mock

import pytest
from rest_framework import status

from shopping.models.cart import Cart, CartItem
from shopping.models.order import Order
from shopping.models.payment import Payment, PaymentLog
from shopping.models.point import PointHistory
from shopping.models.product import Product
from shopping.utils.toss_payment import TossPaymentError


@pytest.mark.django_db
class TestPaymentConfirm:
    """정상 케이스"""

    def test_successful_payment_confirmation(
        self,
        authenticated_client,
        user,
        order,
        payment,
        product,
        mocker,
    ):
        """정상 결제 승인 + 전체 부가 효과 검증"""
        # Arrange
        user.points = 5000
        user.save()

        # 장바구니 활성화 (비활성화 테스트용)
        cart = Cart.objects.create(user=user, is_active=True)

        toss_response = {
            "paymentKey": "test_payment_key_123",
            "orderId": order.order_number,
            "status": "DONE",
            "totalAmount": int(payment.amount),
            "method": "카드",
            "approvedAt": "2025-01-15T10:00:00+09:00",
            "card": {
                "company": "신한카드",
                "number": "1234****",
                "installmentPlanMonths": 0,
            },
        }

        mock_confirm = mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            return_value=toss_response,
        )

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_payment_key_123",
            "amount": int(payment.amount),
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert - HTTP 응답
        assert response.status_code == status.HTTP_200_OK
        assert "결제가 완료되었습니다" in response.data["message"]
        assert "payment" in response.data
        assert "points_earned" in response.data

        # Assert - Payment 상태 변경 (ready → done)
        payment.refresh_from_db()
        assert payment.status == "done"
        assert payment.payment_key == "test_payment_key_123"
        assert payment.method == "카드"
        assert payment.card_company == "신한카드"
        assert payment.is_paid is True

        # Assert - Order 상태 변경 (pending → paid)
        order.refresh_from_db()
        assert order.status == "paid"
        assert order.payment_method == "카드"

        # Assert - 포인트 적립 (final_amount의 1%)
        user.refresh_from_db()
        expected_earn = int(order.final_amount * Decimal("0.01"))
        assert user.points == 5000 + expected_earn

        # Assert - 포인트 이력 기록
        point_history = PointHistory.objects.filter(
            user=user,
            type="earn",
            order=order,
        ).first()
        assert point_history is not None
        assert point_history.points == expected_earn
        assert f"주문 #{order.order_number} 구매 적립" in point_history.description

        # Assert - 장바구니 비활성화
        cart.refresh_from_db()
        assert cart.is_active is False

        # Assert - sold_count 증가
        product.refresh_from_db()
        assert product.sold_count == 1

        # Assert - 결제 로그 기록
        logs = PaymentLog.objects.filter(payment=payment)
        assert logs.count() >= 2  # 적립 로그 + 승인 로그
        assert logs.filter(log_type="approve", message="결제 승인 완료").exists()

        # Assert - 토스 API 호출 확인
        mock_confirm.assert_called_once_with(
            payment_key="test_payment_key_123",
            order_id=order.order_number,
            amount=int(payment.amount),
        )

    def test_payment_with_partial_points_usage(
        self,
        authenticated_client,
        user,
        product,
        add_to_cart_helper,
        shipping_data,
        mocker,
    ):
        """포인트 일부 사용 후 결제"""
        # Arrange
        user.points = 5000
        user.save()

        add_to_cart_helper(user, product, quantity=1)

        # 주문 생성 (2000P 사용)
        order_data = {**shipping_data, "use_points": 2000}
        order_response = authenticated_client.post(
            "/api/orders/",
            order_data,
            format="json",
        )
        assert order_response.status_code == status.HTTP_201_CREATED

        order = Order.objects.filter(user=user).order_by("-created_at").first()
        assert order.used_points == 2000

        # Payment 생성
        payment_request_response = authenticated_client.post(
            "/api/payments/request/",
            {"order_id": order.id},
            format="json",
        )
        assert payment_request_response.status_code == status.HTTP_201_CREATED

        payment = Payment.objects.get(order=order)

        toss_response = {
            "status": "DONE",
            "approvedAt": "2025-01-15T10:00:00+09:00",
            "totalAmount": int(payment.amount),
        }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            return_value=toss_response,
        )

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_key",
            "amount": int(payment.amount),
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        user.refresh_from_db()
        order.refresh_from_db()

        # Assert - 포인트 계산 (5000 - 2000 + 적립)
        expected_earn = int(order.final_amount * Decimal("0.01"))
        assert user.points == 3000 + expected_earn

    def test_multiple_products_sold_count_increase(
        self,
        authenticated_client,
        user,
        category,
        shipping_data,
        mocker,
    ):
        """여러 상품 주문 시 sold_count 증가"""
        # Arrange
        products = [
            Product.objects.create(
                name=f"상품 {i}",
                category=category,
                price=Decimal("10000"),
                stock=10,
                sku=f"TEST-MULTI-{i:03d}",
                is_active=True,
            )
            for i in range(3)
        ]

        order = Order.objects.create(
            user=user,
            status="pending",
            total_amount=sum(p.price for p in products),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
        )

        from shopping.models.order import OrderItem

        for product in products:
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                quantity=2,
                price=product.price,
            )

        payment = Payment.objects.create(
            order=order,
            amount=order.final_amount,
            status="ready",
            toss_order_id=order.order_number,
        )

        toss_response = {
            "status": "DONE",
            "approvedAt": "2025-01-15T10:00:00+09:00",
            "totalAmount": int(payment.amount),
        }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            return_value=toss_response,
        )

        authenticated_client.force_authenticate(user=user)

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_key",
            "amount": int(payment.amount),
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        # Assert - 모든 상품의 sold_count 증가 (각 2개씩)
        for product in products:
            product.refresh_from_db()
            assert product.sold_count == 2


@pytest.mark.django_db
class TestPaymentConfirmBoundary:
    """경계값 테스트"""

    def test_full_points_payment_no_earn(
        self,
        authenticated_client,
        user,
        product,
        add_to_cart_helper,
        shipping_data,
        mocker,
    ):
        """포인트 전액 결제 - 적립 없음"""
        # Arrange
        user.points = 50000
        user.save()

        add_to_cart_helper(user, product, quantity=1)

        # 전액 포인트 결제 (final_amount = 0)
        order_data = {**shipping_data, "use_points": 13000}
        order_response = authenticated_client.post(
            "/api/orders/",
            order_data,
            format="json",
        )
        assert order_response.status_code == status.HTTP_201_CREATED

        order = Order.objects.filter(user=user).order_by("-created_at").first()
        assert order.final_amount == 0

        # Payment 생성
        payment_request_response = authenticated_client.post(
            "/api/payments/request/",
            {"order_id": order.id},
            format="json",
        )
        assert payment_request_response.status_code == status.HTTP_201_CREATED

        payment = Payment.objects.get(order=order)

        toss_response = {
            "status": "DONE",
            "approvedAt": "2025-01-15T10:00:00+09:00",
            "totalAmount": 0,
        }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            return_value=toss_response,
        )

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_key",
            "amount": 0,
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["points_earned"] == 0

        # Assert - 포인트 적립 없음
        user.refresh_from_db()
        assert user.points == 37000  # 50000 - 13000

        # Assert - 적립 이력 없음
        earn_history = PointHistory.objects.filter(
            user=user,
            type="earn",
            order=order,
        )
        assert not earn_history.exists()

        # Assert - 포인트 전액 결제 로그
        log = PaymentLog.objects.filter(
            payment=payment,
            log_type="approve",
            message__contains="포인트 13000점으로 전액 결제",
        ).first()
        assert log is not None

    def test_earn_rate_by_membership_level(
        self,
        authenticated_client,
        user_factory,
        product,
        add_to_cart_helper,
        shipping_data,
        mocker,
    ):
        """등급별 포인트 적립률 (bronze 1%, silver 2%, gold 3%, vip 5%)"""
        # Arrange
        membership_levels = ["bronze", "silver", "gold", "vip"]
        expected_rates = {"bronze": 1, "silver": 2, "gold": 3, "vip": 5}

        for level in membership_levels:
            user = user_factory(
                username=f"user_{level}",
                points=10000,
                membership_level=level,
            )

            add_to_cart_helper(user, product, quantity=1)

            authenticated_client.force_authenticate(user=user)

            # 주문 생성
            order_response = authenticated_client.post(
                "/api/orders/",
                shipping_data,
                format="json",
            )
            order = Order.objects.filter(user=user).order_by("-created_at").first()

            # Payment 생성
            authenticated_client.post(
                "/api/payments/request/",
                {"order_id": order.id},
                format="json",
            )

            payment = Payment.objects.get(order=order)

            toss_response = {
                "status": "DONE",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "totalAmount": int(payment.amount),
            }

            mocker.patch(
                "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
                return_value=toss_response,
            )

            request_data = {
                "order_id": order.order_number,
                "payment_key": "test_key",
                "amount": int(payment.amount),
            }

            # Act
            response = authenticated_client.post(
                "/api/payments/confirm/",
                request_data,
                format="json",
            )

            # Assert
            assert response.status_code == status.HTTP_200_OK

            user.refresh_from_db()
            expected_rate = expected_rates[level]
            expected_earn = int(order.final_amount * Decimal(expected_rate) / Decimal("100"))
            actual_earn = user.points - 10000

            assert actual_earn == expected_earn, f"{level} 등급 적립률 검증 실패"

            # Assert - 포인트 이력 메타데이터 확인
            point_history = PointHistory.objects.filter(
                user=user,
                type="earn",
                order=order,
            ).first()
            assert point_history.metadata["earn_rate"] == f"{expected_rate}%"
            assert point_history.metadata["membership_level"] == level


@pytest.mark.django_db
class TestPaymentConfirmException:
    """예외 케이스"""

    def test_unverified_email_user_rejected(
        self,
        api_client,
        user,
        order,
        payment,
    ):
        """이메일 미인증 사용자 거부"""
        # Arrange
        user.is_email_verified = False
        user.save()

        api_client.force_authenticate(user=user)

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_key",
            "amount": int(payment.amount),
        }

        # Act
        response = api_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "이메일 인증이 필요합니다" in response.data["error"]
        assert response.data["verification_required"] is True
        assert "verification_url" in response.data

    def test_already_paid_payment_rejected(
        self,
        authenticated_client,
        user,
        paid_order,
        paid_payment,
    ):
        """이미 완료된 결제"""
        # Arrange
        request_data = {
            "order_id": paid_order.order_number,
            "payment_key": "test_key",
            "amount": int(paid_payment.amount),
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "이미 완료된 결제입니다" in str(response.data)

    def test_missing_order_id_field(
        self,
        authenticated_client,
    ):
        """order_id 필드 없음"""
        # Arrange
        request_data = {
            "payment_key": "test_key",
            "amount": 10000,
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "order_id" in response.data

    def test_missing_payment_key_field(
        self,
        authenticated_client,
        order,
    ):
        """payment_key 필드 없음"""
        # Arrange
        request_data = {
            "order_id": order.order_number,
            "amount": 10000,
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "payment_key" in response.data

    def test_missing_amount_field(
        self,
        authenticated_client,
        order,
    ):
        """amount 필드 없음"""
        # Arrange
        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_key",
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "amount" in response.data

    def test_amount_mismatch(
        self,
        authenticated_client,
        order,
        payment,
    ):
        """금액 불일치"""
        # Arrange
        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_key",
            "amount": 99999,  # 잘못된 금액
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "결제 금액이 일치하지 않습니다" in str(response.data)

    def test_nonexistent_order_id(
        self,
        authenticated_client,
    ):
        """존재하지 않는 order_id"""
        # Arrange
        request_data = {
            "order_id": "NONEXISTENT_20250115999999",
            "payment_key": "test_key",
            "amount": 10000,
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "결제 정보를 찾을 수 없습니다" in str(response.data)

    def test_toss_api_failure(
        self,
        authenticated_client,
        user,
        order,
        payment,
        mocker,
    ):
        """토스 API 실패"""
        # Arrange
        mock_confirm = mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=TossPaymentError("PROVIDER_ERROR", "결제 승인에 실패했습니다."),
        )

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_key",
            "amount": int(payment.amount),
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "결제 승인에 실패했습니다" in response.data["error"]

        # Assert - Payment 실패 상태로 변경
        payment.refresh_from_db()
        assert payment.status == "aborted"

        # Assert - 에러 로그 기록
        error_log = PaymentLog.objects.filter(
            payment=payment,
            log_type="error",
        ).first()
        assert error_log is not None

    def test_transaction_rollback_on_error(
        self,
        authenticated_client,
        user,
        order,
        payment,
        product,
        mocker,
    ):
        """트랜잭션 롤백 확인 - 토스 API 실패 시"""
        # Arrange
        initial_points = user.points
        initial_sold_count = product.sold_count
        initial_order_status = order.status
        initial_payment_status = payment.status

        # 토스 API 실패 시뮬레이션
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=TossPaymentError("PROVIDER_ERROR", "결제 승인에 실패했습니다."),
        )

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_key",
            "amount": int(payment.amount),
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert - 에러 응답
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "결제 승인에 실패했습니다" in response.data["error"]

        # Assert - 트랜잭션 롤백으로 주요 변경사항 원복
        user.refresh_from_db()
        order.refresh_from_db()
        product.refresh_from_db()

        assert user.points == initial_points
        assert order.status == initial_order_status
        assert product.sold_count == initial_sold_count

        # Assert - Payment는 실패 상태로 변경됨 (에러 로그를 위해)
        payment.refresh_from_db()
        assert payment.status == "aborted"
