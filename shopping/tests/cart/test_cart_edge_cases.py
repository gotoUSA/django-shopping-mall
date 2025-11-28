"""
장바구니 엣지 케이스 테스트

커버리지 미달 라인 커버를 위한 테스트:
- 비회원 세션 처리
- 유효성 검증 에러
- 예외 처리
- CartItemViewSet CRUD
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from shopping.models.cart import Cart, CartItem
from shopping.tests.factories import (
    CartFactory,
    CartItemFactory,
    CategoryFactory,
    ProductFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestCartAnonymousSession:
    """비회원 세션 처리"""

    def test_creates_session_when_none_exists(self):
        """세션 없는 비회원이 장바구니 접근 시 세션 생성"""
        # Arrange
        client = APIClient()

        # Act
        response = client.get(reverse("cart-detail"))

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert client.session.session_key is not None

    def test_retrieves_cart_for_anonymous_user_with_session(self):
        """세션 있는 비회원의 장바구니 조회"""
        # Arrange
        client = APIClient()
        client.get(reverse("cart-detail"))  # 세션 생성
        session_key = client.session.session_key

        # Act
        response = client.get(reverse("cart-detail"))

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert Cart.objects.filter(session_key=session_key).exists()


@pytest.mark.django_db
class TestCartAddItemValidation:
    """상품 추가 유효성 검증 에러"""

    def test_returns_error_when_missing_product_id(self):
        """product_id 누락 시 에러"""
        # Arrange
        user = UserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.post(
            reverse("cart-add-item"),
            {"quantity": 1},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "product_id" in str(response.data)

    def test_returns_error_when_quantity_is_negative(self):
        """수량이 음수일 때 에러"""
        # Arrange
        user = UserFactory()
        category = CategoryFactory()
        product = ProductFactory(category=category)
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.post(
            reverse("cart-add-item"),
            {"product_id": product.id, "quantity": -1},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestCartUpdateItemNotFound:
    """아이템 수정 시 NotFound 처리"""

    def test_returns_404_when_item_not_in_cart(self):
        """장바구니에 없는 아이템 수정 시 404"""
        # Arrange
        user = UserFactory()
        CartFactory(user=user)
        client = APIClient()
        client.force_authenticate(user=user)
        nonexistent_item_id = 99999

        # Act
        response = client.patch(
            reverse("cart-item-detail", kwargs={"pk": nonexistent_item_id}),
            {"quantity": 5},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_404_when_updating_other_users_item(self):
        """다른 사용자의 아이템 수정 시 404"""
        # Arrange
        user = UserFactory()
        other_user = UserFactory()
        category = CategoryFactory()
        product = ProductFactory(category=category)
        other_cart = CartFactory(user=other_user)
        other_item = CartItemFactory(cart=other_cart, product=product)

        client = APIClient()
        client.force_authenticate(user=user)
        CartFactory(user=user)  # user의 장바구니 생성

        # Act
        response = client.patch(
            reverse("cart-item-detail", kwargs={"pk": other_item.id}),
            {"quantity": 5},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestBulkAddQuantityValidation:
    """일괄 추가 수량 검증"""

    def test_rejects_quantity_less_than_one(self):
        """수량 1 미만 거부"""
        # Arrange
        user = UserFactory()
        CartFactory(user=user)
        category = CategoryFactory()
        product = ProductFactory(category=category, stock=100)
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.post(
            reverse("cart-bulk-add"),
            {"items": [{"product_id": product.id, "quantity": 0}]},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_207_MULTI_STATUS
        assert response.data["error_count"] == 1
        assert "1 이상" in str(response.data["errors"])

    def test_rejects_quantity_over_999(self):
        """수량 999 초과 거부"""
        # Arrange
        user = UserFactory()
        CartFactory(user=user)
        category = CategoryFactory()
        product = ProductFactory(category=category, stock=2000)
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.post(
            reverse("cart-bulk-add"),
            {"items": [{"product_id": product.id, "quantity": 1000}]},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_207_MULTI_STATUS
        assert response.data["error_count"] == 1
        assert "999 이하" in str(response.data["errors"])

    def test_rejects_non_integer_quantity(self):
        """정수가 아닌 수량 거부"""
        # Arrange
        user = UserFactory()
        CartFactory(user=user)
        category = CategoryFactory()
        product = ProductFactory(category=category, stock=100)
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.post(
            reverse("cart-bulk-add"),
            {"items": [{"product_id": product.id, "quantity": "abc"}]},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_207_MULTI_STATUS
        assert response.data["error_count"] >= 1


@pytest.mark.django_db
class TestBulkAddException:
    """일괄 추가 예외 처리"""

    def test_handles_database_exception(self, mocker):
        """DB 예외 발생 시 에러 처리"""
        # Arrange
        user = UserFactory()
        CartFactory(user=user)
        category = CategoryFactory()
        product = ProductFactory(category=category, stock=100)
        client = APIClient()
        client.force_authenticate(user=user)

        mocker.patch.object(
            CartItem.objects,
            "create",
            side_effect=Exception("DB connection error"),
        )

        # Act
        response = client.post(
            reverse("cart-bulk-add"),
            {"items": [{"product_id": product.id, "quantity": 1}]},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_207_MULTI_STATUS
        assert response.data["error_count"] >= 1
        assert "DB connection error" in str(response.data["errors"])


@pytest.mark.django_db
class TestCartItemViewSetAnonymous:
    """비회원 CartItemViewSet 처리"""

    def test_returns_empty_list_when_no_session(self):
        """세션 없으면 빈 목록 반환"""
        # Arrange
        client = APIClient()

        # Act
        response = client.get(reverse("cart-item-list"))

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_returns_empty_list_when_no_cart_exists(self):
        """Cart 없으면 빈 목록 반환"""
        # Arrange
        client = APIClient()
        client.get(reverse("cart-detail"))  # 세션만 생성, Cart는 다른 세션

        # Act
        response = client.get(reverse("cart-item-list"))

        # Assert
        assert response.status_code == status.HTTP_200_OK

    def test_creates_session_and_cart_on_item_create(self):
        """비회원 아이템 생성 시 세션과 카트 생성"""
        # Arrange
        client = APIClient()
        category = CategoryFactory()
        product = ProductFactory(category=category, stock=100)

        # Act
        response = client.post(
            reverse("cart-item-list"),
            {"product_id": product.id, "quantity": 1},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        assert client.session.session_key is not None
        session_key = client.session.session_key
        assert Cart.objects.filter(session_key=session_key).exists()

    def test_returns_error_on_invalid_create_request(self):
        """유효하지 않은 생성 요청 시 에러"""
        # Arrange
        client = APIClient()

        # Act
        response = client.post(
            reverse("cart-item-list"),
            {"quantity": 1},  # product_id 누락
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestCartItemViewSetUpdate:
    """CartItemViewSet 수정 테스트"""

    def test_updates_quantity_successfully(self):
        """수량 변경 성공"""
        # Arrange
        user = UserFactory()
        category = CategoryFactory()
        product = ProductFactory(category=category, stock=100)
        cart = CartFactory(user=user)
        item = CartItemFactory(cart=cart, product=product, quantity=2)
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.patch(
            reverse("cart-item-detail", kwargs={"pk": item.id}),
            {"quantity": 5},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        item.refresh_from_db()
        assert item.quantity == 5

    def test_deletes_item_when_quantity_zero(self):
        """수량 0이면 아이템 삭제"""
        # Arrange
        user = UserFactory()
        category = CategoryFactory()
        product = ProductFactory(category=category, stock=100)
        cart = CartFactory(user=user)
        item = CartItemFactory(cart=cart, product=product, quantity=2)
        item_id = item.id
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.patch(
            reverse("cart-item-detail", kwargs={"pk": item_id}),
            {"quantity": 0},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not CartItem.objects.filter(id=item_id).exists()

    def test_returns_404_for_nonexistent_item(self):
        """없는 아이템 수정 시 404"""
        # Arrange
        user = UserFactory()
        CartFactory(user=user)
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.patch(
            reverse("cart-item-detail", kwargs={"pk": 99999}),
            {"quantity": 5},
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_error_on_invalid_quantity(self):
        """유효하지 않은 수량 변경 시 에러"""
        # Arrange
        user = UserFactory()
        category = CategoryFactory()
        product = ProductFactory(category=category, stock=5)
        cart = CartFactory(user=user)
        item = CartItemFactory(cart=cart, product=product, quantity=2)
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.patch(
            reverse("cart-item-detail", kwargs={"pk": item.id}),
            {"quantity": 100},  # 재고 초과
            format="json",
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestCartItemViewSetDestroy:
    """CartItemViewSet 삭제 테스트"""

    def test_deletes_item_successfully(self):
        """아이템 삭제 성공"""
        # Arrange
        user = UserFactory()
        category = CategoryFactory()
        product = ProductFactory(category=category)
        cart = CartFactory(user=user)
        item = CartItemFactory(cart=cart, product=product)
        item_id = item.id
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.delete(
            reverse("cart-item-detail", kwargs={"pk": item_id})
        )

        # Assert
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not CartItem.objects.filter(id=item_id).exists()

    def test_returns_404_for_nonexistent_item(self):
        """없는 아이템 삭제 시 404"""
        # Arrange
        user = UserFactory()
        CartFactory(user=user)
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.delete(
            reverse("cart-item-detail", kwargs={"pk": 99999})
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_404_when_deleting_other_users_item(self):
        """다른 사용자의 아이템 삭제 시 404"""
        # Arrange
        user = UserFactory()
        other_user = UserFactory()
        category = CategoryFactory()
        product = ProductFactory(category=category)
        other_cart = CartFactory(user=other_user)
        other_item = CartItemFactory(cart=other_cart, product=product)

        client = APIClient()
        client.force_authenticate(user=user)
        CartFactory(user=user)

        # Act
        response = client.delete(
            reverse("cart-item-detail", kwargs={"pk": other_item.id})
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert CartItem.objects.filter(id=other_item.id).exists()


@pytest.mark.django_db
class TestCartDeleteItemNotFound:
    """장바구니 아이템 삭제 NotFound 처리"""

    def test_returns_404_when_deleting_nonexistent_item(self):
        """존재하지 않는 아이템 삭제 시 404"""
        # Arrange
        user = UserFactory()
        CartFactory(user=user)
        client = APIClient()
        client.force_authenticate(user=user)

        # Act
        response = client.delete(
            reverse("cart-item-detail", kwargs={"pk": 99999})
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
