"""
결제 포인트 처리 테스트 (Factory Boy 리팩토링 버전)

기존 test_payment_points.py의 일부 테스트를 Factory Boy를 활용하여 리팩토링한 예시입니다.

개선사항:
- 하드코딩된 배송 정보 제거 → TestConstants 사용
- Order/Payment 직접 생성 제거 → Factory 사용
- Toss API 응답 하드코딩 제거 → TossResponseBuilder 사용
- 포인트 이력 생성 간소화 → PointHistoryFactory 사용
- 코드 중복 제거 및 가독성 향상
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status

from shopping.models.order import Order
from shopping.models.payment import Payment
from shopping.models.point import PointHistory
from shopping.services.point_service import PointService
from shopping.tests.factories import (
    CompletedPaymentFactory,
    OrderFactory,
    OrderItemFactory,
    PaidOrderFactory,
    PaymentFactory,
    PointHistoryFactory,
    ProductFactory,
    TestConstants,
    TossResponseBuilder,
    UserFactory,
)


@pytest.mark.django_db
class TestPaymentPointsEarnNormalCase:
    """결제 완료 시 포인트 적립 - 정상 (Factory 사용)"""

    def test_point_history_metadata_on_earn(
        self,
        authenticated_client,
        user,
        mocker,
    ):
        """
        포인트 이력 메타데이터 검증 - 적립 (Factory 버전)

        개선사항:
        - ProductFactory 사용으로 상품 생성 간소화
        - OrderFactory 사용으로 배송 정보 하드코딩 제거
        - TossResponseBuilder 사용으로 응답 구조 통일
        """
        # Arrange
        user.membership_level = "gold"
        user.save()

        # Factory를 사용한 테스트 데이터 생성
        product = ProductFactory(price=TestConstants.DEFAULT_PRODUCT_PRICE)
        order = OrderFactory(
            user=user,
            status="pending",
            total_amount=product.price,
            final_amount=product.price,
        )
        OrderItemFactory(order=order, product=product)

        payment = PaymentFactory(order=order, amount=order.final_amount)

        # TossResponseBuilder 사용
        toss_response = TossResponseBuilder.success_response(
            payment_key=payment.payment_key,
            order_id=order.order_number,
            amount=int(payment.amount),
        )

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            return_value=toss_response,
        )

        request_data = {
            "order_id": order.order_number,
            "payment_key": payment.payment_key,
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

        point_history = PointHistory.objects.filter(
            user=user,
            type="earn",
            order=order,
        ).first()

        assert point_history is not None
        assert "earn_rate" in point_history.metadata
        assert "membership_level" in point_history.metadata
        assert point_history.metadata["membership_level"] == "gold"
        assert point_history.metadata["earn_rate"] == "3%"
        assert point_history.expires_at is not None

    def test_point_history_description_accuracy(
        self,
        authenticated_client,
        user,
        mocker,
    ):
        """
        포인트 이력 description 정확성 검증 (Factory 버전)

        개선사항:
        - 전체적으로 Factory 사용으로 코드 라인 수 감소
        - TestConstants로 금액 일관성 확보
        """
        # Arrange
        product = ProductFactory()
        order = OrderFactory(user=user, status="pending")
        OrderItemFactory(order=order, product=product)
        payment = PaymentFactory(order=order)

        toss_response = TossResponseBuilder.success_response(
            payment_key=payment.payment_key,
            order_id=order.order_number,
            amount=int(payment.amount),
        )

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.confirm_payment",
            return_value=toss_response,
        )

        request_data = {
            "order_id": order.order_number,
            "payment_key": payment.payment_key,
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

        point_history = PointHistory.objects.filter(
            user=user,
            type="earn",
            order=order,
        ).first()

        assert point_history is not None
        assert f"주문 #{order.order_number} 구매 적립" in point_history.description


@pytest.mark.django_db
class TestPaymentPointsCancelNormalCase:
    """결제 취소 시 포인트 처리 - 정상 (Factory 사용)"""

    def test_fifo_points_deduction_on_cancel(
        self,
        authenticated_client,
        product,
        mocker,
    ):
        """
        FIFO 방식 포인트 회수 검증 (Factory 버전)

        개선사항:
        - UserFactory 사용으로 사용자 생성 간소화
        - PointHistoryFactory 사용으로 포인트 이력 생성 간소화
        - PaidOrderFactory 사용으로 결제 완료 주문 생성 간소화
        - CompletedPaymentFactory 사용
        - TestConstants로 매직 넘버 제거
        """
        # Arrange - Factory를 사용한 사용자 생성
        user = UserFactory(points=0)

        # 클라이언트 인증
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        from rest_framework.test import APIClient

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")

        # PointHistoryFactory를 사용한 포인트 이력 생성
        now = timezone.now()

        # 가장 먼저 만료될 포인트 (30일 후)
        history1 = PointHistoryFactory(
            user=user,
            points=1000,
            balance=1000,
            description="첫번째 적립",
            expires_at=now + timedelta(days=30),
        )

        # 두번째로 만료될 포인트 (60일 후)
        history2 = PointHistoryFactory(
            user=user,
            points=2000,
            balance=3000,
            description="두번째 적립",
            expires_at=now + timedelta(days=60),
        )

        # 가장 나중에 만료될 포인트 (90일 후)
        history3 = PointHistoryFactory(
            user=user,
            points=3000,
            balance=6000,
            description="세번째 적립",
            expires_at=now + timedelta(days=90),
        )

        user.points = 6000
        user.save()

        # PaidOrderFactory 사용으로 결제 완료 주문 생성 간소화
        order = PaidOrderFactory(
            user=user,
            total_amount=product.price,
            final_amount=product.price,
            earned_points=2500,
        )

        OrderItemFactory(order=order, product=product)

        # CompletedPaymentFactory 사용
        payment = CompletedPaymentFactory(
            order=order,
            amount=order.total_amount,
            payment_key="test_fifo_key",
        )

        # 적립 이력 생성
        PointHistoryFactory(
            user=user,
            points=2500,
            balance=8500,
            type="earn",
            order=order,
            description="주문 적립",
            expires_at=now + timedelta(days=365),
        )

        user.points = 8500
        user.save()

        # TossResponseBuilder 사용
        toss_cancel_response = TossResponseBuilder.cancel_response(
            payment_key=payment.payment_key,
        )

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.cancel_payment",
            return_value=toss_cancel_response,
        )

        request_data = {
            "payment_id": payment.id,
            "cancel_reason": "FIFO 테스트",
        }

        # Act
        response = client.post(
            "/api/payments/cancel/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        # FIFO 순서 검증: 가장 먼저 만료되는 순서대로 회수
        history1.refresh_from_db()
        history2.refresh_from_db()
        history3.refresh_from_db()

        # 첫번째 이력 (1000P) - 전액 회수
        assert history1.metadata.get("used_amount", 0) == 1000

        # 두번째 이력 (2000P) - 1500P 회수 (2500 - 1000)
        assert history2.metadata.get("used_amount", 0) == 1500

        # 세번째 이력 (3000P) - 회수 안됨
        assert history3.metadata.get("used_amount", 0) == 0

    def test_point_history_metadata_on_cancel(
        self,
        authenticated_client,
        mocker,
    ):
        """
        포인트 이력 메타데이터 검증 - 취소 환불/회수 (Factory 버전)

        개선사항:
        - UserFactory, ProductFactory 사용
        - Order 생성 시 배송 정보 하드코딩 제거
        - Factory의 기본값 활용
        """
        # Arrange - Factory를 사용한 데이터 생성
        user = UserFactory(points=10000)

        # 인증 클라이언트 설정
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        from rest_framework.test import APIClient

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")

        product = ProductFactory()

        # OrderFactory 사용 (배송 정보 자동 설정)
        order = PaidOrderFactory(
            user=user,
            total_amount=product.price,
            used_points=3000,
            final_amount=product.price - Decimal("3000"),
            earned_points=100,
        )

        OrderItemFactory(order=order, product=product)

        # 포인트 사용 이력
        PointHistoryFactory(
            user=user,
            points=-3000,
            balance=7000,
            type="use",
            order=order,
            description="포인트 사용",
        )

        # 포인트 적립 이력
        PointHistoryFactory(
            user=user,
            points=100,
            balance=7100,
            type="earn",
            order=order,
            description="주문 적립",
        )

        user.points = 7100
        user.save()

        payment = CompletedPaymentFactory(
            order=order,
            amount=order.final_amount,
            payment_key="test_metadata_key",
        )

        toss_cancel_response = TossResponseBuilder.cancel_response(
            payment_key=payment.payment_key,
        )

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.cancel_payment",
            return_value=toss_cancel_response,
        )

        request_data = {
            "payment_id": payment.id,
            "cancel_reason": "메타데이터 테스트",
        }

        # Act
        response = client.post(
            "/api/payments/cancel/",
            request_data,
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        # 환불 이력 (type="cancel_refund")
        refund_history = PointHistory.objects.filter(
            user=user,
            type="cancel_refund",
            order=order,
        ).first()
        assert refund_history is not None
        assert refund_history.points == 3000

        # 회수 이력 (type="cancel_deduct")
        deduct_history = PointHistory.objects.filter(
            user=user,
            type="cancel_deduct",
            order=order,
        ).first()
        assert deduct_history is not None
        assert deduct_history.points == -100


@pytest.mark.django_db
class TestPaymentPointsBoundary:
    """경계값 테스트 (Factory 사용)"""

    def test_partial_expired_points_deduction(self):
        """
        부분 만료된 포인트 회수 처리 (Factory 버전)

        개선사항:
        - UserFactory 사용으로 사용자 생성 간소화
        - PointHistoryFactory 사용
        """
        # Arrange
        user = UserFactory(points=0)

        now = timezone.now()
        point_service = PointService()

        # 만료된 포인트 (500P) - 30일 전에 만료
        expired_history = PointHistoryFactory(
            user=user,
            points=500,
            balance=500,
            description="만료된 적립",
            expires_at=now - timedelta(days=30),
        )

        # 유효한 포인트 (2000P) - 30일 후 만료
        valid_history = PointHistoryFactory(
            user=user,
            points=2000,
            balance=2500,
            description="유효한 적립",
            expires_at=now + timedelta(days=30),
        )

        user.points = 2500
        user.save()

        # Act - 1500P 회수 시도
        result = point_service.use_points_fifo(
            user=user,
            amount=1500,
            type="cancel_deduct",
            description="부분 만료 테스트",
        )

        # Assert
        assert result["success"] is True

        # 만료된 포인트는 건너뛰고 유효한 포인트에서만 회수
        expired_history.refresh_from_db()
        valid_history.refresh_from_db()

        assert expired_history.metadata.get("used_amount", 0) == 0
        assert valid_history.metadata.get("used_amount", 0) == 1500

        user.refresh_from_db()
        assert user.points == 1000


@pytest.mark.django_db
class TestPaymentPointsException:
    """예외 케이스 (Factory 사용)"""

    def test_insufficient_points_for_deduction(self):
        """
        포인트 부족으로 회수 불가 (Factory 버전)

        개선사항:
        - UserFactory로 코드 간소화
        - PointHistoryFactory 사용
        """
        # Arrange
        user = UserFactory(points=0)

        now = timezone.now()
        point_service = PointService()

        # 유효한 포인트 1000P만 존재
        PointHistoryFactory(
            user=user,
            points=1000,
            balance=1000,
            description="유효한 적립",
            expires_at=now + timedelta(days=30),
        )

        user.points = 1000
        user.save()

        # Act - 2000P 회수 시도 (부족)
        result = point_service.use_points_fifo(
            user=user,
            amount=2000,
            type="cancel_deduct",
            description="부족 테스트",
        )

        # Assert
        assert result["success"] is False
        assert "부족" in result["message"]

        # 포인트 변동 없음
        user.refresh_from_db()
        assert user.points == 1000

    def test_cancel_with_insufficient_earned_points(
        self,
        mocker,
    ):
        """
        적립 포인트 회수 시 포인트 부족 - API 통합 테스트 (Factory 버전)

        개선사항:
        - 전체적으로 Factory 사용
        - TossResponseBuilder 사용
        - 배송 정보 하드코딩 제거
        """
        # Arrange
        user = UserFactory(points=100)

        # 인증 클라이언트
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        from rest_framework.test import APIClient

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")

        product = ProductFactory()

        # 결제 완료 주문 (2000P 적립됨)
        order = PaidOrderFactory(
            user=user,
            total_amount=product.price,
            final_amount=product.price,
            earned_points=2000,
        )

        OrderItemFactory(order=order, product=product)

        # 적립 이력
        PointHistoryFactory(
            user=user,
            points=2000,
            balance=2100,
            type="earn",
            order=order,
            description="주문 적립",
        )

        # 사용자가 적립된 포인트를 거의 다 사용 (100P만 남음)
        # (별도 주문에서 2000P 사용했다고 가정)

        payment = CompletedPaymentFactory(
            order=order,
            amount=order.total_amount,
            payment_key="test_insufficient_earned_key",
        )

        toss_cancel_response = TossResponseBuilder.cancel_response(
            payment_key=payment.payment_key,
        )

        mocker.patch(
            "shopping.utils.toss_payment.TossPaymentClient.cancel_payment",
            return_value=toss_cancel_response,
        )

        request_data = {
            "payment_id": payment.id,
            "cancel_reason": "부족 테스트",
        }

        # Act
        response = client.post(
            "/api/payments/cancel/",
            request_data,
            format="json",
        )

        # Assert - 포인트 부족으로 취소 실패 (400 에러)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "포인트가 부족" in str(response.data)

        # 주문/결제 상태 변경 없음
        order.refresh_from_db()
        payment.refresh_from_db()
        assert order.status == "paid"
        assert payment.status == "done"
