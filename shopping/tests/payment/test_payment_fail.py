"""결제 실패 처리 테스트"""

import pytest
from rest_framework import status

from shopping.models.payment import Payment, PaymentLog


@pytest.mark.django_db
class TestPaymentFailNormalCase:
    """정상 케이스"""

    def test_user_cancel_payment(self, api_client, payment):
        """사용자 취소 (USER_CANCEL) - 가장 일반적인 케이스"""
        # Arrange
        request_data = {
            "code": "USER_CANCEL",
            "message": "사용자가 결제를 취소했습니다",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert - HTTP 응답
        assert response.status_code == status.HTTP_200_OK
        assert "결제 실패가 처리되었습니다" in response.data["message"]

        # Assert - Payment 상태 변경
        payment.refresh_from_db()
        assert payment.status == "aborted"
        assert "USER_CANCEL" in payment.fail_reason
        assert "사용자가 결제를 취소했습니다" in payment.fail_reason

    def test_timeout_payment(self, api_client, payment):
        """시간 초과 (TIMEOUT)"""
        # Arrange
        request_data = {
            "code": "TIMEOUT",
            "message": "결제 시간이 초과되었습니다",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()
        assert payment.status == "aborted"
        assert "TIMEOUT" in payment.fail_reason

    def test_invalid_card_expiration(self, api_client, payment):
        """카드 유효기간 오류"""
        # Arrange
        request_data = {
            "code": "INVALID_CARD_EXPIRATION",
            "message": "카드 유효기간이 올바르지 않습니다",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()
        assert payment.status == "aborted"
        assert "INVALID_CARD_EXPIRATION" in payment.fail_reason

    def test_exceed_daily_limit(self, api_client, payment):
        """일일 한도 초과"""
        # Arrange
        request_data = {
            "code": "EXCEED_MAX_DAILY_PAYMENT_COUNT",
            "message": "일일 결제 한도를 초과했습니다",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()
        assert payment.status == "aborted"
        assert "EXCEED_MAX_DAILY_PAYMENT_COUNT" in payment.fail_reason

    def test_provider_error(self, api_client, payment):
        """결제 승인 실패"""
        # Arrange
        request_data = {
            "code": "PROVIDER_ERROR",
            "message": "결제 승인에 실패했습니다",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()
        assert payment.status == "aborted"
        assert "PROVIDER_ERROR" in payment.fail_reason

    def test_payment_status_changed_to_aborted(self, api_client, payment):
        """Payment 상태 변경 (ready → aborted)"""
        # Arrange
        assert payment.status == "ready"

        request_data = {
            "code": "USER_CANCEL",
            "message": "결제 취소",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()
        assert payment.status == "aborted"

    def test_order_status_remains_pending(self, api_client, payment):
        """주문 상태는 pending 유지"""
        # Arrange
        order = payment.order
        assert order.status == "pending"

        request_data = {
            "code": "USER_CANCEL",
            "message": "결제 취소",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.status == "pending"  # 주문 상태는 변경되지 않음

    def test_fail_log_created(self, api_client, payment):
        """실패 로그 기록 확인"""
        # Arrange
        initial_log_count = PaymentLog.objects.filter(payment=payment).count()

        request_data = {
            "code": "USER_CANCEL",
            "message": "결제 취소",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        # 로그 생성 확인
        logs = PaymentLog.objects.filter(payment=payment, log_type="error")
        assert logs.exists()

        log = logs.first()
        assert "결제 실패" in log.message
        assert log.data["code"] == "USER_CANCEL"
        assert log.data["message"] == "결제 취소"

        # 로그 개수 증가 확인
        final_log_count = PaymentLog.objects.filter(payment=payment).count()
        assert final_log_count > initial_log_count

    def test_response_data_structure(self, api_client, payment):
        """응답 데이터 구조 검증"""
        # Arrange
        request_data = {
            "code": "USER_CANCEL",
            "message": "결제 취소",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data

        # 필수 필드 확인
        required_fields = [
            "message",
            "payment_id",
            "order_id",
            "order_number",
            "status",
            "fail_code",
            "fail_message",
        ]
        for field in required_fields:
            assert field in data, f"필수 필드 누락: {field}"

        # 데이터 타입 확인
        assert isinstance(data["payment_id"], int)
        assert isinstance(data["order_id"], int)
        assert isinstance(data["order_number"], str)
        assert data["status"] == "aborted"
        assert data["fail_code"] == "USER_CANCEL"

    def test_fail_reason_format(self, api_client, payment):
        """실패 사유 저장 형식 확인"""
        # Arrange
        request_data = {
            "code": "TIMEOUT",
            "message": "결제 시간 초과",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()

        # fail_reason 형식: [CODE] message
        assert payment.fail_reason == "[TIMEOUT] 결제 시간 초과"


@pytest.mark.django_db
class TestPaymentFailBoundary:
    """경계값 테스트"""

    def test_long_fail_message(self, api_client, payment):
        """긴 실패 메시지 처리"""
        # Arrange
        long_message = "실패 사유 " * 100  # 500자 이상

        request_data = {
            "code": "USER_CANCEL",
            "message": long_message,
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()
        assert payment.status == "aborted"
        assert long_message in payment.fail_reason

    def test_special_characters_in_message(self, api_client, payment):
        """특수문자 포함 메시지"""
        # Arrange
        special_message = "결제 실패: <script>alert('XSS')</script> & 특수문자 \"테스트\""

        request_data = {
            "code": "USER_CANCEL",
            "message": special_message,
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()
        assert payment.status == "aborted"
        assert special_message in payment.fail_reason

    def test_minimal_required_fields(self, api_client, payment):
        """최소 필수 필드만 전송"""
        # Arrange
        request_data = {
            "code": "ERROR",
            "message": "실패",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()
        assert payment.status == "aborted"

    def test_unicode_characters_in_message(self, api_client, payment):
        """유니코드 문자 포함 메시지"""
        # Arrange
        unicode_message = "결제 실패 😢 カード エラー 💳"

        request_data = {
            "code": "USER_CANCEL",
            "message": unicode_message,
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        payment.refresh_from_db()
        assert unicode_message in payment.fail_reason


@pytest.mark.django_db
class TestPaymentFailException:
    """예외 케이스"""

    def test_nonexistent_order_id(self, api_client):
        """존재하지 않는 order_id"""
        # Arrange
        request_data = {
            "code": "USER_CANCEL",
            "message": "결제 취소",
            "order_id": "NONEXISTENT_ORDER_ID_99999",
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "결제 정보를 찾을 수 없습니다" in str(response.data)

    def test_already_done_payment(self, api_client, user, product):
        """이미 완료된 결제 (done 상태)"""
        # Arrange - 완료된 결제 생성
        from django.utils import timezone

        from shopping.models.order import Order, OrderItem

        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구 테스트로 123",
            shipping_address_detail="101동 202호",
            order_number="20250115999001",
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
            status="done",  # 이미 완료된 상태
            toss_order_id=order.order_number,
            payment_key="test_done_payment_key",
            approved_at=timezone.now(),
        )

        request_data = {
            "code": "USER_CANCEL",
            "message": "결제 취소",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "이미 완료된 결제입니다" in str(response.data)

    def test_already_canceled_payment(self, api_client, user, product):
        """이미 취소된 결제"""
        # Arrange - 취소된 결제 생성
        from django.utils import timezone

        from shopping.models.order import Order, OrderItem

        order = Order.objects.create(
            user=user,
            status="canceled",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구 테스트로 123",
            shipping_address_detail="101동 202호",
            order_number="20250115999002",
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
            status="canceled",  # 이미 취소된 상태
            is_canceled=True,
            toss_order_id=order.order_number,
            payment_key="test_canceled_payment_key",
            canceled_at=timezone.now(),
        )

        request_data = {
            "code": "USER_CANCEL",
            "message": "결제 취소",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "이미 취소된 결제입니다" in str(response.data)

    def test_missing_code_field(self, api_client, payment):
        """필수 필드 누락 - code"""
        # Arrange
        request_data = {
            # "code": "USER_CANCEL",  # 누락
            "message": "결제 취소",
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "code" in str(response.data)

    def test_missing_message_field(self, api_client, payment):
        """필수 필드 누락 - message"""
        # Arrange
        request_data = {
            "code": "USER_CANCEL",
            # "message": "결제 취소",  # 누락
            "order_id": payment.toss_order_id,
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "message" in str(response.data)

    def test_missing_order_id_field(self, api_client):
        """필수 필드 누락 - order_id"""
        # Arrange
        request_data = {
            "code": "USER_CANCEL",
            "message": "결제 취소",
            # "order_id": payment.toss_order_id,  # 누락
        }

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "order_id" in str(response.data)

    def test_empty_request_body(self, api_client):
        """빈 요청 본문"""
        # Arrange
        request_data = {}

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_json_format(self, api_client):
        """잘못된 JSON 형식"""
        # Arrange - 문자열로 전송
        request_data = "invalid_json"

        # Act
        response = api_client.post(
            "/api/payments/fail/",
            request_data,
            content_type="application/json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
