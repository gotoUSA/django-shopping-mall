import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status

from shopping.models.order import Order


@pytest.mark.django_db
class TestOrderStatusHappyPath:
    """주문 상태 조회 및 필터링"""

    def test_filter_by_pending_status(self, authenticated_client, user):
        """pending 상태 필터링"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        Order.objects.create(
            user=user,
            status="paid",
            total_amount=Decimal("20000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=pending"

        # Act
        response = authenticated_client.get(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["status"] == "pending"

    def test_filter_by_paid_status(self, authenticated_client, user):
        """paid 상태 필터링"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        Order.objects.create(
            user=user,
            status="paid",
            total_amount=Decimal("20000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=paid"

        # Act
        response = authenticated_client.get(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["status"] == "paid"

    def test_filter_all_status_values(self, authenticated_client, user):
        """모든 주문 상태 값 필터링"""
        # Arrange
        statuses = ["pending", "paid", "preparing", "shipped", "delivered", "canceled", "refunded"]

        for status_value in statuses:
            Order.objects.create(
                user=user,
                status=status_value,
                total_amount=Decimal("10000"),
                shipping_name="홍길동",
                shipping_phone="010-1234-5678",
                shipping_postal_code="12345",
                shipping_address="서울",
                shipping_address_detail="101호",
            )

        # Act - 각 상태별로 필터링 테스트
        for status_value in statuses:
            url = reverse("order-list") + f"?status={status_value}"
            response = authenticated_client.get(url)

            # Assert
            assert response.status_code == status.HTTP_200_OK
            assert response.data["count"] == 1
            assert response.data["results"][0]["status"] == status_value

    def test_status_display_in_list(self, authenticated_client, user):
        """목록 조회에서 status_display 필드 확인"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list")

        # Act
        response = authenticated_client.get(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["status"] == "pending"
        assert response.data["results"][0]["status_display"] == "결제대기"

    def test_status_display_in_detail(self, authenticated_client, user):
        """상세 조회에서 모든 상태의 status_display 확인"""
        # Arrange
        statuses = [
            ("pending", "결제대기"),
            ("paid", "결제완료"),
            ("preparing", "배송준비중"),
            ("shipped", "배송중"),
            ("delivered", "배송완료"),
            ("canceled", "주문취소"),
            ("refunded", "환불완료"),
        ]

        for status_code, status_display in statuses:
            order = Order.objects.create(
                user=user,
                status=status_code,
                total_amount=Decimal("10000"),
                shipping_name="홍길동",
                shipping_phone="010-1234-5678",
                shipping_postal_code="12345",
                shipping_address="서울",
                shipping_address_detail="101호",
            )
            url = reverse("order-detail", kwargs={"pk": order.id})

            # Act
            response = authenticated_client.get(url)

            # Assert
            assert response.status_code == status.HTTP_200_OK
            assert response.data["status"] == status_code
            assert response.data["status_display"] == status_display

            # 다음 테스트를 위해 삭제
            order.delete()

    def test_can_cancel_for_cancelable_statuses(self, authenticated_client, user):
        """취소 가능한 상태의 can_cancel=True 확인"""
        # Arrange - pending, paid는 취소 가능
        cancelable_statuses = ["pending", "paid"]

        for status_value in cancelable_statuses:
            order = Order.objects.create(
                user=user,
                status=status_value,
                total_amount=Decimal("10000"),
                shipping_name="홍길동",
                shipping_phone="010-1234-5678",
                shipping_postal_code="12345",
                shipping_address="서울",
                shipping_address_detail="101호",
            )
            url = reverse("order-detail", kwargs={"pk": order.id})

            # Act
            response = authenticated_client.get(url)

            # Assert
            assert response.status_code == status.HTTP_200_OK
            assert response.data["can_cancel"] is True, f"{status_value} 상태는 취소 가능해야 함"

            order.delete()

    def test_can_cancel_for_non_cancelable_statuses(self, authenticated_client, user):
        """취소 불가능한 상태의 can_cancel=False 확인"""
        # Arrange
        non_cancelable_statuses = ["preparing", "shipped", "delivered", "canceled", "refunded"]

        for status_value in non_cancelable_statuses:
            order = Order.objects.create(
                user=user,
                status=status_value,
                total_amount=Decimal("10000"),
                shipping_name="홍길동",
                shipping_phone="010-1234-5678",
                shipping_postal_code="12345",
                shipping_address="서울",
                shipping_address_detail="101호",
            )
            url = reverse("order-detail", kwargs={"pk": order.id})

            # Act
            response = authenticated_client.get(url)

            # Assert
            assert response.status_code == status.HTTP_200_OK
            assert response.data["can_cancel"] is False, f"{status_value} 상태는 취소 불가능해야 함"

            order.delete()


@pytest.mark.django_db
class TestOrderStatusBoundary:
    """주문 상태 조회 - 경계값 테스트"""

    def test_empty_status_filter(self, authenticated_client, user):
        """빈 문자열 상태 필터"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status="

        # Act
        response = authenticated_client.get(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        # 빈 문자열은 필터가 무시되어 모든 주문이 반환됨
        assert response.data["count"] == 1

    def test_whitespace_status_filter(self, authenticated_client, user):
        """공백 상태 필터"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status= "

        # Act
        response = authenticated_client.get(url)

        # Assert - 잘못된 choice 값이므로 400 에러
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_case_sensitive_status_pending(self, authenticated_client, user):
        """대소문자 구분 - Pending (대문자 시작)"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=Pending"

        # Act
        response = authenticated_client.get(url)

        # Assert - STATUS_CHOICES에 없는 값이므로 400 에러
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_case_sensitive_status_paid(self, authenticated_client, user):
        """대소문자 구분 - PAID (전체 대문자)"""
        # Arrange
        Order.objects.create(
            user=user,
            status="paid",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=PAID"

        # Act
        response = authenticated_client.get(url)

        # Assert - STATUS_CHOICES에 없는 값이므로 400 에러
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_nonexistent_status_value(self, authenticated_client, user):
        """존재하지 않는 상태값"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=invalid_status"

        # Act
        response = authenticated_client.get(url)

        # Assert - STATUS_CHOICES에 없는 값이므로 400 에러
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_multiple_status_filter(self, authenticated_client, user):
        """복수 상태 필터링 시도"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        Order.objects.create(
            user=user,
            status="paid",
            total_amount=Decimal("20000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=paid,pending"

        # Act
        response = authenticated_client.get(url)

        # Assert - "paid,pending"은 유효한 choice가 아니므로 400 에러
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_filter_with_no_matching_orders(self, authenticated_client, user):
        """해당 상태 주문이 없는 경우"""
        # Arrange - pending 주문만 생성
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=delivered"

        # Act
        response = authenticated_client.get(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0
        assert response.data["results"] == []


@pytest.mark.django_db
class TestOrderStatusException:
    """주문 상태 조회 - 예외 케이스"""

    def test_sql_injection_attempt(self, authenticated_client, user):
        """SQL Injection 시도"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=pending' OR '1'='1"

        # Act
        response = authenticated_client.get(url)

        # Assert - ChoiceField 검증으로 SQL injection 차단됨 (400 에러)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_special_characters_in_status(self, authenticated_client, user):
        """특수문자 포함 상태값"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=pending!@#$%"

        # Act
        response = authenticated_client.get(url)

        # Assert - 유효하지 않은 choice이므로 400 에러
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_very_long_status_value(self, authenticated_client, user):
        """매우 긴 상태값"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        long_status = "a" * 1000
        url = reverse("order-list") + f"?status={long_status}"

        # Act
        response = authenticated_client.get(url)

        # Assert - 유효하지 않은 choice이므로 400 에러
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unicode_characters_in_status(self, authenticated_client, user):
        """유니코드 문자 포함 상태값"""
        # Arrange
        Order.objects.create(
            user=user,
            status="pending",
            total_amount=Decimal("10000"),
            shipping_name="홍길동",
            shipping_phone="010-1234-5678",
            shipping_postal_code="12345",
            shipping_address="서울",
            shipping_address_detail="101호",
        )
        url = reverse("order-list") + "?status=결제대기"

        # Act
        response = authenticated_client.get(url)

        # Assert - 한글은 유효한 status choice가 아니므로 400 에러
        assert response.status_code == status.HTTP_400_BAD_REQUEST
