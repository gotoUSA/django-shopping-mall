"""
장바구니 기능 TDD 테스트

이 파일은 장바구니의 모든 기능을 테스트합니다.
상품 추가, 수량 변경, 삭제, 재고 관리 등을 포함합니다.
"""

import json
from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock
import threading
import time

from shopping.models.user import User
from shopping.models.product import Product, Category
from shopping.models.cart import Cart, CartItem


class CartBasicTestCase(TestCase):
    """장바구니 기본 기능 테스트"""

    def setUp(self):
        """테스트 데이터 초기 설정"""
        # API 클라이언트
        self.client = APIClient()

        # 테스트 사용자 생성
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            phone_number="010-1234-5678",
        )

        # 다른 사용자 (권한 테스트용)
        self.other_user = User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            password="otherpass123",
        )

        # 카테고리 생성
        self.category = Category.objects.create(
            name="테스트 카테고리", slug="test-category"
        )

        # 테스트 상품들 생성
        self.product1 = Product.objects.create(
            name="테스트 상품 1",
            slug="test-product-1",
            category=self.category,
            price=Decimal("10000"),
            stock=10,
            sku="TEST-001",
            description="테스트 상품 1 설명",
        )

        self.product2 = Product.objects.create(
            name="테스트 상품 2",
            slug="test-product-2",
            category=self.category,
            price=Decimal("20000"),
            stock=5,
            sku="TEST-002",
            description="테스트 상품 2 설명",
        )

        # 품절 상품
        self.out_of_stock_product = Product.objects.create(
            name="품절 상품",
            slug="out-of-stock",
            category=self.category,
            price=Decimal("5000"),
            stock=0,
            sku="TEST-003",
            description="재고 없는 상품",
        )

        # 비활성 상품
        self.inactive_product = Product.objects.create(
            name="판매중단 상품",
            slug="inactive-product",
            category=self.category,
            price=Decimal("15000"),
            stock=10,
            is_active=False,  # 판매 중단
            sku="TEST-004",
            description="판매 중단된 상품",
        )

        # URL 정의
        self.cart_url = reverse("cart-detail")  # GET /api/cart/
        self.cart_summary_url = reverse("cart-summary")  # GET /api/cart/summary/
        self.cart_add_url = reverse("cart-add-item")  # POST /api/cart/add_item/
        self.cart_items_url = reverse("cart-items")  # GET /api/cart/items/
        self.cart_clear_url = reverse("cart-clear")  # POST /api/cart/clear/
        self.cart_check_stock_url = reverse(
            "cart-check-stock"
        )  # GET /api/cart/check_stock/

    def tearDown(self):
        """테스트 후 정리"""
        Cart.objects.all().delete()
        super().tearDown()

    def _login_user(self, user=None):
        """사용자 로그인 헬퍼 메서드"""
        if user is None:
            user = self.user

        response = self.client.post(
            reverse("auth-login"),
            {
                "username": user.username,
                "password": "testpass123" if user == self.user else "otherpass123",
            },
        )
        token = response.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return token

    # ========== 장바구니 생성 및 조회 테스트 ==========

    def test_get_or_create_cart_for_authenticated_user(self):
        """인증된 사용자의 장바구니 생성/조회 테스트"""
        self._login_user()

        # 장바구니 조회
        response = self.client.get(self.cart_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertIn("id", data)
        self.assertIn("items", data)
        self.assertEqual(data["total_amount"], "0")
        self.assertEqual(data["total_quantity"], 0)
        self.assertEqual(len(data["items"]), 0)

        # DB에 장바구니가 생성되었는지 확인
        cart = Cart.objects.get(user=self.user, is_active=True)
        self.assertIsNotNone(cart)

    def test_cart_requires_authentication(self):
        """비로그인 사용자 접근 차단 테스트"""
        # 인증 없이 장바구니 접근 시도
        response = self.client.get(self.cart_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_has_only_one_active_cart(self):
        """사용자당 활성 장바구니는 하나만 존재"""
        self._login_user()

        # 첫 번째 장바구니 조회
        response1 = self.client.get(self.cart_url)
        cart_id1 = response1.json()["id"]

        # 두 번째 장바구니 조회
        response2 = self.client.get(self.cart_url)
        cart_id2 = response2.json()["id"]

        # 같은 장바구니여야 함
        self.assertEqual(cart_id1, cart_id2)

        # DB에서도 확인
        cart_count = Cart.objects.filter(user=self.user, is_active=True).count()
        self.assertEqual(cart_count, 1)

    # ========== 상품 추가 테스트 ==========

    def test_add_product_to_cart(self):
        """장바구니에 상품 추가 테스트"""
        self._login_user()

        # 상품 추가
        add_data = {"product_id": self.product1.id, "quantity": 2}
        response = self.client.post(self.cart_add_url, add_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response_data = response.json()
        self.assertIn("message", response_data)
        self.assertEqual(response_data["message"], "장바구니에 추가되었습니다.")

        # 추가된 아이템 확인
        item = response_data["item"]
        self.assertEqual(item["product_id"], self.product1.id)
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["subtotal"], "20000")  # 10000 * 2

        # DB 확인
        cart = Cart.objects.get(user=self.user, is_active=True)
        cart_item = CartItem.objects.get(cart=cart, product=self.product1)
        self.assertEqual(cart_item.quantity, 2)

    def test_add_same_product_increases_quantity(self):
        """이미 담긴 상품 추가시 수량 증가 테스트"""
        self._login_user()

        # 첫 번째 추가
        add_data = {"product_id": self.product1.id, "quantity": 2}
        self.client.post(self.cart_add_url, add_data, format="json")

        # 두 번째 추가 (같은 상품)
        add_data = {"product_id": self.product1.id, "quantity": 3}
        response = self.client.post(self.cart_add_url, add_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 수량이 5가 되어야 함 (2 + 3)
        item = response.json()["item"]
        self.assertEqual(item["quantity"], 5)
        self.assertEqual(item["subtotal"], "50000")  # 10000 * 5

    def test_add_out_of_stock_product(self):
        """품절 상품 추가 시도 테스트"""
        self._login_user()

        add_data = {"product_id": self.out_of_stock_product.id, "quantity": 1}
        response = self.client.post(self.cart_add_url, add_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("품절된 상품입니다.", str(response.json()))

    def test_add_inactive_product(self):
        """비활성(판매중단) 상품 추가 시도 테스트"""
        self._login_user()

        add_data = {"product_id": self.inactive_product.id, "quantity": 1}
        response = self.client.post(self.cart_add_url, add_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("현재 판매하지 않는 상품입니다.", str(response.json()))

    def test_add_product_exceeds_stock(self):
        """재고 초과 수량 추가 시도 테스트"""
        self._login_user()

        # product1의 재고는 10개
        add_data = {"product_id": self.product1.id, "quantity": 15}  # 재고 초과
        response = self.client.post(self.cart_add_url, add_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("재고가 부족합니다", str(response.json()))

    def test_add_nonexistent_product(self):
        """존재하지 않는 상품 추가 시도 테스트"""
        self._login_user()

        add_data = {"product_id": 99999, "quantity": 1}  # 존재하지 않는 ID
        response = self.client.post(self.cart_add_url, add_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("찾을 수 없습니다", str(response.json()))

    # ========== 수량 변경 테스트 ==========

    def test_update_cart_item_quantity(self):
        """장바구니 아이템 수량 변경 테스트"""
        self._login_user()

        # 상품 추가
        add_data = {"product_id": self.product1.id, "quantity": 2}
        response = self.client.post(self.cart_add_url, add_data, format="json")
        item_id = response.json()["item"]["id"]

        # 수량 변경
        update_url = reverse("cart-item-detail", kwargs={"pk": item_id})
        update_data = {"quantity": 5}
        response = self.client.patch(update_url, update_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(response_data["message"], "수량이 변경되었습니다.")
        self.assertEqual(response_data["item"]["quantity"], 5)
        self.assertEqual(response_data["item"]["subtotal"], "50000")

    def test_update_quantity_to_zero_deletes_item(self):
        """수량을 0으로 변경시 아이템 삭제 테스트"""
        self._login_user()

        # 상품 추가
        add_data = {"product_id": self.product1.id, "quantity": 2}
        response = self.client.post(self.cart_add_url, add_data, format="json")
        item_id = response.json()["item"]["id"]

        # 수량을 0으로 변경
        update_url = reverse("cart-item-detail", kwargs={"pk": item_id})
        update_data = {"quantity": 0}
        response = self.client.patch(update_url, update_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # DB에서 삭제 확인
        cart_item_exists = CartItem.objects.filter(id=item_id).exists()
        self.assertFalse(cart_item_exists)

    def test_update_quantity_exceeds_stock(self):
        """재고 초과 수량으로 변경 시도 테스트"""
        self._login_user()

        # 상품 추가
        add_data = {"product_id": self.product1.id, "quantity": 2}
        response = self.client.post(self.cart_add_url, add_data, format="json")
        item_id = response.json()["item"]["id"]

        # 재고(10개)보다 많은 수량으로 변경 시도
        update_url = reverse("cart-item-detail", kwargs={"pk": item_id})
        update_data = {"quantity": 15}
        response = self.client.patch(update_url, update_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("재고가 부족합니다", str(response.json()))

    # ========== 아이템 삭제 테스트 ==========

    def test_delete_cart_item(self):
        """장바구니 아이템 삭제 테스트"""
        self._login_user()

        # 상품 추가
        add_data = {"product_id": self.product1.id, "quantity": 2}
        response = self.client.post(self.cart_add_url, add_data, format="json")
        item_id = response.json()["item"]["id"]

        # 아이템 삭제
        delete_url = reverse("cart-item-detail", kwargs={"pk": item_id})
        response = self.client.delete(delete_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # DB에서 삭제 확인
        cart_item_exists = CartItem.objects.filter(id=item_id).exists()
        self.assertFalse(cart_item_exists)

    def test_delete_other_users_cart_item(self):
        """다른 사용자의 장바구니 아이템 삭제 시도 테스트"""

        # 첫 번째 사용자로 상품 추가
        self._login_user(self.user)
        add_data = {"product_id": self.product1.id, "quantity": 2}
        response = self.client.post(self.cart_add_url, add_data, format="json")
        item_id = response.json()["item"]["id"]

        # 다른 사용자로 로그인
        self._login_user(self.other_user)

        # 첫 번째 사용자의 아이템 삭제 시도
        delete_url = reverse("cart-item-detail", kwargs={"pk": item_id})
        response = self.client.delete(delete_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ========== 장바구니 비우기 테스트 ==========

    def test_clear_cart(self):
        """
        장바구니 비우기 테스트
        """
        self._login_user()

        # 여러 상품 추가
        self.client.post(
            self.cart_add_url, {"product_id": self.product1.id, "quantity": 2}
        )
        self.client.post(
            self.cart_add_url, {"product_id": self.product2.id, "quantity": 1}
        )

        # 장바구니 비우기
        clear_data = {"confirm": True}
        response = self.client.post(self.cart_clear_url, clear_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 장바구니가 비어있는지 확인
        cart = Cart.objects.get(user=self.user, is_active=True)
        self.assertEqual(cart.items.count(), 0)

    def test_clear_cart_without_confirmation(self):
        """확인 없이 장바구니 비우기 시도 테스트"""
        self._login_user()

        # 상품 추가
        self.client.post(
            self.cart_add_url, {"product_id": self.product1.id, "quantity": 2}
        )

        # 확인 없이 비우기 시도
        clear_data = {"confirm": False}
        response = self.client.post(self.cart_clear_url, clear_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # 장바구니가 그대로인지 확인
        cart = Cart.objects.get(user=self.user, is_active=True)
        self.assertEqual(cart.items.count(), 1)

    # ========== 장바구니 요약 및 계산 테스트 ==========

    def test_cart_summary(self):
        """장바구니 요약 정보 테스트"""
        self._login_user()

        # 여러 상품 추가
        self.client.post(
            self.cart_add_url, {"product_id": self.product1.id, "quantity": 2}
        )
        self.client.post(
            self.cart_add_url, {"product_id": self.product2.id, "quantity": 3}
        )

        # 요약 정보 조회
        response = self.client.get(self.cart_summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data["total_amount"], "80000")  # 10000*2 + 20000*3
        self.assertEqual(data["total_quantity"], 5)  # 2 + 3
        self.assertEqual(data["item_count"], 2)  # 2종류

    def test_cart_total_calculation(self):
        """장바구니 총액 계산 정확성 테스트"""
        self._login_user()

        # 상품 추가
        self.client.post(
            self.cart_add_url, {"product_id": self.product1.id, "quantity": 3}
        )
        self.client.post(
            self.cart_add_url, {"product_id": self.product2.id, "quantity": 2}
        )

        # 전체 장바구니 조회
        response = self.client.get(self.cart_url)

        data = response.json()

        # 총액 확인: (10000 * 3) + (20000 * 2) = 70000
        self.assertEqual(data["total_amount"], "70000")

        # 각 아이템의 소계 확인
        items = data["items"]
        self.assertEqual(len(items), 2)

        for item in items:
            if item["product_id"] == self.product1.id:
                self.assertEqual(item["subtotal"], "30000")
            elif item["product_id"] == self.product2.id:
                self.assertEqual(item["subtotal"], "40000")

    # ========== 재고 확인 테스트 ==========

    def test_check_stock_all_available(self):
        """모든 상품 재고 충분 테스트"""
        self._login_user()

        # 재고 내에서 상품 추가
        self.client.post(
            self.cart_add_url, {"product_id": self.product1.id, "quantity": 5}
        )
        self.client.post(
            self.cart_add_url, {"product_id": self.product2.id, "quantity": 3}
        )

        # 재고 확인
        response = self.client.get(self.cart_check_stock_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertFalse(data["has_issues"])
        self.assertEqual(data["message"], "모든 상품을 구매할 수 있습니다.")

    def test_check_stock_all_available(self):
        """모든 상품 재고 충분 테스트"""
        self._login_user()

        # 재고 내에서 상품 추가
        self.client.post(
            self.cart_add_url, {"product_id": self.product1.id, "quantity": 5}
        )
        self.client.post(
            self.cart_add_url, {"product_id": self.product2.id, "quantity": 3}
        )

        # 재고 확인
        response = self.client.get(self.cart_check_stock_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertFalse(data["has_issues"])
        self.assertEqual(data["message"], "모든 상품을 구매할 수 있습니다.")

    def test_check_stock_with_issues(self):
        """
        재고 부족 상품이 있을 때 테스트
        """
        self._login_user()

        # 장바구니에 상품 추가
        cart = Cart.get_or_create_active_cart(self.user)[0]

        # 먼저 정상적으로 CartItem 생성
        cart_item = CartItem.objects.create(
            cart=cart, product=self.product1, quantity=5  # 재고(10개) 내에서 생성
        )

        # 그 후 상품의 재고를 줄여서 재고 부족 상황 만들기
        self.product1.stock = 3  # 재고를 3개로 줄임 (quantity=5보다 적게)
        self.product1.save()

        # 재고 확인
        response = self.client.get(self.cart_check_stock_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertTrue(data["has_issues"])
        self.assertIn("issues", data)

        issue = data["issues"][0]
        self.assertEqual(issue["product_id"], self.product1.id)
        self.assertEqual(issue["issue"], "재고 부족")
        self.assertEqual(issue["requested"], 5)
        self.assertEqual(issue["available"], 3)

    def test_check_stock_with_inactive_product(self):
        """비활성 상품이 있을 때 재고 확인 테스트"""
        self._login_user()

        # 장바구니에 상품 추가
        cart = Cart.get_or_create_active_cart(self.user)[0]

        # 정상 상품 추가
        CartItem.objects.create(cart=cart, product=self.product1, quantity=2)

        # 상품을 비활성화
        self.product1.is_active = False
        self.product1.save()

        # 재고 확인
        response = self.client.get(self.cart_check_stock_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertTrue(data["has_issues"])

        issue = data["issues"][0]
        self.assertEqual(issue["issue"], "판매 중단")
        self.assertEqual(issue["available"], 0)


class CartConcurrencyTestCase(TransactionTestCase):
    """
    장바구니 동시성 처리 테스트

    여러 요청이 동시에 같은 장바구니를 수정할 때의 동작을 테스트합니다.
    """

    def setUp(self):
        """테스트 데이터 설정"""
        self.client = APIClient()

        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

        self.category = Category.objects.create(
            name="테스트 카테고리", slug="test-category"
        )

        self.product = Product.objects.create(
            name="테스트 상품",
            slug="test-product",
            category=self.category,
            price=Decimal("10000"),
            stock=10,
            sku="TEST-001",
        )

        self.cart_add_url = reverse("cart-add-item")

    def test_concurrent_add_same_product(self):
        """동시에 같은 상품을 추가할 때 정확한 수량 처리 테스트"""
        # 로그인
        response = self.client.post(
            reverse("auth-login"), {"username": "testuser", "password": "testpass123"}
        )
        token = response.json()["access"]

        success_count = 0
        errors = []
        expected_total_quantity = 5  # 5개 스레드 * 1개씩

        def add_to_cart():
            """장바구니에 상품 추가하는 함수"""
            nonlocal success_count
            try:
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

                response = client.post(
                    self.cart_add_url,
                    {"product_id": self.product.id, "quantity": 1},
                    format="json",
                )

                if response.status_code == status.HTTP_201_CREATED:
                    success_count += 1
            except Exception as e:
                errors.append(str(e))

        # 5개의 스레드로 동시에 추가
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=add_to_cart)
            threads.append(thread)
            thread.start()

        # 모든 스레드 완료 대기
        for thread in threads:
            thread.join()

        # 최종 수량 확인
        cart = Cart.objects.get(user=self.user, is_active=True)
        try:
            cart_item = CartItem.objects.get(cart=cart, product=self.product)
            self.assertEqual(cart_item.quantity, expected_total_quantity)
        except CartItem.DoesNotExist:
            self.fail("장바구니 아이템이 생성되지 않았습니다.")

    def test_concurrent_quantity_update(self):
        """동시 수량 변경 시 Last Write Wins 정책 테스트"""
        # 초기 장바구니 설정
        cart = Cart.get_or_create_active_cart(self.user)[0]
        cart_item = CartItem.objects.create(cart=cart, product=self.product, quantity=5)
        initial_quantity = cart_item.quantity

        # 로그인
        response = self.client.post(
            reverse("auth-login"), {"username": "testuser", "password": "testpass123"}
        )
        token = response.json()["access"]

        results = []
        update_times = []

        def update_quantity(new_quantity):
            """수량 변경 함수"""
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            update_url = reverse("cart-item-detail", kwargs={"pk": cart_item.id})

            start_time = time.time()
            response = client.patch(
                update_url, {"quantity": new_quantity}, format="json"
            )
            end_time = time.time()
            results.append(
                {
                    "quantity": new_quantity,
                    "status": response.status_code,
                    "start": start_time,
                    "end": end_time,
                }
            )

        # 여러 스레드로 다른 수량으로 변경 시도
        threads = []
        quantities = [3, 7, 2, 8, 4]

        for qty in quantities:
            thread = threading.Thread(target=update_quantity, args=(qty,))
            threads.append(thread)

        # 모든 스레드 거의 동시 시작
        for thread in threads:
            thread.start()

        # 모든 스레드 완료 대기
        for thread in threads:
            thread.join()

        # 마지막 업데이트가 반영되어야 함
        cart_item.refresh_from_db()

        # 1. 모든 요청이 성공했는지 확인 (select_for_update로 순차 처리됨)
        success_count = sum(1 for r in results if r["status"] == 200)
        self.assertEqual(
            success_count,
            len(quantities),
            f"모든 요청이 성공해야 함. 성공: {success_count}/{len(quantities)}",
        )

        # 2. 최종값이 요청한 값 중 하나여야 함
        self.assertIn(
            cart_item.quantity,
            quantities,
            f"최종 수량({cart_item.quantity})은 요청한 값 중 하나여야 함: {quantities}",
        )

        # 3. 데이터 정합성 확인
        self.assertGreater(cart_item.quantity, 0, "수량은 0보다 커야 함")
        self.assertLessEqual(
            cart_item.quantity,
            self.product.stock,
            f"수량은 재고({self.product.stock})를 초과할 수 없음",
        )

        # 4. 실제로 업데이트가 되었는지 확인
        self.assertNotEqual(
            cart_item.quantity,
            initial_quantity,
            f"수량이 초기값({initial_quantity})에서 변경되어야 함",
        )

        # 디버깅 정보 출력 (실패 시 유용)
        if success_count != len(quantities):
            print(f"\n업데이트 결과:")
            for r in sorted(results, key=lambda x: x["end"]):
                print(f"  수량 {r['quantity']}: 상태 {r['status']}")
            print(f"최종 수량: {cart_item.quantity}")


class CartPerformanceTestCase(TestCase):
    """
    장바구니 성능 테스트

    많은 상품이 담긴 장바구니의 성능을 테스트합니다.
    """

    def setUp(self):
        """대량 테스트 데이터 생성"""
        self.client = APIClient()

        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

        self.category = Category.objects.create(
            name="테스트 카테고리", slug="test-category"
        )

        # 100개의 상품 생성
        self.products = []
        for i in range(100):
            product = Product.objects.create(
                name=f"테스트 상품 {i}",
                slug=f"test-product-{i}",
                category=self.category,
                price=Decimal(str(1000 * (i + 1))),
                stock=100,
                sku=f"TEST-{i:03d}",
            )
            self.products.append(product)

    def test_large_cart_performance(self):
        """많은 상품이 담긴 장바구니 조회 성능 테스트"""
        # 로그인
        response = self.client.post(
            reverse("auth-login"), {"username": "testuser", "password": "testpass123"}
        )
        token = response.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # 50개 상품을 장바구니에 추가
        cart = Cart.get_or_create_active_cart(self.user)[0]

        cart_items = []
        for i in range(50):
            cart_items.append(
                CartItem(cart=cart, product=self.products[i], quantity=i + 1)
            )
        CartItem.objects.bulk_create(cart_items)

        # 장바구니 조회 시간 측정
        import time

        start_time = time.time()

        response = self.client.get(reverse("cart-detail"))

        end_time = time.time()
        elapsed_time = end_time - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 응답 시간이 1초 이내여야 함
        self.assertLess(elapsed_time, 1.0, f"조회 시간: {elapsed_time:.3f}초")

        # 데이터 정확성 확인
        data = response.json()
        self.assertEqual(len(data["items"]), 50)

        # 총액 계산 확인
        expected_total = sum(self.products[i].price * (i + 1) for i in range(50))
        self.assertEqual(Decimal(data["total_amount"]), expected_total)
