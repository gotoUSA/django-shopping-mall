"""
포인트 태스크 테스트

point_tasks.py의 미커버 라인 테스트:
- expire_points_task 예외 처리 (46-50)
- send_expiry_notification_task (66-86)
- send_email_notification (108-125)
- add_points_after_payment 경계/예외 케이스 (162-163, 174-175, 208->216, 226-239)
"""

import pytest
from decimal import Decimal

from shopping.tasks.point_tasks import (
    expire_points_task,
    send_expiry_notification_task,
    send_email_notification,
    add_points_after_payment,
)
from shopping.tests.factories import (
    UserFactory,
    OrderFactory,
    OrderItemFactory,
    PaymentFactory,
    ProductFactory,
)


@pytest.mark.django_db(transaction=True)
class TestExpirePointsTaskException:
    """포인트 만료 태스크 예외 케이스"""

    def test_retry_on_service_error(self, mocker):
        """서비스 에러 발생 시 태스크가 재시도됨"""
        # Arrange: 지연 import되므로 원본 위치를 mock
        mocker.patch(
            "shopping.services.point_service.PointService.expire_points",
            side_effect=Exception("DB connection error"),
        )

        # Act & Assert
        with pytest.raises(Exception):
            expire_points_task.apply(throw=True)


@pytest.mark.django_db(transaction=True)
class TestSendExpiryNotificationTaskHappyPath:
    """만료 알림 태스크 정상 케이스"""

    def test_sends_notification_successfully(self, mocker):
        """알림 발송이 성공적으로 완료됨"""
        # Arrange: 지연 import되므로 원본 위치를 mock
        mock_service = mocker.patch(
            "shopping.services.point_service.PointService.send_expiry_notifications",
            return_value=5,
        )

        # Act
        result = send_expiry_notification_task()

        # Assert
        assert result["status"] == "success"
        assert result["notification_count"] == 5
        assert "5명에게 만료 예정 알림을 발송했습니다" in result["message"]
        mock_service.assert_called_once()


@pytest.mark.django_db(transaction=True)
class TestSendExpiryNotificationTaskException:
    """만료 알림 태스크 예외 케이스"""

    def test_retry_on_service_error(self, mocker):
        """서비스 에러 발생 시 태스크가 재시도됨"""
        # Arrange: 지연 import되므로 원본 위치를 mock
        mocker.patch(
            "shopping.services.point_service.PointService.send_expiry_notifications",
            side_effect=Exception("Email service unavailable"),
        )

        # Act & Assert
        with pytest.raises(Exception):
            send_expiry_notification_task.apply(throw=True)


@pytest.mark.django_db(transaction=True)
class TestSendEmailNotificationHappyPath:
    """이메일 발송 태스크 정상 케이스"""

    def test_sends_email_successfully(self, mocker):
        """이메일이 성공적으로 발송됨"""
        # Arrange
        mock_send_mail = mocker.patch(
            "shopping.tasks.point_tasks.send_mail",
            return_value=1,
        )

        # Act
        result = send_email_notification(
            email="test@example.com",
            subject="테스트 제목",
            message="테스트 메시지",
            html_message="<p>테스트</p>",
        )

        # Assert
        assert result is True
        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args
        assert call_kwargs.kwargs["recipient_list"] == ["test@example.com"]
        assert call_kwargs.kwargs["subject"] == "테스트 제목"


@pytest.mark.django_db(transaction=True)
class TestSendEmailNotificationException:
    """이메일 발송 태스크 예외 케이스"""

    def test_retry_on_smtp_error(self, mocker):
        """SMTP 에러 발생 시 태스크가 재시도됨"""
        # Arrange
        mocker.patch(
            "shopping.tasks.point_tasks.send_mail",
            side_effect=Exception("SMTP connection failed"),
        )

        # Act & Assert
        with pytest.raises(Exception):
            send_email_notification.apply(
                args=("test@example.com", "제목", "메시지"),
                throw=True,
            )


@pytest.mark.django_db(transaction=True)
class TestAddPointsAfterPaymentHappyPath:
    """결제 후 포인트 적립 정상 케이스"""

    def test_adds_points_for_paid_order(self, mocker):
        """결제 완료된 주문에 포인트가 적립됨"""
        # Arrange
        user = UserFactory.with_membership(level="silver")
        product = ProductFactory()
        order = OrderFactory(
            user=user,
            status="paid",
            total_amount=Decimal("50000"),
            final_amount=Decimal("50000"),
        )
        OrderItemFactory(order=order, product=product)

        # 지연 import되므로 원본 위치를 mock
        mock_add_points = mocker.patch(
            "shopping.services.point_service.PointService.add_points",
            return_value=True,
        )

        # Act
        result = add_points_after_payment(user_id=user.id, order_id=order.id)

        # Assert
        assert result["status"] == "success"
        assert result["points_added"] == 1000  # 50000 * 2% (silver)
        mock_add_points.assert_called_once()

    def test_creates_payment_log_when_payment_exists(self, mocker):
        """Payment가 존재할 때 PaymentLog가 생성됨"""
        # Arrange
        user = UserFactory.with_membership(level="bronze")
        product = ProductFactory()
        order = OrderFactory(
            user=user,
            status="paid",
            total_amount=Decimal("10000"),
            final_amount=Decimal("10000"),
        )
        OrderItemFactory(order=order, product=product)
        PaymentFactory.done(order=order)

        # 지연 import되므로 원본 위치를 mock
        mocker.patch(
            "shopping.services.point_service.PointService.add_points",
            return_value=True,
        )

        # Act
        result = add_points_after_payment(user_id=user.id, order_id=order.id)

        # Assert
        assert result["status"] == "success"
        order.refresh_from_db()
        assert order.earned_points == 100  # 10000 * 1% (bronze)

        # PaymentLog 생성 확인
        from shopping.models.payment import PaymentLog

        log = PaymentLog.objects.filter(payment=order.payment).first()
        assert log is not None
        assert "포인트" in log.message


@pytest.mark.django_db(transaction=True)
class TestAddPointsAfterPaymentBoundary:
    """결제 후 포인트 적립 경계 케이스"""

    def test_skips_when_full_point_payment(self):
        """포인트 전액 결제 시 적립을 스킵함"""
        # Arrange
        user = UserFactory.with_points(50000)
        product = ProductFactory()
        order = OrderFactory(
            user=user,
            status="paid",
            total_amount=Decimal("10000"),
            used_points=10000,
            final_amount=Decimal("0"),  # 포인트 전액 결제
        )
        OrderItemFactory(order=order, product=product)

        # Act
        result = add_points_after_payment(user_id=user.id, order_id=order.id)

        # Assert
        assert result["status"] == "skipped"
        assert "포인트 전액 결제" in result["message"]

    def test_skips_when_zero_points_to_earn(self):
        """적립 포인트가 0 이하일 때 스킵함"""
        # Arrange
        user = UserFactory.with_membership(level="bronze")  # 1%
        product = ProductFactory()
        order = OrderFactory(
            user=user,
            status="paid",
            total_amount=Decimal("50"),
            final_amount=Decimal("50"),  # 50 * 1% = 0.5 -> int 0
        )
        OrderItemFactory(order=order, product=product)

        # Act
        result = add_points_after_payment(user_id=user.id, order_id=order.id)

        # Assert
        assert result["status"] == "skipped"
        assert "적립할 포인트 없음" in result["message"]


@pytest.mark.django_db(transaction=True)
class TestAddPointsAfterPaymentException:
    """결제 후 포인트 적립 예외 케이스"""

    def test_returns_failed_when_user_not_found(self):
        """존재하지 않는 사용자 ID로 호출 시 실패 반환"""
        # Arrange
        product = ProductFactory()
        user = UserFactory()
        order = OrderFactory(user=user)
        OrderItemFactory(order=order, product=product)
        non_existent_user_id = 99999

        # Act
        result = add_points_after_payment(
            user_id=non_existent_user_id,
            order_id=order.id,
        )

        # Assert
        assert result["status"] == "failed"
        assert result["user_id"] == non_existent_user_id

    def test_returns_failed_when_order_not_found(self):
        """존재하지 않는 주문 ID로 호출 시 실패 반환"""
        # Arrange
        user = UserFactory()
        non_existent_order_id = 99999

        # Act
        result = add_points_after_payment(
            user_id=user.id,
            order_id=non_existent_order_id,
        )

        # Assert
        assert result["status"] == "failed"
        assert result["order_id"] == non_existent_order_id

    def test_retry_on_unexpected_error(self, mocker):
        """예상치 못한 에러 발생 시 태스크가 재시도됨"""
        # Arrange
        user = UserFactory()
        product = ProductFactory()
        order = OrderFactory(
            user=user,
            status="paid",
            total_amount=Decimal("10000"),
            final_amount=Decimal("10000"),
        )
        OrderItemFactory(order=order, product=product)

        # 지연 import되므로 원본 위치를 mock
        mocker.patch(
            "shopping.services.point_service.PointService.add_points",
            side_effect=Exception("Unexpected database error"),
        )

        # Act & Assert
        with pytest.raises(Exception):
            add_points_after_payment.apply(
                args=(user.id, order.id),
                throw=True,
            )
