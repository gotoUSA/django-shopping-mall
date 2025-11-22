from django.urls import reverse

import pytest
from rest_framework import status

from shopping.models.order import Order, OrderItem
from shopping.models.product import Product


@pytest.mark.django_db
class TestOrderCancelHappyPath:
    """주문 취소 - 정상 케이스"""

    def test_cancel_pending_order(self, authenticated_client, pending_order, product):
        """pending 상태 주문 취소 성공"""
        # Arrange
        initial_stock = product.stock
        url = reverse("order-cancel", kwargs={"pk": pending_order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "주문이 취소되었습니다."

        pending_order.refresh_from_db()
        assert pending_order.status == "canceled"

        product.refresh_from_db()
        assert product.stock == initial_stock + 1

    def test_cancel_paid_order(self, authenticated_client, paid_order, product):
        """paid 상태 주문 취소 성공"""
        # Arrange
        initial_stock = product.stock
        url = reverse("order-cancel", kwargs={"pk": paid_order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "주문이 취소되었습니다."

        paid_order.refresh_from_db()
        assert paid_order.status == "canceled"

        product.refresh_from_db()
        assert product.stock == initial_stock + 1

    def test_cancel_order_single_product_stock_restored(self, authenticated_client, user, product, order_factory):
        """단일 상품 주문 취소 시 재고 복구"""
        # Arrange
        initial_stock = product.stock
        order_quantity = 3

        order = order_factory(user, status="pending", total_amount=product.price * order_quantity)
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            quantity=order_quantity,
            price=product.price,
        )

        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK

        product.refresh_from_db()
        assert product.stock == initial_stock + order_quantity

    def test_cancel_order_multiple_products_stock_restored(self, authenticated_client, user, multiple_products, order_factory):
        """여러 상품 주문 취소 시 모든 재고 복구"""
        # Arrange
        initial_stocks = {p.id: p.stock for p in multiple_products}

        order = order_factory(user, status="pending", total_amount=sum(p.price for p in multiple_products))

        for product in multiple_products:
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                quantity=2,
                price=product.price,
            )

        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK

        for product in multiple_products:
            product.refresh_from_db()
            assert product.stock == initial_stocks[product.id] + 2

    def test_cancel_order_status_changed_to_canceled(self, authenticated_client, pending_order):
        """주문 취소 후 상태가 canceled로 변경"""
        # Arrange
        assert pending_order.status == "pending"
        url = reverse("order-cancel", kwargs={"pk": pending_order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK

        pending_order.refresh_from_db()
        assert pending_order.status == "canceled"
        assert pending_order.can_cancel is False


@pytest.mark.django_db
class TestOrderCancelBoundary:
    """주문 취소 - 경계값 테스트"""

    def test_cancel_other_user_order(self, authenticated_client, seller_user, product, order_factory):
        """다른 사용자의 주문 취소 시도"""
        # Arrange
        other_order = order_factory(seller_user, status="pending", total_amount=product.price, shipping_name="판매자", shipping_phone="010-9999-8888")
        OrderItem.objects.create(
            order=other_order,
            product=product,
            product_name=product.name,
            quantity=1,
            price=product.price,
        )

        url = reverse("order-cancel", kwargs={"pk": other_order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_cancel_other_user_order(self, api_client, user, seller_user, product, admin_user, order_factory):
        """관리자가 다른 사용자 주문 취소"""
        # Arrange
        other_order = order_factory(user, status="pending", total_amount=product.price, shipping_name="일반사용자", shipping_phone="010-1111-2222")
        OrderItem.objects.create(
            order=other_order,
            product=product,
            product_name=product.name,
            quantity=1,
            price=product.price,
        )

        api_client.force_authenticate(user=admin_user)
        url = reverse("order-cancel", kwargs={"pk": other_order.id})

        # Act
        response = api_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK

        other_order.refresh_from_db()
        assert other_order.status == "canceled"

    def test_cancel_already_canceled_order(self, authenticated_client, order):
        """이미 취소된 주문 재취소 시도"""
        # Arrange
        order.status = "canceled"
        order.save()

        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "취소할 수 없는 주문" in response.data["error"]

    def test_cancel_order_immediately_after_cancel(self, authenticated_client, pending_order, product):
        """취소 직후 다시 취소 시도"""
        # Arrange
        initial_stock = product.stock
        url = reverse("order-cancel", kwargs={"pk": pending_order.id})

        # 첫 번째 취소
        response1 = authenticated_client.post(url)
        assert response1.status_code == status.HTTP_200_OK

        # Act - 두 번째 취소 시도
        response2 = authenticated_client.post(url)

        # Assert
        assert response2.status_code == status.HTTP_400_BAD_REQUEST
        assert "취소할 수 없는 주문" in response2.data["error"]

        product.refresh_from_db()
        assert product.stock == initial_stock + 1

    def test_cancel_order_with_zero_stock_product(self, authenticated_client, user, out_of_stock_product, order_factory):
        """재고 0인 상품 주문 취소 시 재고 복구"""
        # Arrange
        assert out_of_stock_product.stock == 0

        order = order_factory(user, status="pending", total_amount=out_of_stock_product.price)
        OrderItem.objects.create(
            order=order,
            product=out_of_stock_product,
            product_name=out_of_stock_product.name,
            quantity=5,
            price=out_of_stock_product.price,
        )

        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK

        out_of_stock_product.refresh_from_db()
        assert out_of_stock_product.stock == 5


@pytest.mark.django_db
class TestOrderCancelException:
    """주문 취소 - 예외 케이스"""

    def test_cancel_shipped_order(self, authenticated_client, order):
        """shipped 상태 주문 취소 시도"""
        # Arrange
        order.status = "shipped"
        order.save()

        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "취소할 수 없는 주문" in response.data["error"]

    def test_cancel_preparing_order(self, authenticated_client, order):
        """preparing 상태 주문 취소 시도"""
        # Arrange
        order.status = "preparing"
        order.save()

        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "취소할 수 없는 주문" in response.data["error"]

    def test_cancel_delivered_order(self, authenticated_client, order):
        """delivered 상태 주문 취소 시도"""
        # Arrange
        order.status = "delivered"
        order.save()

        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "취소할 수 없는 주문" in response.data["error"]

    def test_cancel_refunded_order(self, authenticated_client, order):
        """refunded 상태 주문 취소 시도"""
        # Arrange
        order.status = "refunded"
        order.save()

        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "취소할 수 없는 주문" in response.data["error"]

    def test_cancel_nonexistent_order(self, authenticated_client):
        """존재하지 않는 주문 취소 시도"""
        # Arrange
        nonexistent_id = 99999
        url = reverse("order-cancel", kwargs={"pk": nonexistent_id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cancel_order_unauthenticated(self, api_client, order):
        """인증되지 않은 사용자의 주문 취소 시도"""
        # Arrange
        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = api_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cancel_order_with_deleted_product(self, authenticated_client, user, product, order_factory):
        """상품이 삭제된 주문 취소 (재고 복구 스킵)"""
        # Arrange
        order = order_factory(user, status="pending", total_amount=product.price)
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            quantity=2,
            price=product.price,
        )

        product_id = product.id
        product.stock

        # 상품 삭제 (OrderItem의 product는 NULL로 설정됨)
        product.delete()
        order_item.refresh_from_db()
        assert order_item.product is None

        url = reverse("order-cancel", kwargs={"pk": order.id})

        # Act
        response = authenticated_client.post(url)

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "주문이 취소되었습니다."

        order.refresh_from_db()
        assert order.status == "canceled"

        # 삭제된 상품은 재고 복구 불가 확인
        assert not Product.objects.filter(id=product_id).exists()
