"""결제 동시성 테스트"""

import threading
import uuid
from decimal import Decimal

import pytest
from django.db.models import F
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from shopping.models.order import Order, OrderItem
from shopping.models.payment import Payment
from shopping.models.product import Product
from shopping.models.user import User


def login_and_get_token(username, password="testpass123"):
    """
    로그인하여 JWT 토큰 발급

    멀티스레딩 환경에서 사용
    """
    client = APIClient()
    login_url = reverse("auth-login")
    response = client.post(
        login_url,
        {"username": username, "password": password},
        format="json",
    )

    if response.status_code != status.HTTP_200_OK:
        return None, None, f"Login failed: {response.status_code}"

    token = response.json().get("access")
    return client, token, None


def create_test_user(username, email, phone_number, points=5000, is_verified=True):
    """테스트 사용자 생성 헬퍼"""
    return User.objects.create_user(
        username=username,
        email=email,
        password="testpass123",
        phone_number=phone_number,
        points=points,
        is_email_verified=is_verified,
    )


def create_test_order_with_payment(user, product, amount=None, quantity=1):
    """
    테스트 주문 및 결제 생성 헬퍼

    실제 주문 생성 플로우 시뮬레이션:
    1. 재고 차감 (주문 생성 시)
    2. Order 생성
    3. Payment 생성 (ready 상태)
    """
    if amount is None:
        amount = product.price

    # 1. 재고 차감 (주문 생성 시뮬레이션)
    Product.objects.filter(pk=product.pk).update(stock=F("stock") - quantity)

    order = Order.objects.create(
        user=user,
        status="pending",
        total_amount=amount,
        shipping_name="홍길동",
        shipping_phone="010-1234-5678",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=quantity,
        price=amount,
    )

    payment = Payment.objects.create(
        order=order,
        amount=amount,
        status="ready",
        toss_order_id=order.order_number,
    )

    return order, payment


@pytest.mark.django_db(transaction=True)
class TestPaymentConcurrencyHappyPath:
    """정상 케이스 - 충분한 리소스가 있는 상황"""

    def test_multiple_users_concurrent_payment_success(self, product, mocker):
        """여러 사용자가 동시에 독립적인 결제 성공"""
        # Arrange
        product.stock = 100
        product.save()

        users = []
        payments = []
        for i in range(5):
            user = create_test_user(
                username=f"concurrent_user{i}",
                email=f"concurrent{i}@test.com",
                phone_number=f"010-0000-{i:04d}",
            )
            users.append(user)

            _, payment = create_test_order_with_payment(user, product)
            payments.append(payment)

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": "test_order_id",
                "status": "DONE",
                "totalAmount": int(product.price),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {
                    "company": "신한카드",
                    "number": "1234****",
                    "installmentPlanMonths": 0,
                },
                "receipt": {"url": "https://receipt.example.com"},
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )

        results = []
        lock = threading.Lock()

        def confirm_payment(user_obj, payment_obj):
            """결제 승인 함수"""
            try:
                client, token, error = login_and_get_token(user_obj.username)
                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment_obj.toss_order_id,
                        "payment_key": "test_key",
                        "amount": int(payment_obj.amount),
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [
            threading.Thread(target=confirm_payment, args=(u, p))
            for u, p in zip(users, payments)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count == 5, f"5명 모두 성공해야 함. 성공: {success_count}"

        # 재고 확인 (100 - 5 = 95)
        product.refresh_from_db()
        assert product.stock == 95

    def test_concurrent_payment_with_point_earning(self, product, mocker):
        """동시 결제 시 포인트 적립 정상 처리"""
        # Arrange
        product.stock = 50
        product.price = Decimal("10000")
        product.save()

        users = []
        payments = []
        for i in range(3):
            user = create_test_user(
                username=f"point_user{i}",
                email=f"point{i}@test.com",
                phone_number=f"010-1111-{i:04d}",
                points=0,
            )
            users.append(user)

            _, payment = create_test_order_with_payment(user, product)
            payments.append(payment)

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": "test_order_id",
                "status": "DONE",
                "totalAmount": 10000,
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
                "receipt": {"url": "https://receipt.example.com"},
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )

        results = []
        lock = threading.Lock()

        def confirm_payment_with_points(user_obj, payment_obj):
            """포인트 적립 결제 승인"""
            try:
                client, token, error = login_and_get_token(user_obj.username)
                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment_obj.toss_order_id,
                        "payment_key": "test_key",
                        "amount": 10000,
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [
            threading.Thread(target=confirm_payment_with_points, args=(u, p))
            for u, p in zip(users, payments)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count == 3, f"3명 모두 성공해야 함. 성공: {success_count}"

        # 포인트 적립 확인 (10000 * 1% = 100P)
        for user in users:
            user.refresh_from_db()
            assert user.points == 100, f"{user.username}의 포인트가 100P 적립되어야 함"


@pytest.mark.django_db(transaction=True)
class TestPaymentConcurrencyBoundary:
    """경계값 테스트 - 리소스가 딱 맞는 경계 상황"""

    def test_concurrent_payment_exact_stock_boundary(self, product, mocker):
        """재고 5개에 5명이 동시 결제 - 모두 성공"""
        # Arrange
        product.stock = 5
        product.save()

        users = []
        payments = []
        for i in range(5):
            user = create_test_user(
                username=f"boundary_user{i}",
                email=f"boundary{i}@test.com",
                phone_number=f"010-2222-{i:04d}",
            )
            users.append(user)

            _, payment = create_test_order_with_payment(user, product)
            payments.append(payment)

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": "test_order_id",
                "status": "DONE",
                "totalAmount": int(product.price),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
                "receipt": {"url": "https://receipt.example.com"},
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )

        results = []
        lock = threading.Lock()

        def confirm_payment(user_obj, payment_obj):
            """결제 승인"""
            try:
                client, token, error = login_and_get_token(user_obj.username)
                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment_obj.toss_order_id,
                        "payment_key": "test_key",
                        "amount": int(payment_obj.amount),
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [
            threading.Thread(target=confirm_payment, args=(u, p))
            for u, p in zip(users, payments)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count == 5, f"5명 모두 성공해야 함. 성공: {success_count}"

        # 재고 확인 (5 - 5 = 0)
        product.refresh_from_db()
        assert product.stock == 0

    def test_concurrent_payment_stock_boundary_one_fails(self, product, mocker):
        """재고 2개에 3명이 동시 결제 - 2명만 성공"""
        # Arrange
        product.stock = 2
        product.save()

        users = []
        payments = []
        for i in range(3):
            user = create_test_user(
                username=f"boundary_fail{i}",
                email=f"boundaryfail{i}@test.com",
                phone_number=f"010-3333-{i:04d}",
            )
            users.append(user)

            _, payment = create_test_order_with_payment(user, product)
            payments.append(payment)

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": "test_order_id",
                "status": "DONE",
                "totalAmount": int(product.price),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
                "receipt": {"url": "https://receipt.example.com"},
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )

        results = []
        lock = threading.Lock()

        def confirm_payment(user_obj, payment_obj):
            """결제 승인"""
            try:
                client, token, error = login_and_get_token(user_obj.username)
                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment_obj.toss_order_id,
                        "payment_key": "test_key",
                        "amount": int(payment_obj.amount),
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [
            threading.Thread(target=confirm_payment, args=(u, p))
            for u, p in zip(users, payments)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))
        failed_count = len(results) - success_count

        assert success_count == 2, f"2명만 성공해야 함. 성공: {success_count}"
        assert failed_count == 1, f"1명은 실패해야 함. 실패: {failed_count}"

        # 재고 확인 (2 - 2 = 0)
        product.refresh_from_db()
        assert product.stock == 0


@pytest.mark.django_db(transaction=True)
class TestPaymentConcurrencyException:
    """예외 케이스 - 동시성 경합 및 race condition"""

    def test_duplicate_payment_confirm_rejected(self, user, product, mocker):
        """동일 결제를 여러 번 동시 승인 시도 - 1번만 성공"""
        # Arrange
        product.stock = 10
        product.save()

        _, payment = create_test_order_with_payment(user, product)

        # Toss API Mock - 의도적으로 동일한 payment_key 사용 (중복 확인용)
        mock_toss_response = {
            "paymentKey": f"test_payment_key_duplicate_{payment.id}",
            "orderId": payment.toss_order_id,
            "status": "DONE",
            "totalAmount": int(product.price),
            "method": "카드",
            "approvedAt": "2025-01-15T10:00:00+09:00",
            "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
            "receipt": {"url": "https://receipt.example.com"},
        }
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            return_value=mock_toss_response,
        )

        client, token, error = login_and_get_token(user.username)
        if error:
            pytest.skip(f"로그인 실패: {error}")

        results = []
        lock = threading.Lock()

        def confirm_same_payment():
            """동일 결제 승인 시도"""
            try:
                confirm_client = APIClient()
                confirm_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = confirm_client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment.toss_order_id,
                        "payment_key": "test_key",
                        "amount": int(payment.amount),
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"error": str(e)})

        # Act - 5번 동시 승인 시도
        threads = [threading.Thread(target=confirm_same_payment) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 1번만 성공
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count == 1, f"1번만 성공해야 함. 성공: {success_count}"

        # Payment 상태 확인
        payment.refresh_from_db()
        assert payment.status == "done"

    def test_concurrent_confirm_and_cancel_race_condition(
        self, user, product, mocker
    ):
        """승인과 취소 동시 호출 - 먼저 성공한 것만 처리됨"""
        # Arrange
        product.stock = 10
        product.save()

        # sold_count 미리 증가 (취소 시 감소를 위해)
        Product.objects.filter(pk=product.pk).update(sold_count=F("sold_count") + 1)
        product.refresh_from_db()

        order, payment = create_test_order_with_payment(user, product)

        # Payment를 done 상태로 변경 (취소 가능하도록)
        payment.status = "done"
        payment.payment_key = "test_payment_key"
        payment.save()

        # Order도 paid 상태로 변경
        order.status = "paid"
        order.save()

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": payment.toss_order_id,
                "status": "DONE",
                "totalAmount": int(product.price),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
                "receipt": {"url": "https://receipt.example.com"},
            }

        def mock_cancel_payment(*args, **kwargs):
            return {
                "status": "CANCELED",
                "canceledAt": "2025-01-15T11:00:00+09:00",
                "cancelReason": "동시 호출 테스트",
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.cancel_payment",
            side_effect=mock_cancel_payment,
        )

        client, token, error = login_and_get_token(user.username)
        if error:
            pytest.skip(f"로그인 실패: {error}")

        results = []
        lock = threading.Lock()

        def confirm_payment_action():
            """결제 승인 시도"""
            try:
                confirm_client = APIClient()
                confirm_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = confirm_client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment.toss_order_id,
                        "payment_key": "test_key",
                        "amount": int(payment.amount),
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "action": "confirm",
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"action": "confirm", "error": str(e)})

        def cancel_payment_action():
            """결제 취소 시도"""
            try:
                cancel_client = APIClient()
                cancel_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = cancel_client.post(
                    "/api/payments/cancel/",
                    {
                        "payment_id": payment.id,
                        "cancel_reason": "동시 호출 테스트",
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "action": "cancel",
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"action": "cancel", "error": str(e)})

        # Act - confirm 3번, cancel 3번 동시 호출
        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=confirm_payment_action))
            threads.append(threading.Thread(target=cancel_payment_action))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 최소 1개는 성공
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count >= 1, f"최소 1개는 성공해야 함. 성공: {success_count}"

        # Payment 최종 상태 확인 (done 또는 canceled)
        payment.refresh_from_db()
        assert payment.status in ["done", "canceled"]

    def test_concurrent_confirm_and_fail_api_calls(self, user, product, mocker):
        """confirm과 fail API 동시 호출 - 먼저 처리된 것만 적용"""
        # Arrange
        product.stock = 10
        product.save()

        _, payment = create_test_order_with_payment(user, product)

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": payment.toss_order_id,
                "status": "DONE",
                "totalAmount": int(product.price),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
                "receipt": {"url": "https://receipt.example.com"},
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )

        client, token, error = login_and_get_token(user.username)
        if error:
            pytest.skip(f"로그인 실패: {error}")

        results = []
        lock = threading.Lock()

        def confirm_payment_action():
            """결제 승인 시도"""
            try:
                confirm_client = APIClient()
                confirm_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = confirm_client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment.toss_order_id,
                        "payment_key": "test_key",
                        "amount": int(payment.amount),
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "action": "confirm",
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"action": "confirm", "error": str(e)})

        def fail_payment_action():
            """결제 실패 처리 시도"""
            try:
                fail_client = APIClient()
                response = fail_client.post(
                    "/api/payments/fail/",
                    {
                        "code": "USER_CANCEL",
                        "message": "사용자 취소",
                        "order_id": payment.toss_order_id,
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "action": "fail",
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"action": "fail", "error": str(e)})

        # Act - confirm 2번, fail 2번 동시 호출
        threads = []
        for _ in range(2):
            threads.append(threading.Thread(target=confirm_payment_action))
            threads.append(threading.Thread(target=fail_payment_action))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 모두 성공 (confirm은 상태 검증, fail은 항상 성공)
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count >= 2, f"최소 2개는 성공해야 함. 성공: {success_count}"

        # Payment 최종 상태 확인
        payment.refresh_from_db()
        assert payment.status in ["done", "aborted"]

    def test_concurrent_stock_deduction_with_select_for_update(
        self, product, mocker
    ):
        """select_for_update를 사용한 재고 차감 동시성 제어"""
        # Arrange
        product.stock = 10
        product.save()

        users = []
        payments = []
        for i in range(10):
            user = create_test_user(
                username=f"stock_user{i}",
                email=f"stock{i}@test.com",
                phone_number=f"010-4444-{i:04d}",
            )
            users.append(user)

            _, payment = create_test_order_with_payment(user, product)
            payments.append(payment)

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": "test_order_id",
                "status": "DONE",
                "totalAmount": int(product.price),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
                "receipt": {"url": "https://receipt.example.com"},
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )

        results = []
        lock = threading.Lock()

        def confirm_payment(user_obj, payment_obj):
            """결제 승인 (재고 차감 포함)"""
            try:
                client, token, error = login_and_get_token(user_obj.username)
                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment_obj.toss_order_id,
                        "payment_key": "test_key",
                        "amount": int(payment_obj.amount),
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act - 10명이 동시 결제
        threads = [
            threading.Thread(target=confirm_payment, args=(u, p))
            for u, p in zip(users, payments)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count == 10, f"10명 모두 성공해야 함. 성공: {success_count}"

        # 재고 및 sold_count 확인
        product.refresh_from_db()
        assert product.stock == 0
        assert product.sold_count == 10

    def test_concurrent_point_usage_and_earning(self, product, mocker):
        """포인트 사용과 적립 동시 처리"""
        # Arrange
        product.stock = 50
        product.price = Decimal("10000")
        product.save()

        users = []
        payments = []
        for i in range(3):
            user = create_test_user(
                username=f"point_concurrent{i}",
                email=f"pointc{i}@test.com",
                phone_number=f"010-5555-{i:04d}",
                points=2000,
            )
            users.append(user)

            # 재고 차감 (주문 생성 시뮬레이션)
            Product.objects.filter(pk=product.pk).update(stock=F("stock") - 1)

            # 포인트 차감 (주문 생성 시뮬레이션)
            user.use_points(1000)

            # 포인트 사용 주문 생성
            order = Order.objects.create(
                user=user,
                status="pending",
                total_amount=product.price,
                used_points=1000,
                final_amount=product.price - Decimal("1000"),
                shipping_name="홍길동",
                shipping_phone="010-1234-5678",
                shipping_postal_code="12345",
                shipping_address="서울시 강남구",
                shipping_address_detail="101동",
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
                amount=order.final_amount,
                status="ready",
                toss_order_id=order.order_number,
            )
            payments.append(payment)

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": "test_order_id",
                "status": "DONE",
                "totalAmount": 9000,
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
                "receipt": {"url": "https://receipt.example.com"},
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )

        results = []
        lock = threading.Lock()

        def confirm_payment_with_points(user_obj, payment_obj):
            """포인트 사용 결제 승인"""
            try:
                client, token, error = login_and_get_token(user_obj.username)
                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment_obj.toss_order_id,
                        "payment_key": "test_key",
                        "amount": 9000,
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [
            threading.Thread(target=confirm_payment_with_points, args=(u, p))
            for u, p in zip(users, payments)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count == 3, f"3명 모두 성공해야 함. 성공: {success_count}"

        # 포인트 확인 (2000 - 1000 사용 + 90 적립 = 1090)
        for user in users:
            user.refresh_from_db()
            assert user.points == 1090, f"{user.username}의 포인트가 1090P여야 함"

    def test_same_user_multiple_concurrent_payments(self, user, product, mocker):
        """동일 사용자가 여러 결제를 동시 생성"""
        # Arrange
        product.stock = 50
        product.save()

        payments = []
        for i in range(3):
            _, payment = create_test_order_with_payment(user, product)
            payments.append(payment)

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": "test_order_id",
                "status": "DONE",
                "totalAmount": int(product.price),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
                "receipt": {"url": "https://receipt.example.com"},
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )

        client, token, error = login_and_get_token(user.username)
        if error:
            pytest.skip(f"로그인 실패: {error}")

        results = []
        lock = threading.Lock()

        def confirm_payment(payment_obj):
            """결제 승인"""
            try:
                confirm_client = APIClient()
                confirm_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = confirm_client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment_obj.toss_order_id,
                        "payment_key": "test_key",
                        "amount": int(payment_obj.amount),
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "payment_id": payment_obj.id,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"payment_id": payment_obj.id, "error": str(e)})

        # Act - 3개 결제 동시 승인
        threads = [threading.Thread(target=confirm_payment, args=(p,)) for p in payments]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count == 3, f"3개 모두 성공해야 함. 성공: {success_count}"

        # 재고 확인 (50 - 3 = 47)
        product.refresh_from_db()
        assert product.stock == 47

    def test_payment_during_stock_depletion(self, product, mocker):
        """결제 진행 중 재고 소진 시나리오"""
        # Arrange
        product.stock = 1
        product.save()

        users = []
        payments = []
        for i in range(5):
            user = create_test_user(
                username=f"depletion_user{i}",
                email=f"depletion{i}@test.com",
                phone_number=f"010-6666-{i:04d}",
            )
            users.append(user)

            _, payment = create_test_order_with_payment(user, product)
            payments.append(payment)

        # Toss API Mock - 각 호출마다 고유한 payment_key 생성
        def mock_confirm_payment(*args, **kwargs):
            return {
                "paymentKey": f"test_payment_key_{uuid.uuid4().hex[:12]}",
                "orderId": "test_order_id",
                "status": "DONE",
                "totalAmount": int(product.price),
                "method": "카드",
                "approvedAt": "2025-01-15T10:00:00+09:00",
                "card": {"company": "신한카드", "number": "1234****", "installmentPlanMonths": 0},
                "receipt": {"url": "https://receipt.example.com"},
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=mock_confirm_payment,
        )

        results = []
        lock = threading.Lock()

        def confirm_payment(user_obj, payment_obj):
            """결제 승인"""
            try:
                client, token, error = login_and_get_token(user_obj.username)
                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post(
                    "/api/payments/confirm/",
                    {
                        "order_id": payment_obj.toss_order_id,
                        "payment_key": "test_key",
                        "amount": int(payment_obj.amount),
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act - 5명이 재고 1개를 두고 경합
        threads = [
            threading.Thread(target=confirm_payment, args=(u, p))
            for u, p in zip(users, payments)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 1명만 성공
        success_count = sum(1 for r in results if r.get("success", False))
        failed_count = len(results) - success_count

        assert success_count == 1, f"1명만 성공해야 함. 성공: {success_count}"
        assert failed_count == 4, f"4명은 실패해야 함. 실패: {failed_count}"

        # 재고 확인 (1 - 1 = 0)
        product.refresh_from_db()
        assert product.stock == 0

    def test_duplicate_cancel_requests(self, user, product, mocker):
        """동일 결제를 여러 번 동시 취소 시도 - 1번만 성공"""
        # Arrange
        product.stock = 10
        product.save()

        # sold_count 미리 증가 (취소 시 감소를 위해)
        Product.objects.filter(pk=product.pk).update(sold_count=F("sold_count") + 1)
        product.refresh_from_db()

        order, payment = create_test_order_with_payment(user, product)

        # Payment를 done 상태로 변경
        payment.status = "done"
        payment.payment_key = "test_payment_key"
        payment.save()

        # Order도 paid 상태로 변경
        order.status = "paid"
        order.save()

        # Toss API Mock - 각 호출마다 고유한 응답 생성
        def mock_cancel_payment(*args, **kwargs):
            return {
                "status": "CANCELED",
                "canceledAt": "2025-01-15T11:00:00+09:00",
                "cancelReason": "중복 취소 테스트",
            }

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.cancel_payment",
            side_effect=mock_cancel_payment,
        )

        client, token, error = login_and_get_token(user.username)
        if error:
            pytest.skip(f"로그인 실패: {error}")

        results = []
        lock = threading.Lock()

        def cancel_payment():
            """결제 취소"""
            try:
                cancel_client = APIClient()
                cancel_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = cancel_client.post(
                    "/api/payments/cancel/",
                    {
                        "payment_id": payment.id,
                        "cancel_reason": "중복 취소 테스트",
                    },
                    format="json",
                )

                with lock:
                    results.append(
                        {
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_200_OK,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"error": str(e)})

        # Act - 5번 동시 취소 시도
        threads = [threading.Thread(target=cancel_payment) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 1번만 성공
        success_count = sum(1 for r in results if r.get("success", False))
        assert success_count == 1, f"1번만 성공해야 함. 성공: {success_count}"

        # Payment 상태 확인
        payment.refresh_from_db()
        assert payment.status == "canceled"
        assert payment.is_canceled is True
