"""결제 비동기 태스크 테스트"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from shopping.models.payment import Payment
from shopping.tasks.payment_tasks import (
    call_toss_confirm_api,
    finalize_payment_confirm,
)
from shopping.tests.factories import (
    PaymentFactory,
    OrderFactory,
    ProductFactory,
    UserFactory,
    OrderItemFactory,
)


@pytest.mark.django_db(transaction=True)
class TestPaymentTasksHappyPath:
    """결제 태스크 정상 케이스"""

    def test_call_toss_api_task_success(self, mocker):
        """Toss API 호출 태스크가 성공적으로 실행됨"""
        # Arrange
        mock_response = {
            "paymentKey": "test_key_123",
            "orderId": "ORDER_123",
            "status": "DONE",
        }
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            return_value=mock_response
        )

        # Act
        result = call_toss_confirm_api(
            payment_key="test_key_123",
            order_id="ORDER_123",
            amount=10000
        )

        # Assert
        assert result == mock_response
        assert result["status"] == "DONE"

    def test_finalize_payment_task_success(self, user_factory, product):
        """결제 최종 처리 태스크가 성공적으로 실행됨"""
        # Arrange
        from django.utils import timezone

        user = user_factory()
        order = OrderFactory(user=user, status="pending")
        payment = PaymentFactory(order=order, status="ready")

        # OrderItem 생성
        order_item = OrderItemFactory(order=order, product=product, quantity=2)

        toss_response = {
            "paymentKey": "test_key",
            "status": "DONE",
            "approvedAt": timezone.now().isoformat(),  # timezone-aware datetime
        }

        # Act
        result = finalize_payment_confirm(
            toss_response=toss_response,
            payment_id=payment.id,
            user_id=user.id
        )

        # Assert
        payment.refresh_from_db()
        assert payment.is_paid
        assert payment.order.status == "paid"
        assert result["status"] == "success"

    def test_payment_chain_integration(self, user_factory, mocker, settings):
        """Toss API → 최종 처리 체인이 정상 작동"""
        # Arrange
        # 테스트 격리를 위해 eager 모드 명시적 설정
        settings.CELERY_TASK_ALWAYS_EAGER = True
        settings.CELERY_TASK_EAGER_PROPAGATES = True

        user = user_factory()
        order = OrderFactory(user=user)
        payment = PaymentFactory(order=order)

        mock_toss_response = {"status": "DONE", "paymentKey": "key123"}
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            return_value=mock_toss_response
        )

        # Act
        from celery import chain
        from shopping.tasks.payment_tasks import call_toss_confirm_api, finalize_payment_confirm

        task_chain = chain(
            call_toss_confirm_api.s("key123", "ORDER_123", 10000),
            finalize_payment_confirm.s(payment.id, user.id)
        )

        result = task_chain.apply()

        # Assert
        payment.refresh_from_db()
        assert payment.is_paid
        assert result.successful()


@pytest.mark.django_db(transaction=True)
class TestPaymentTasksBoundary:
    """결제 태스크 경계 케이스"""

    def test_duplicate_payment_confirm_ignored(self, user_factory):
        """이미 처리된 결제는 무시됨"""
        # Arrange
        user = user_factory()
        order = OrderFactory(user=user, status="paid")
        payment = PaymentFactory(order=order, status="done")

        # Act
        result = finalize_payment_confirm(
            toss_response={"status": "DONE"},
            payment_id=payment.id,
            user_id=user.id
        )

        # Assert
        assert result["status"] == "already_processed"


@pytest.mark.django_db(transaction=True)
class TestPaymentTasksException:
    """결제 태스크 예외 케이스"""

    def test_toss_api_network_error_retries(self, mocker):
        """네트워크 오류 시 재시도"""
        # Arrange
        from shopping.utils.toss_payment import TossPaymentError

        mock_client = mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=TossPaymentError("NETWORK_ERROR", "Network failed")
        )

        # Act & Assert
        with pytest.raises(Exception):  # Celery retry exception
            call_toss_confirm_api.apply(
                args=("key", "order", 10000),
                throw=True
            )

    def test_payment_not_found(self):
        """존재하지 않는 결제 ID로 최종 처리 시도"""
        # Arrange
        non_existent_id = 99999

        # Act & Assert
        with pytest.raises(Payment.DoesNotExist):
            finalize_payment_confirm(
                toss_response={"status": "DONE"},
                payment_id=non_existent_id,
                user_id=1
            )
