"""
결제 취소 웹훅 테스트 (PAYMENT.CANCELED)

토스페이먼츠 PAYMENT.CANCELED 이벤트 처리 및 중복 요청 방지 테스트
"""

from decimal import Decimal

import pytest
from rest_framework import status

from shopping.models.payment import PaymentLog
from shopping.models.point import PointHistory


@pytest.mark.django_db
class TestPaymentCanceledWebhook:
    """결제 취소 웹훅 처리"""

    @pytest.fixture(autouse=True)
    def setup(self, api_client, user, product, webhook_url):
        """테스트 환경 설정"""
        self.client = api_client
        self.user = user
        self.product = product
        self.webhook_url = webhook_url

    # ==========================================
    # 1단계: 정상 케이스 (Happy Path)
    # ==========================================

    def test_payment_canceled_from_paid_order(
        self, mock_verify_webhook, webhook_data_builder, webhook_signature, paid_order, paid_payment
    ):
        """paid 상태 주문의 정상적인 결제 취소 - 재고 복구 및 포인트 회수"""
        # Arrange
        mock_verify_webhook()

        # 초기 재고 및 판매 수량 저장
        initial_stock = self.product.stock
        initial_sold_count = self.product.sold_count
        initial_user_points = self.user.points

        # paid_order를 사용하기 위해 product를 paid_order의 product로 교체
        order_item = paid_order.order_items.first()
        order_item.product = self.product
        order_item.save()

        # paid_payment의 order를 paid_order로 설정
        paid_payment.order = paid_order
        paid_payment.status = "done"
        paid_payment.is_paid = True
        paid_payment.save()

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id=paid_order.order_number,
            payment_key=paid_payment.payment_key,
            cancel_reason="사용자 요청",
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 응답 검증
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Webhook processed"

        # Assert - Payment 상태 확인
        paid_payment.refresh_from_db()
        assert paid_payment.status == "canceled"
        assert paid_payment.is_canceled is True
        assert paid_payment.cancel_reason == "사용자 요청"
        assert paid_payment.canceled_at is not None

        # Assert - Order 상태 확인
        paid_order.refresh_from_db()
        assert paid_order.status == "canceled"

        # Assert - 재고 복구 확인
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock + 1
        assert self.product.sold_count == initial_sold_count - 1

        # Assert - 포인트 회수 확인 (1% 회수)
        self.user.refresh_from_db()
        expected_deducted_points = int(paid_payment.amount * Decimal("0.01"))
        assert self.user.points == initial_user_points - expected_deducted_points

        # Assert - PointHistory 생성 확인
        point_history = PointHistory.objects.filter(
            user=self.user, type="cancel_deduct"
        ).first()
        assert point_history is not None
        assert point_history.points == -expected_deducted_points

        # Assert - PaymentLog 생성 확인
        log = PaymentLog.objects.filter(
            payment=paid_payment, log_type="webhook"
        ).first()
        assert log is not None
        assert "결제 취소" in log.message

    def test_payment_canceled_from_preparing_order(
        self, mock_verify_webhook, webhook_data_builder, webhook_signature, order, payment
    ):
        """preparing 상태 주문의 결제 취소 - 재고 복구"""
        # Arrange
        mock_verify_webhook()

        # Order를 paid -> preparing 상태로 시뮬레이션
        order.status = "preparing"
        order.save()

        payment.status = "done"
        payment.is_paid = True
        payment.save()

        # 재고 차감 시뮬레이션 (결제 완료 시 차감됨)
        self.product.stock -= 1
        self.product.sold_count += 1
        self.product.save()

        initial_stock = self.product.stock
        initial_sold_count = self.product.sold_count

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id=order.order_number,
            payment_key=payment.payment_key,
            cancel_reason="배송 준비 중 취소",
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 응답 검증
        assert response.status_code == status.HTTP_200_OK

        # Assert - 재고 복구 확인
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock + 1
        assert self.product.sold_count == initial_sold_count - 1

    def test_payment_canceled_with_multiple_items(
        self,
        mock_verify_webhook,
        webhook_data_builder,
        webhook_signature,
        order_with_multiple_items,
        multiple_products,
    ):
        """여러 상품이 포함된 주문의 결제 취소"""
        # Arrange
        from shopping.models.payment import Payment

        mock_verify_webhook()

        # Order를 paid 상태로 설정
        order_with_multiple_items.status = "paid"
        order_with_multiple_items.save()

        payment = Payment.objects.create(
            order=order_with_multiple_items,
            amount=order_with_multiple_items.total_amount,
            status="done",
            is_paid=True,
            toss_order_id=order_with_multiple_items.order_number,
            payment_key="test_key_multi_cancel",
        )

        # 재고 차감 시뮬레이션
        for product in multiple_products:
            product.stock -= 1
            product.sold_count += 1
            product.save()

        initial_stocks = {p.id: p.stock for p in multiple_products}
        initial_sold_counts = {p.id: p.sold_count for p in multiple_products}

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id=order_with_multiple_items.order_number,
            payment_key="test_key_multi_cancel",
            cancel_reason="다중 상품 주문 취소",
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 응답 검증
        assert response.status_code == status.HTTP_200_OK

        # Assert - 모든 상품의 재고 복구 확인
        for product in multiple_products:
            product.refresh_from_db()
            assert product.stock == initial_stocks[product.id] + 1
            assert product.sold_count == initial_sold_counts[product.id] - 1

    # ==========================================
    # 2단계: 경계값/중복 케이스 (Boundary)
    # ==========================================

    def test_payment_canceled_duplicate_request(
        self, mock_verify_webhook, webhook_data_builder, webhook_signature, order, payment
    ):
        """중복 취소 요청 - 이미 취소된 결제"""
        # Arrange
        mock_verify_webhook()

        # Payment를 이미 취소 상태로 설정
        payment.status = "canceled"
        payment.is_canceled = True
        payment.cancel_reason = "이미 취소됨"
        payment.save()

        # Order도 취소 상태로 설정
        order.status = "canceled"
        order.save()

        initial_stock = self.product.stock

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id=order.order_number,
            payment_key=payment.payment_key,
            cancel_reason="중복 취소 시도",
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 응답 검증
        assert response.status_code == status.HTTP_200_OK

        # Assert - 재고가 중복 복구되지 않았는지 확인
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock

    def test_payment_canceled_order_already_canceled(
        self, mock_verify_webhook, webhook_data_builder, webhook_signature, order, payment
    ):
        """주문이 이미 canceled 상태인 경우"""
        # Arrange
        mock_verify_webhook()

        # Order를 이미 canceled 상태로 설정
        order.status = "canceled"
        order.save()

        initial_stock = self.product.stock

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id=order.order_number,
            payment_key=payment.payment_key,
            cancel_reason="이미 취소된 주문",
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 응답 검증
        assert response.status_code == status.HTTP_200_OK

        # Assert - Payment는 업데이트되어야 함
        payment.refresh_from_db()
        assert payment.status == "canceled"
        assert payment.is_canceled is True

        # Assert - 재고는 중복 복구되지 않아야 함
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock

    def test_payment_canceled_from_pending_order(
        self, mock_verify_webhook, webhook_data_builder, webhook_signature, order, payment
    ):
        """pending 상태 주문 취소 - 재고 복구 안됨"""
        # Arrange
        mock_verify_webhook()

        # Order는 pending 상태 유지
        assert order.status == "pending"

        initial_stock = self.product.stock

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id=order.order_number,
            payment_key=payment.payment_key,
            cancel_reason="결제 전 취소",
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 응답 검증
        assert response.status_code == status.HTTP_200_OK

        # Assert - Payment 상태 확인
        payment.refresh_from_db()
        assert payment.status == "canceled"
        assert payment.is_canceled is True

        # Assert - Order 상태 확인
        order.refresh_from_db()
        assert order.status == "canceled"

        # Assert - 재고는 복구되지 않음 (원래 차감 안됨)
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock

    def test_payment_canceled_stock_recovery_zero_sold_count(
        self, mock_verify_webhook, webhook_data_builder, webhook_signature, order, payment
    ):
        """sold_count가 0일 때 음수 방지 확인"""
        # Arrange
        mock_verify_webhook()

        # Order를 paid 상태로 설정
        order.status = "paid"
        order.save()

        payment.status = "done"
        payment.is_paid = True
        payment.save()

        # sold_count를 0으로 설정 (비정상 상황 시뮬레이션)
        self.product.sold_count = 0
        self.product.save()

        initial_stock = self.product.stock

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id=order.order_number,
            payment_key=payment.payment_key,
            cancel_reason="sold_count 0 테스트",
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 응답 검증
        assert response.status_code == status.HTTP_200_OK

        # Assert - sold_count는 음수가 되지 않아야 함
        self.product.refresh_from_db()
        assert self.product.sold_count >= 0
        assert self.product.stock == initial_stock + 1

    # ==========================================
    # 3단계: 예외 케이스 (Exception)
    # ==========================================

    def test_payment_canceled_user_none(
        self, mock_verify_webhook, webhook_data_builder, webhook_signature, order, payment
    ):
        """user가 None인 경우 포인트 회수 스킵"""
        # Arrange
        mock_verify_webhook()

        # Order를 paid 상태로 설정하고 user를 None으로 설정
        order.status = "paid"
        order.user = None
        order.save()

        payment.status = "done"
        payment.is_paid = True
        payment.save()

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id=order.order_number,
            payment_key=payment.payment_key,
            cancel_reason="비회원 주문 취소",
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 에러 없이 처리되어야 함
        assert response.status_code == status.HTTP_200_OK

        # Assert - Payment 상태는 업데이트됨
        payment.refresh_from_db()
        assert payment.status == "canceled"
        assert payment.is_canceled is True

        # Assert - PointHistory가 생성되지 않음
        point_history = PointHistory.objects.filter(type="cancel_deduct").first()
        assert point_history is None

    def test_payment_canceled_payment_not_found(
        self, mock_verify_webhook, webhook_data_builder, webhook_signature
    ):
        """Payment가 존재하지 않는 경우"""
        # Arrange
        mock_verify_webhook()

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id="nonexistent_order_123",
            payment_key="nonexistent_payment_key",
            cancel_reason="존재하지 않는 결제",
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 웹훅은 성공 응답 (로그만 남기고 처리)
        assert response.status_code == status.HTTP_200_OK

    def test_payment_canceled_insufficient_user_points(
        self, mock_verify_webhook, webhook_data_builder, webhook_signature, order, payment
    ):
        """사용자 포인트가 부족할 때 회수 시도"""
        # Arrange
        mock_verify_webhook()

        # Order를 paid 상태로 설정
        order.status = "paid"
        order.save()

        payment.status = "done"
        payment.is_paid = True
        payment.amount = Decimal("1000000")  # 큰 금액으로 설정
        payment.save()

        # 사용자 포인트를 매우 낮게 설정
        self.user.points = 10
        self.user.save()

        initial_points = self.user.points

        webhook_data = webhook_data_builder(
            event_type="PAYMENT.CANCELED",
            order_id=order.order_number,
            payment_key=payment.payment_key,
            cancel_reason="포인트 부족 테스트",
            amount=int(payment.amount),
        )

        # Act
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE=webhook_signature,
        )

        # Assert - 응답 검증
        assert response.status_code == status.HTTP_200_OK

        # Assert - Payment는 취소 처리됨
        payment.refresh_from_db()
        assert payment.status == "canceled"
        assert payment.is_canceled is True

        # Assert - 포인트는 음수가 될 수 있음 (비즈니스 로직에 따라)
        self.user.refresh_from_db()
        expected_deducted_points = int(payment.amount * Decimal("0.01"))
        assert self.user.points == initial_points - expected_deducted_points
