"""결제 상세 조회 테스트"""

from decimal import Decimal

from django.utils import timezone

import pytest
from rest_framework import status

from shopping.models.order import Order, OrderItem
from shopping.models.payment import Payment


@pytest.mark.django_db
class TestPaymentDetailNormalCase:
    """정상 케이스"""

    def test_get_payment_detail_success(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """정상 결제 상세 조회"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000001",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key",
            method="카드",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == payment.id

    def test_response_data_structure(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """응답 데이터 구조 검증"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000002",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_2",
            method="카드",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data

        # Assert - 필수 필드 확인
        required_fields = [
            "id",
            "order",
            "order_number",
            "payment_key",
            "amount",
            "used_points",
            "earned_points",
            "method",
            "status",
            "status_display",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"필수 필드 누락: {field}"

    def test_payment_info_included(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """결제 정보 확인 (method, amount, status)"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=Decimal("50000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000003",
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
            amount=Decimal("50000"),
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_3",
            method="카드",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["method"] == "카드"
        assert data["amount"] == "50000"
        assert data["status"] == "done"
        assert data["status_display"] == "결제 완료"

    def test_order_info_included(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """주문 정보 포함 확인"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000004",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_4",
            method="카드",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["order"] == order.id
        assert data["order_number"] == "20250115000004"

    def test_card_number_masking(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """카드 정보 마스킹 확인"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000005",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_5",
            method="카드",
            card_company="신한카드",
            card_number="1234****5678",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["card_company"] == "신한카드"
        assert data["card_number"] == "1234****5678"
        assert "****" in data["card_number"]

    def test_approved_at_included(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """승인 시간 포함"""
        # Arrange
        approved_time = timezone.now()
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000006",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_6",
            method="카드",
            approved_at=approved_time,
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["approved_at"] is not None
        assert "approved_at" in data

    def test_point_info_included(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """포인트 정보 확인 (used_points, earned_points)"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=Decimal("50000"),
            used_points=5000,
            earned_points=500,
            final_amount=Decimal("45000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000007",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_7",
            method="카드",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["used_points"] == 5000
        assert data["earned_points"] == 500

    def test_done_status_payment(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """완료된 결제 조회"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000008",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_8",
            method="카드",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "done"
        assert response.data["status_display"] == "결제 완료"

    def test_canceled_payment_detail(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """취소된 결제 조회"""
        # Arrange
        canceled_time = timezone.now()
        order = Order.objects.create(
            user=user,
            status="canceled",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000009",
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
            status="canceled",
            is_canceled=True,
            toss_order_id=order.order_number,
            payment_key="test_payment_key_9",
            method="카드",
            canceled_amount=order.total_amount,
            cancel_reason="사용자 요청",
            canceled_at=canceled_time,
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["status"] == "canceled"
        assert data["is_canceled"] is True
        assert data["canceled_amount"] == str(order.total_amount)
        assert data["cancel_reason"] == "사용자 요청"
        assert data["canceled_at"] is not None

    def test_ready_status_payment(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """준비 상태 결제 조회"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="pending",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000010",
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
            status="ready",
            toss_order_id=order.order_number,
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ready"
        assert response.data["status_display"] == "결제 준비"

    def test_aborted_status_payment(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """실패 결제 조회"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="pending",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000011",
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
            status="aborted",
            toss_order_id=order.order_number,
            fail_reason="[USER_CANCEL] 사용자가 결제를 취소했습니다",
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "aborted"
        assert response.data["status_display"] == "결제 실패"


@pytest.mark.django_db
class TestPaymentDetailBoundary:
    """경계값 테스트"""

    def test_payment_without_card_info(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """카드 정보 없는 결제 (계좌이체 등)"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000012",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_12",
            method="계좌이체",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["method"] == "계좌이체"
        assert data["card_company"] == ""
        assert data["card_number"] == ""
        assert data["installment_plan_months"] == 0

    def test_payment_with_installment(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """할부 결제"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=Decimal("100000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000013",
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
            amount=Decimal("100000"),
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_13",
            method="카드",
            card_company="KB국민카드",
            card_number="9876****1234",
            installment_plan_months=3,
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["installment_plan_months"] == 3

    def test_payment_with_zero_points(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """포인트 미사용 결제"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            used_points=0,
            earned_points=100,
            final_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000014",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_14",
            method="카드",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["used_points"] == 0
        assert data["earned_points"] == 100

    def test_payment_with_full_points(
        self,
        authenticated_client,
        user,
        product,
    ) -> None:
        """포인트 전액 사용 결제"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=Decimal("10000"),
            used_points=10000,
            earned_points=0,
            final_amount=Decimal("0"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000015",
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
            amount=Decimal("0"),
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_15",
            method="포인트",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["used_points"] == 10000
        assert data["earned_points"] == 0
        assert data["amount"] == "0"


@pytest.mark.django_db
class TestPaymentDetailException:
    """예외 케이스"""

    def test_nonexistent_payment(
        self,
        authenticated_client,
    ) -> None:
        """존재하지 않는 결제"""
        # Arrange
        nonexistent_id = 999999

        # Act
        response = authenticated_client.get(f"/api/payments/{nonexistent_id}/")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "결제 정보를 찾을 수 없습니다" in str(response.data)

    def test_other_user_payment(
        self,
        authenticated_client,
        other_user,
        product,
    ) -> None:
        """다른 사용자의 결제 조회 불가"""
        # Arrange
        order = Order.objects.create(
            user=other_user,
            status="paid",
            total_amount=product.price,
            shipping_name="김철수",
            shipping_phone="010-9999-9999",
            shipping_postal_code="54321",
            shipping_address="부산시 해운대구",
            shipping_address_detail="202동",
            order_number="20250115000016",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_16",
            method="카드",
            approved_at=timezone.now(),
        )

        # Act
        response = authenticated_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "결제 정보를 찾을 수 없습니다" in str(response.data)

    def test_unauthenticated_user(
        self,
        api_client,
        user,
        product,
    ) -> None:
        """인증되지 않은 사용자"""
        # Arrange
        order = Order.objects.create(
            user=user,
            status="paid",
            total_amount=product.price,
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울시 강남구",
            shipping_address_detail="101동",
            order_number="20250115000017",
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
            status="done",
            toss_order_id=order.order_number,
            payment_key="test_payment_key_17",
            method="카드",
            approved_at=timezone.now(),
        )

        # Act
        response = api_client.get(f"/api/payments/{payment.id}/")

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_payment_id_string(
        self,
        authenticated_client,
    ) -> None:
        """문자열 payment_id"""
        # Arrange
        invalid_id = "invalid_string"

        # Act
        response = authenticated_client.get(f"/api/payments/{invalid_id}/")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_invalid_payment_id_negative(
        self,
        authenticated_client,
    ) -> None:
        """음수 payment_id"""
        # Arrange
        negative_id = -1

        # Act
        response = authenticated_client.get(f"/api/payments/{negative_id}/")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
