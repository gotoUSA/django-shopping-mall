from decimal import Decimal

from django.urls import reverse

import pytest
from rest_framework import status

from shopping.models.cart import Cart
from shopping.models.payment import Payment, PaymentLog


@pytest.mark.django_db
class TestPaymentDoneWebhook:
    """결제 승인 웹훅 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self, api_client, user, product, order, payment):
        """각 테스트마다 자동 실행되는 설정"""
        self.client = api_client
        self.user = user
        self.product = product
        self.order = order
        self.payment = payment
        self.webhook_url = reverse("toss-webhook")

    def test_payment_done_success(self, mocker):
        """정상적인 결제 승인 웹훅 처리"""
        # Mock 시그니처 검증
        mock_verify = mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "paymentKey": "test_payment_key_123",
                "orderId": self.order.order_number,
                "status": "DONE",
                "totalAmount": int(self.payment.amount),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {
                    "company": "신한카드",
                    "number": "1234****",
                    "installmentPlanMonths": 0,
                },
            },
        }

        # 웹훅 호출
        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        # 응답 검증
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Webhook processed"

        # Payment 상태 확인
        self.payment.refresh_from_db()
        assert self.payment.status == "done"
        assert self.payment.is_paid is True
        assert self.payment.payment_key == "test_payment_key_123"
        assert self.payment.method == "카드"

        # Order 상태 확인
        self.order.refresh_from_db()
        assert self.order.status == "paid"
        assert self.order.payment_method == "카드"

        # 재고 차감 확인
        self.product.refresh_from_db()
        assert self.product.stock == 9  # 10 - 1
        assert self.product.sold_count == 1

        # 포인트 적립 확인 (1%)
        self.user.refresh_from_db()
        expected_points = int(self.payment.amount * Decimal("0.01"))
        assert self.user.points == 5000 + expected_points

        # 장바구니 비활성화 확인
        active_carts = Cart.objects.filter(user=self.user, is_active=True)
        assert active_carts.count() == 0

        # PaymentLog 생성 확인
        log = PaymentLog.objects.filter(payment=self.payment, log_type="webhook").first()
        assert log is not None
        assert "결제 완료" in log.message

        # Mock 검증
        mock_verify.assert_called_once()

    def test_payment_done_with_multiple_items(self, mocker, order_with_multiple_items, multiple_products):
        """여러 상품이 포함된 주문의 결제 승인"""
        # Mock 시그니처 검증
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # Payment 생성
        payment = Payment.objects.create(
            order=order_with_multiple_items,
            amount=order_with_multiple_items.total_amount,
            status="pending",
            toss_order_id=order_with_multiple_items.order_number,
        )

        # 초기 재고 저장
        initial_stocks = {p.id: p.stock for p in multiple_products}

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "paymentKey": "test_key_multi",
                "orderId": order_with_multiple_items.order_number,
                "status": "DONE",
                "totalAmount": int(payment.amount),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # 모든 상품의 재고 차감 확인
        for product in multiple_products:
            product.refresh_from_db()
            assert product.stock == initial_stocks[product.id] - 1
            assert product.sold_count == 1

    def test_payment_done_duplicate_request(self, mocker):
        """중복 웹훅 요청 - 이미 처리된 결제"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # Payment를 이미 완료 상태로 설정
        self.payment.status = "done"
        self.payment.payment_key = "already_processed"
        self.payment.save()

        # 초기 재고 저장
        initial_stock = self.product.stock

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "paymentKey": "duplicate_key",
                "orderId": self.order.order_number,
                "status": "DONE",
                "totalAmount": int(self.payment.amount),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # 재고가 중복 차감되지 않았는지 확인
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock

    def test_payment_done_order_already_paid(self, mocker):
        """주문이 이미 paid 상태인 경우"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # Order를 이미 paid 상태로 설정
        self.order.status = "paid"
        self.order.save()

        initial_stock = self.product.stock

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "paymentKey": "test_key",
                "orderId": self.order.order_number,
                "status": "DONE",
                "totalAmount": int(self.payment.amount),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # Payment는 업데이트되어야 함
        self.payment.refresh_from_db()
        assert self.payment.status == "done"

        # 재고는 중복 차감되지 않아야 함
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock

    def test_payment_done_insufficient_stock(self, mocker):
        """재고 부족 시나리오 - 웹훅에서는 로그만 남기고 계속 진행"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # 재고를 0으로 설정
        self.product.stock = 0
        self.product.save()

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "paymentKey": "test_key",
                "orderId": self.order.order_number,
                "status": "DONE",
                "totalAmount": int(self.payment.amount),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        # 웹훅은 성공 응답
        assert response.status_code == status.HTTP_200_OK

        # Payment와 Order 상태는 업데이트됨
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        assert self.payment.status == "done"
        assert self.order.status == "paid"

    def test_payment_done_user_none(self, mocker):
        """user가 None인 경우 포인트 적립 스킵"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # Order의 user를 None으로 설정
        self.order.user = None
        self.order.save()

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "paymentKey": "test_key",
                "orderId": self.order.order_number,
                "status": "DONE",
                "totalAmount": int(self.payment.amount),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        # 에러 없이 처리되어야 함
        assert response.status_code == status.HTTP_200_OK

        # Payment 상태는 업데이트됨
        self.payment.refresh_from_db()
        assert self.payment.status == "done"

    def test_payment_done_payment_not_found(self, mocker):
        """Payment가 존재하지 않는 경우"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "paymentKey": "test_key",
                "orderId": "nonexistent_order_123",
                "status": "DONE",
                "totalAmount": 10000,
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        # 웹훅은 성공 응답 (로그만 남기고 처리)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestPaymentCanceledWebhook:
    """결제 취소 웹훅 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self, api_client, user, product, paid_order, paid_payment):
        """각 테스트마다 자동 실행되는 설정"""
        self.client = api_client
        self.user = user
        self.product = product
        self.order = paid_order
        self.payment = paid_payment
        self.webhook_url = reverse("toss-webhook")

        # 초기 재고 설정 (paid 상태이므로 이미 차감되었다고 가정)
        self.product.stock = 9  # 원래 10에서 1개 차감
        self.product.sold_count = 1
        self.product.save()

    def test_payment_canceled_success(self, mocker):
        """정상적인 결제 취소 웹훅 처리"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # 초기 포인트 저장 (적립된 포인트 포함)
        initial_points = self.user.points

        webhook_data = {
            "eventType": "PAYMENT.CANCELED",
            "data": {
                "paymentKey": self.payment.payment_key,
                "orderId": self.order.order_number,
                "status": "CANCELED",
                "cancelReason": "사용자 요청",
                "canceledAt": "2025-01-15T11:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # Payment 상태 확인
        self.payment.refresh_from_db()
        assert self.payment.is_canceled is True
        assert self.payment.status == "canceled"
        assert self.payment.cancel_reason == "사용자 요청"

        # Order 상태 확인
        self.order.refresh_from_db()
        assert self.order.status == "canceled"

        # 재고 복구 확인
        self.product.refresh_from_db()
        assert self.product.stock == 10  # 9 + 1
        assert self.product.sold_count == 0  # 1 - 1

        # 포인트 회수 확인
        self.user.refresh_from_db()
        deducted_points = int(self.payment.amount * Decimal("0.01"))
        assert self.user.points == initial_points - deducted_points

        # PaymentLog 생성 확인
        log = PaymentLog.objects.filter(payment=self.payment, log_type="webhook", message__contains="취소").first()
        assert log is not None

    def test_payment_canceled_duplicate_request(self, mocker):
        """중복 취소 요청 - 이미 취소된 결제"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # Payment를 이미 취소 상태로 설정
        self.payment.status = "canceled"
        self.payment.is_canceled = True
        self.payment.save()

        initial_stock = self.product.stock

        webhook_data = {
            "eventType": "PAYMENT.CANCELED",
            "data": {
                "paymentKey": self.payment.payment_key,
                "orderId": self.order.order_number,
                "status": "CANCELED",
                "cancelReason": "중복 요청",
                "canceledAt": "2025-01-15T11:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # 재고가 중복 복구되지 않았는지 확인
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock

    def test_payment_canceled_order_already_canceled(self, mocker):
        """주문이 이미 canceled 상태인 경우"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # Order를 이미 canceled 상태로 설정
        self.order.status = "canceled"
        self.order.save()

        initial_stock = self.product.stock

        webhook_data = {
            "eventType": "PAYMENT.CANCELED",
            "data": {
                "paymentKey": self.payment.payment_key,
                "orderId": self.order.order_number,
                "status": "CANCELED",
                "cancelReason": "중복",
                "canceledAt": "2025-01-15T11:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # 재고 중복 복구되지 않음
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock

    def test_payment_canceled_from_pending_status(self, mocker, order, payment):
        """pending 상태에서 취소 - 재고 복구 안 함"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # pending 상태의 주문 (재고 차감 안 됨)
        assert order.status == "pending"

        initial_stock = self.product.stock

        webhook_data = {
            "eventType": "PAYMENT.CANCELED",
            "data": {
                "paymentKey": "test_key",
                "orderId": order.order_number,
                "status": "CANCELED",
                "cancelReason": "결제 실패",
                "canceledAt": "2025-01-15T11:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # 재고는 변경되지 않음 (원래 차감 안 했으므로)
        self.product.refresh_from_db()
        assert self.product.stock == initial_stock

    def test_payment_canceled_with_multiple_items(self, mocker, user, multiple_products):
        """여러 상품이 포함된 주문의 취소"""
        from shopping.models.order import Order, OrderItem

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # 주문 생성 (paid 상태)
        total = sum(p.price for p in multiple_products)
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=total,
            shipping_name="테스트",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="주소",
            shipping_address_detail="상세주소",
        )

        for product in multiple_products:
            OrderItem.objects.create(order=order, product=product, quantity=1, price=product.price)

        # Payment 생성
        payment = Payment.objects.create(
            order=order,
            amount=total,
            status="done",
            toss_order_id=order.order_number,
            payment_key="multi_key",
        )

        # 재고 차감 시뮬레이션
        for product in multiple_products:
            product.stock -= 1
            product.sold_count += 1
            product.save()

        initial_stocks = {p.id: p.stock for p in multiple_products}

        webhook_data = {
            "eventType": "PAYMENT.CANCELED",
            "data": {
                "paymentKey": "multi_key",
                "orderId": order.order_number,
                "status": "CANCELED",
                "cancelReason": "전체 취소",
                "canceledAt": "2025-01-15T11:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # 모든 상품의 재고 복구 확인
        for product in multiple_products:
            product.refresh_from_db()
            assert product.stock == initial_stocks[product.id] + 1
            assert product.sold_count == 0


@pytest.mark.django_db
class TestPaymentFailedWebhook:
    """결제 실패 웹훅 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self, api_client, order, payment):
        """각 테스트마다 자동 실행되는 설정"""
        self.client = api_client
        self.order = order
        self.payment = payment
        self.webhook_url = reverse("toss-webhook")

    def test_payment_failed_success(self, mocker):
        """정상적인 결제 실패 웹훅 처리"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        webhook_data = {
            "eventType": "PAYMENT.FAILED",
            "data": {
                "orderId": self.order.order_number,
                "failReason": "카드 한도 초과",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # Payment 상태 확인
        self.payment.refresh_from_db()
        assert self.payment.status == "aborted"
        assert self.payment.fail_reason == "카드 한도 초과"

        # PaymentLog 생성 확인
        log = PaymentLog.objects.filter(payment=self.payment, log_type="webhook", message__contains="실패").first()
        assert log is not None

    def test_payment_failed_duplicate_request(self, mocker):
        """중복 실패 요청 - 이미 실패 처리된 결제"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # Payment를 이미 실패 상태로 설정
        self.payment.status = "aborted"
        self.payment.fail_reason = "이미 실패"
        self.payment.save()

        webhook_data = {
            "eventType": "PAYMENT.FAILED",
            "data": {
                "orderId": self.order.order_number,
                "failReason": "중복 요청",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_200_OK

        # fail_reason이 변경되지 않음 (중복 처리 스킵)
        self.payment.refresh_from_db()
        assert self.payment.fail_reason == "이미 실패"

    def test_payment_failed_payment_not_found(self, mocker):
        """Payment가 존재하지 않는 경우"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        webhook_data = {
            "eventType": "PAYMENT.FAILED",
            "data": {
                "orderId": "nonexistent_order_999",
                "failReason": "존재하지 않는 주문",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        # 에러 없이 처리됨 (로그만 남김)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestWebhookSignatureVerification:
    """웹훅 시그니처 검증 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self, api_client, order):
        """각 테스트마다 자동 실행되는 설정"""
        self.client = api_client
        self.order = order
        self.webhook_url = reverse("toss-webhook")

    def test_webhook_signature_missing(self):
        """시그니처 헤더가 없는 경우"""
        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "orderId": self.order.order_number,
            },
        }

        # 시그니처 헤더 없이 요청
        response = self.client.post(self.webhook_url, webhook_data, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Signature missing" in response.json()["error"]

    def test_webhook_signature_invalid(self, mocker):
        """잘못된 시그니처인 경우"""
        # Mock 검증 실패
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=False,
        )

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "orderId": self.order.order_number,
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="invalid_signature",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid signature" in response.json()["error"]

    def test_webhook_signature_empty_string(self):
        """빈 문자열 시그니처"""
        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "orderId": self.order.order_number,
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_webhook_signature_verification_exception(self, mocker):
        """시그니처 검증 중 예외 발생"""
        # Mock 검증에서 예외 발생
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            side_effect=Exception("검증 중 에러"),
        )

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "orderId": self.order.order_number,
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "verification failed" in response.json()["error"]


@pytest.mark.django_db
class TestWebhookDataValidation:
    """웹훅 데이터 검증 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self, api_client):
        """각 테스트마다 자동 실행되는 설정"""
        self.client = api_client
        self.webhook_url = reverse("toss-webhook")

    def test_webhook_invalid_json(self, mocker):
        """잘못된 JSON 데이터"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # 필수 필드 누락
        webhook_data = {
            "eventType": "PAYMENT.DONE",
            # data 필드 누락
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_webhook_missing_event_type(self, mocker):
        """eventType 필드 누락"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        webhook_data = {
            # eventType 누락
            "data": {
                "orderId": "test_order",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_webhook_unsupported_event(self, mocker):
        """지원하지 않는 이벤트 타입"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        webhook_data = {
            "eventType": "PAYMENT.UNKNOWN_EVENT",
            "data": {
                "orderId": "test_order",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        # 지원하지 않는 이벤트는 200 응답 (무시)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Event ignored"

    def test_webhook_partial_canceled_event(self, mocker):
        """부분 취소 이벤트 (향후 지원 예정)"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        webhook_data = {
            "eventType": "PAYMENT.PARTIAL_CANCELED",
            "data": {
                "orderId": "test_order",
                "cancelAmount": 5000,
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        # 현재는 무시 (향후 지원)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestWebhookHttpMethods:
    """웹훅 HTTP 메서드 제한 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self, api_client):
        """각 테스트마다 자동 실행되는 설정"""
        self.client = api_client
        self.webhook_url = reverse("toss-webhook")

    def test_webhook_get_method_not_allowed(self):
        """GET 메서드는 허용되지 않음"""
        response = self.client.get(self.webhook_url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED  # Method Not Allowed

    def test_webhook_put_method_not_allowed(self):
        """PUT 메서드는 허용되지 않음"""
        response = self.client.put(self.webhook_url, {}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_webhook_delete_method_not_allowed(self):
        """DELETE 메서드는 허용되지 않음"""
        response = self.client.delete(self.webhook_url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
class TestWebhookExceptionHandling:
    """웹훅 예외 처리 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self, api_client, order, payment):
        """각 테스트마다 자동 실행되는 설정"""
        self.client = api_client
        self.order = order
        self.payment = payment
        self.webhook_url = reverse("toss-webhook")

    def test_webhook_processing_exception(self, mocker):
        """웹훅 처리 중 예외 발생"""
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.verify_webhook",
            return_value=True,
        )

        # Payment.mark_as_paid에서 예외 발생하도록 Mock
        mocker.patch(
            "shopping.models.payment.Payment.mark_as_paid",
            side_effect=Exception("처리 중 에러"),
        )

        webhook_data = {
            "eventType": "PAYMENT.DONE",
            "data": {
                "paymentKey": "test_key",
                "orderId": self.order.order_number,
                "status": "DONE",
                "totalAmount": int(self.payment.amount),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
            },
        }

        response = self.client.post(
            self.webhook_url,
            webhook_data,
            format="json",
            HTTP_X_TOSS_WEBHOOK_SIGNATURE="test_signature",
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Processing failed" in response.json()["error"]
