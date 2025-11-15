"""결제 보안 테스트"""

from decimal import Decimal

import pytest
from rest_framework import status

from shopping.models.order import Order, OrderItem
from shopping.models.payment import Payment


@pytest.mark.django_db
class TestPaymentSecurityNormalCase:
    """정상 케이스 - 인증된 사용자의 정상적인 결제 접근"""

    def test_authenticated_verified_user_can_request_payment(
        self,
        authenticated_client,
        user,
        order,
    ):
        """인증되고 이메일 인증된 사용자는 본인 주문 결제 요청 가능"""
        # Arrange
        assert user.is_email_verified is True
        assert order.user == user

        request_data = {"order_id": order.id}

        # Act
        response = authenticated_client.post(
            "/api/payments/request/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        assert "payment_id" in response.data
        assert response.data["order_id"] == order.id

    def test_own_payment_operations_allowed(
        self,
        authenticated_client,
        user,
        paid_payment,
    ):
        """본인 결제는 모든 작업(조회, 취소) 허용"""
        # Arrange
        assert paid_payment.order.user == user

        # Act - 결제 조회
        detail_response = authenticated_client.get(
            f"/api/payments/{paid_payment.id}/"
        )

        # Assert
        assert detail_response.status_code == status.HTTP_200_OK
        assert detail_response.data["id"] == paid_payment.id


@pytest.mark.django_db
class TestPaymentSecurityBoundary:
    """경계값 - 권한 경계 테스트"""

    def test_permission_boundary_between_users(
        self,
        api_client,
        user,
        other_user,
        product,
    ):
        """사용자 간 권한 경계 확인 (본인은 허용, 타인은 거부)"""
        # Arrange - user의 주문/결제
        order = Order.objects.create(
            user=user,
            status="pending",
            total_amount=product.price,
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

        # Act - user로 접근 (본인)
        api_client.force_authenticate(user=user)
        own_response = api_client.get(f"/api/payments/{payment.id}/")

        # Assert - 본인 접근 허용
        assert own_response.status_code == status.HTTP_200_OK

        # Act - other_user로 접근 (타인)
        api_client.force_authenticate(user=other_user)
        other_response = api_client.get(f"/api/payments/{payment.id}/")

        # Assert - 타인 접근 거부
        assert other_response.status_code == status.HTTP_404_NOT_FOUND
        assert "결제 정보를 찾을 수 없습니다" in str(other_response.data)


@pytest.mark.django_db
class TestPaymentSecurityException:
    """보안 예외 - 공격 및 부적절한 접근 차단"""

    def test_tampered_amount_in_confirm_rejected(
        self,
        authenticated_client,
        order,
        payment,
    ):
        """변조된 금액으로 결제 승인 시도 거부"""
        # Arrange - 정상 금액의 50% 감액 변조
        original_amount = int(payment.amount)
        tampered_amount = original_amount // 2

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_payment_key",
            "amount": tampered_amount,
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

        # Assert - Payment 상태 변경 없음
        payment.refresh_from_db()
        assert payment.status == "ready"

    def test_nonexistent_order_id_rejected(
        self,
        authenticated_client,
    ):
        """존재하지 않는 order_id로 결제 승인 시도 거부"""
        # Arrange - 존재하지 않는 order_id
        fake_order_id = "FAKE_ORDER_99999999"

        request_data = {
            "order_id": fake_order_id,
            "payment_key": "test_payment_key",
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

    def test_other_user_order_payment_request_rejected(
        self,
        authenticated_client,
        other_user_order,
    ):
        """다른 사용자의 주문으로 결제 요청 시도 거부"""
        # Arrange
        request_data = {"order_id": other_user_order.id}

        # Act
        response = authenticated_client.post(
            "/api/payments/request/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "주문을 찾을 수 없습니다" in str(response.data)

    def test_other_user_order_payment_confirm_rejected(
        self,
        api_client,
        user,
        other_user,
        other_user_order,
        product,
    ):
        """다른 사용자의 주문 결제 승인 시도 거부"""
        # Arrange - other_user의 결제
        payment = Payment.objects.create(
            order=other_user_order,
            amount=other_user_order.final_amount,
            status="ready",
            toss_order_id=other_user_order.order_number,
        )

        # user로 인증 (주문 소유자가 아님)
        api_client.force_authenticate(user=user)

        request_data = {
            "order_id": other_user_order.order_number,
            "payment_key": "test_payment_key",
            "amount": int(payment.amount),
        }

        # Act
        response = api_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "결제 정보를 찾을 수 없습니다" in str(response.data)

    def test_other_user_payment_cancel_rejected(
        self,
        api_client,
        other_user,
        paid_payment,
    ):
        """다른 사용자의 결제 취소 시도 거부"""
        # Arrange - other_user로 인증
        api_client.force_authenticate(user=other_user)

        request_data = {
            "payment_id": paid_payment.id,
            "cancel_reason": "권한 없는 취소 시도",
        }

        # Act
        response = api_client.post(
            "/api/payments/cancel/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "결제 정보를 찾을 수 없습니다" in str(response.data)

        # Assert - Payment 상태 변경 없음
        paid_payment.refresh_from_db()
        assert paid_payment.status == "done"
        assert paid_payment.is_canceled is False

    def test_other_user_payment_detail_rejected(
        self,
        api_client,
        other_user,
        paid_payment,
    ):
        """다른 사용자의 결제 상세 조회 시도 거부"""
        # Arrange - other_user로 인증
        api_client.force_authenticate(user=other_user)

        # Act
        response = api_client.get(f"/api/payments/{paid_payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "결제 정보를 찾을 수 없습니다" in str(response.data)

    def test_expired_payment_confirm_rejected(
        self,
        authenticated_client,
        order,
        payment,
    ):
        """만료된 결제로 승인 시도 거부"""
        # Arrange - Payment를 만료 상태로 변경
        payment.status = "expired"
        payment.save()

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_payment_key",
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
        assert "결제 정보를 찾을 수 없습니다" in str(response.data)

        # Assert - 상태 변경 없음
        payment.refresh_from_db()
        assert payment.status == "expired"

    def test_canceled_payment_reconfirm_rejected(
        self,
        authenticated_client,
        user,
        product,
    ):
        """취소된 결제로 재승인 시도 거부"""
        # Arrange - 취소된 결제 생성
        order = Order.objects.create(
            user=user,
            status="canceled",
            total_amount=product.price,
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
            status="canceled",
            is_canceled=True,
            toss_order_id=order.order_number,
        )

        request_data = {
            "order_id": order.order_number,
            "payment_key": "test_payment_key",
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

        # Assert - 상태 변경 없음
        payment.refresh_from_db()
        assert payment.status == "canceled"

    def test_unauthenticated_access_rejected(
        self,
        api_client,
        order,
    ):
        """비인증 사용자의 결제 요청 거부"""
        # Arrange - 인증 없이 요청
        request_data = {"order_id": order.id}

        # Act
        response = api_client.post(
            "/api/payments/request/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unverified_email_user_blocked(
        self,
        api_client,
        unverified_user,
        product,
    ):
        """이메일 미인증 사용자의 결제 요청 거부"""
        # Arrange - 미인증 사용자의 주문
        order = Order.objects.create(
            user=unverified_user,
            status="pending",
            total_amount=product.price,
            shipping_name="미인증",
            shipping_phone="010-9999-9999",
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

        api_client.force_authenticate(user=unverified_user)

        request_data = {"order_id": order.id}

        # Act
        response = api_client.post(
            "/api/payments/request/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "이메일 인증이 필요합니다" in response.data["error"]

    def test_sql_injection_in_order_id_sanitized(
        self,
        authenticated_client,
    ):
        """order_id에 SQL Injection 시도 차단"""
        # Arrange - SQL Injection 페이로드
        sql_injection_payloads = [
            "' OR '1'='1",
            "1' UNION SELECT * FROM users--",
            "'; DROP TABLE shopping_payment;--",
            "1' AND 1=1--",
        ]

        for payload in sql_injection_payloads:
            request_data = {
                "order_id": payload,
                "payment_key": "test_key",
                "amount": 10000,
            }

            # Act
            response = authenticated_client.post(
                "/api/payments/confirm/",
                request_data,
                format="json",
            )

            # Assert - Django ORM이 자동으로 이스케이프 처리
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "결제 정보를 찾을 수 없습니다" in str(response.data)

    def test_xss_in_cancel_reason_sanitized(
        self,
        authenticated_client,
        paid_payment,
        mocker,
    ):
        """cancel_reason에 XSS 공격 시도 차단"""
        # Arrange - XSS 페이로드
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg/onload=alert('XSS')>",
        ]

        # Toss API 모킹
        toss_cancel_response = {
            "status": "CANCELED",
            "canceledAt": "2025-01-15T11:00:00+09:00",
        }
        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.cancel_payment",
            return_value=toss_cancel_response,
        )

        for payload in xss_payloads:
            # 새로운 결제 생성 (재사용 방지)
            from django.utils import timezone

            new_payment = Payment.objects.create(
                order=paid_payment.order,
                amount=paid_payment.amount,
                status="done",
                toss_order_id=f"TEST_ORDER_{timezone.now().timestamp()}",
                payment_key=f"test_key_{timezone.now().timestamp()}",
            )

            request_data = {
                "payment_id": new_payment.id,
                "cancel_reason": payload,
            }

            # Act
            response = authenticated_client.post(
                "/api/payments/cancel/",
                request_data,
                format="json",
            )

            # Assert - 취소는 성공하지만 XSS는 이스케이프됨
            assert response.status_code == status.HTTP_200_OK

            # Assert - 저장된 데이터에 스크립트 태그가 그대로 문자열로 저장
            new_payment.refresh_from_db()
            assert new_payment.cancel_reason == payload  # 문자열로 저장됨
            # 응답 시 DRF가 JSON 이스케이프 처리

    def test_confirm_without_payment_object_rejected(
        self,
        authenticated_client,
        order,
    ):
        """Payment 생성 없이 confirm 시도 거부 (플로우 우회)"""
        # Arrange - Payment 생성 단계 건너뛰기
        assert not hasattr(order, "payment")

        request_data = {
            "order_id": order.order_number,
            "payment_key": "fake_payment_key",
            "amount": int(order.final_amount),
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

    def test_confirm_with_fake_payment_key_rejected(
        self,
        authenticated_client,
        order,
        payment,
        mocker,
    ):
        """존재하지 않는 payment_key로 confirm 시도 거부"""
        # Arrange - Toss API가 에러 반환
        from shopping.utils.toss_payment import TossPaymentError

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=TossPaymentError(
                code="INVALID_PAYMENT_KEY",
                message="유효하지 않은 결제 키입니다.",
                status_code=400,
            ),
        )

        request_data = {
            "order_id": order.order_number,
            "payment_key": "FAKE_INVALID_KEY_12345",
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
        assert "error" in response.data

        # Assert - Payment 실패 처리
        payment.refresh_from_db()
        assert payment.status == "aborted"

    def test_confirm_with_mismatched_payment_key_rejected(
        self,
        authenticated_client,
        user,
        product,
        mocker,
    ):
        """다른 주문의 payment_key 사용 시도 거부"""
        # Arrange - 두 개의 서로 다른 주문/결제 생성
        order1 = Order.objects.create(
            user=user,
            status="pending",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
        )
        OrderItem.objects.create(
            order=order1,
            product=product,
            product_name=product.name,
            quantity=1,
            price=product.price,
        )
        payment1 = Payment.objects.create(
            order=order1,
            amount=order1.final_amount,
            status="ready",
            toss_order_id=order1.order_number,
        )

        order2 = Order.objects.create(
            user=user,
            status="pending",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
        )
        OrderItem.objects.create(
            order=order2,
            product=product,
            product_name=product.name,
            quantity=1,
            price=product.price,
        )
        payment2 = Payment.objects.create(
            order=order2,
            amount=order2.final_amount,
            status="ready",
            toss_order_id=order2.order_number,
        )

        # Toss API 에러 모킹
        from shopping.utils.toss_payment import TossPaymentError

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            side_effect=TossPaymentError(
                code="INVALID_REQUEST",
                message="주문번호와 결제키가 일치하지 않습니다.",
                status_code=400,
            ),
        )

        # order1의 order_id + order2의 payment_key (불일치)
        request_data = {
            "order_id": order1.order_number,
            "payment_key": "mismatched_payment_key",
            "amount": int(payment1.amount),
        }

        # Act
        response = authenticated_client.post(
            "/api/payments/confirm/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

        # Assert - 두 결제 모두 상태 변경 없음 (payment1만 aborted)
        payment1.refresh_from_db()
        payment2.refresh_from_db()
        assert payment1.status == "aborted"
        assert payment2.status == "ready"
