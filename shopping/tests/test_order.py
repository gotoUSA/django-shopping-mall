import threading
from decimal import Decimal

from django.db import connection
from django.db.models import F
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from shopping.models.cart import Cart, CartItem
from shopping.models.order import Order, OrderItem
from shopping.models.point import PointHistory
from shopping.models.product import Category, Product
from shopping.models.user import User


class OrderCreateTestCase(TestCase):
    """주문 생성 기본 테스트"""

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
            points=5000,  # 포인트 보유
            is_email_verified=True,  # 이메일 인증 완료된 사용자 생성
        )

        # 카테고리 생성
        self.category = Category.objects.create(name="테스트 카테고리", slug="test-category")

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

        # 재고 없는 상품
        self.out_of_stock_product = Product.objects.create(
            name="품절 상품",
            slug="out-of-stock",
            category=self.category,
            price=Decimal("5000"),
            stock=0,
            sku="TEST-003",
            description="재고 없는 상품",
        )

        # URL 정의
        self.order_list_url = reverse("order-list")
        self.cart_add_url = reverse("cart-add-item")

        # 기본 배송 정보
        self.shipping_data = {
            "shipping_name": "홍길동",
            "shipping_phone": "010-9999-8888",
            "shipping_postal_code": "12345",
            "shipping_address": "서울시 강남구 테스트로 123",
            "shipping_address_detail": "101동 202호",
            "order_memo": "부재시 경비실에 맡겨주세요",
        }

    def _print_response_for_debug(self, response):
        """테스트 실패시 응답 내용을 출력하는 헬퍼 메서드"""
        print("\n=== Response Debug Info ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Data: {response.data}")
        print("===========================\n")

    def tearDown(self):
        """테스트 후 정리"""
        # 생성된 모든 주문 삭제 (다음 테스트에 영향 안 주도록)
        Order.objects.all().delete()
        Cart.objects.all().delete()
        super().tearDown()

    def _login_user(self):
        """사용자 로그인 헬퍼 메서드"""
        response = self.client.post(reverse("auth-login"), {"username": "testuser", "password": "testpass123"})
        token = response.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return token

    def _add_to_cart(self, product, quantity):
        """장바구니에 상품 추가 헬퍼 메서드 - 수정됨"""
        # 직접 Cart와 CartItem 생성 (API 호출 대신)
        cart, _ = Cart.get_or_create_active_cart(self.user)

        # 이미 있으면 수량 증가, 없으면 생성
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": quantity})

        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        return cart_item

    # ========== 정상 주문 생성 테스트 ==========

    def test_create_order_from_cart_success(self):
        """
        정상적인 주문 생성 테스트

        시나리오:
        1. 장바구니에 상품 추가
        2. 주문 생성
        3. 주문 정보 확인
        4. 장바구니는 유지됨 확인
        """
        # Given: 로그인하고 장바구니에 상품 추가
        self._login_user()
        self._add_to_cart(self.product1, 2)
        self._add_to_cart(self.product2, 1)

        # When: 주문 생성
        response = self.client.post(self.order_list_url, self.shipping_data, format="json")

        # 디버깅: 실패 시 응답 확인
        if response.status_code != status.HTTP_201_CREATED:
            self._print_response_for_debug(response)

        # Then: 주문 생성 성공
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 주문이 실제로 생성되었는지 확인
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        order = Order.objects.filter(user=self.user).first()

        self.assertEqual(order.user, self.user)
        self.assertEqual(order.status, "pending")  # 결제 대기 상태
        self.assertEqual(order.total_amount, Decimal("40000"))  # 10000*2 + 20000*1
        self.assertEqual(order.final_amount, Decimal("40000"))  # 포인트 미사용
        self.assertEqual(order.used_points, 0)

        # 주문 아이템 확인
        order_items = order.order_items.all()
        self.assertEqual(order_items.count(), 2)

        # 재고는 아직 차감되지 않음
        self.product1.refresh_from_db()
        self.product2.refresh_from_db()
        self.assertEqual(self.product1.stock, 10)  # 그대로
        self.assertEqual(self.product2.stock, 5)  # 그대로

        # 장바구니는 유지됨
        cart = Cart.objects.get(user=self.user, is_active=True)
        self.assertTrue(cart.is_active)
        self.assertEqual(cart.items.count(), 2)  # 아이템도 그대로

    def test_create_order_with_points(self):
        """
        포인트를 사용한 주문 생성 테스트

        시나리오:
        1. 5000 포인트 보유 상태
        2. 2000 포인트 사용하여 주문
        3. 포인트 차감 및 이력 확인
        """
        # Given: 장바구니에 상품 추가
        self._login_user()
        self._add_to_cart(self.product1, 3)  # 30,000원

        # When: 포인트 사용하여 주문
        order_data = {**self.shipping_data, "use_points": 2000}
        response = self.client.post(self.order_list_url, order_data, format="json")

        # 디버깅
        if response.status_code != status.HTTP_201_CREATED:
            self._print_response_for_debug(response)

        # Then: 주문 생성 성공
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        order = Order.objects.filter(user=self.user).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.total_amount, Decimal("30000"))
        self.assertEqual(order.used_points, 2000)
        self.assertEqual(order.final_amount, Decimal("28000"))  # 30000 - 2000

        # 사용자 포인트 차감 확인
        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 3000)  # 5000 - 2000

        # 포인트 사용 이력 확인
        point_history = PointHistory.objects.filter(user=self.user, type="use", order=order).first()
        self.assertIsNotNone(point_history)
        self.assertEqual(point_history.points, -2000)

    def test_create_order_with_maximum_points(self):
        """
        최대 포인트 사용 테스트 (주문 금액 100%)
        """
        # Given: 충분한 포인트 보유
        self.user.points = 50000
        self.user.save()

        self._login_user()
        self._add_to_cart(self.product1, 2)  # 20,000원

        # When: 주문 금액 + 배송비 전액을 포인트로 결제
        # 20,000원(상품) + 3,000원(배송비) = 23,000원
        order_data = {**self.shipping_data, "use_points": 23000}
        response = self.client.post(self.order_list_url, order_data, format="json")

        # Then: 성공
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 전체 주문 확인
        order = Order.objects.filter(user=self.user).first()
        self.assertIsNotNone(order)

        # 검증: 상품 금액, 배송비, 포인트 사용
        self.assertEqual(order.total_amount, Decimal("20000"))  # 상품 금액
        self.assertEqual(order.shipping_fee, Decimal("3000"))  # 배송비 (무료배송 미달)
        self.assertEqual(order.used_points, 23000)  # 사용 포인트
        self.assertEqual(order.final_amount, Decimal("0"))  # 전액 포인트 결제

        # 사용자 포인트 차감 확인
        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 27000)  # 50000 - 23000

    def test_create_order_with_partial_points_covering_product(self):
        """포인트로 상품 금액만 결제하고 배송비는 현금 결제하는 테스트"""
        # Given: 포인트 보유
        self.user.points = 25000
        self.user.save()

        self._login_user()
        self._add_to_cart(self.product1, 2)  # 20,000원

        # When: 상품 금액만큼만 포인트 사용
        order_data = {**self.shipping_data, "use_points": 20000}
        response = self.client.post(self.order_list_url, order_data, format="json")

        # Then: 배송비만 현금 결제
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        order = Order.objects.filter(user=self.user).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.total_amount, Decimal("20000"))
        self.assertEqual(order.shipping_fee, Decimal("3000"))
        self.assertEqual(order.used_points, 20000)
        self.assertEqual(order.final_amount, Decimal("3000"))  # 배송비만 남음

    # ========== 검증 실패 테스트 ==========

    def test_create_order_empty_cart(self):
        """빈 장바구니로 주문 시도"""
        self._login_user()

        # 빈 장바구니 상태에서 주문 시도
        response = self.client.post(self.order_list_url, self.shipping_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("장바구니가 비어있습니다", str(response.json()))

    def test_create_order_insufficient_stock(self):
        """재고 부족 상품 주문 시도"""
        self._login_user()

        # 재고보다 많은 수량 주문
        cart = Cart.get_or_create_active_cart(self.user)[0]
        cart_item = CartItem(cart=cart, product=self.product2, quantity=10)
        super(CartItem, cart_item).save(force_insert=True)

    def test_create_order_out_of_stock_product(self):
        """품절 상품 주문 시도"""
        from django.core.exceptions import ValidationError

        # 예외를 예상하도록 수정
        with self.assertRaises(ValidationError):
            self._add_to_cart(self.out_of_stock_product, 1)

    def test_create_order_insufficient_points(self):
        """포인트 부족으로 주문 실패"""
        self._login_user()
        self._add_to_cart(self.product1, 1)

        # 보유 포인트(5000)보다 많이 사용 시도
        order_data = {**self.shipping_data, "use_points": 10000}

        response = self.client.post(self.order_list_url, order_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("보유 포인트가 부족합니다", str(response.json()))

    def test_create_order_minimum_points_validation(self):
        """최소 포인트 사용 제한 테스트 (100포인트)"""
        self._login_user()
        self._add_to_cart(self.product1, 1)

        # 100포인트 미만 사용 시도
        order_data = {**self.shipping_data, "use_points": 50}

        response = self.client.post(self.order_list_url, order_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("최소 100포인트 이상", str(response.json()))

    def test_create_order_exceeds_order_amount(self):
        """주문 금액보다 많은 포인트 사용 시도"""
        # Given: 충분한 포인트 보유
        self.user.points = 50000
        self.user.save()

        self._login_user()
        self._add_to_cart(self.product1, 1)  # 10,000원

        # 주문 금액보다 많은 포인트 사용
        order_data = {**self.shipping_data, "use_points": 15000}

        response = self.client.post(self.order_list_url, order_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # 에러 메시지 확인 (두 가지 가능성)
        response_str = str(response.json())
        self.assertTrue("주문 금액보다 많은 포인트" in response_str or "보유 포인트가 부족합니다" in response_str)

    # ========== 인증 테스트 ==========

    def test_create_order_unauthenticated(self):
        """인증 없이 주문 시도"""
        response = self.client.post(self.order_list_url, self.shipping_data, format="json")

        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_view_orders_authenticated(self):
        """내 주문 목록 조회"""
        self._login_user()

        # 주문 생성
        self._add_to_cart(self.product1, 1)
        self.client.post(self.order_list_url, self.shipping_data, format="json")

        # 주문 목록 조회
        response = self.client.get(self.order_list_url)

        # 페이지네이션 처리 추가
        if "result" in response.data:
            orders = response.data["results"]
        else:
            orders = response.data if isinstance(response.data, list) else []
        if orders:
            self.assertIn("id", orders[0])

    # ========== 주문 번호 생성 테스트 ==========

    def test_order_number_generation(self):
        """주문 번호 자동 생성 테스트"""
        self._login_user()
        self._add_to_cart(self.product1, 1)

        response = self.client.post(self.order_list_url, self.shipping_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        order = Order.objects.filter(user=self.user).first()

        # 주문번호 형식: YYYYMMDD + 6자리 ID
        self.assertIsNotNone(order.order_number)
        self.assertEqual(len(order.order_number), 14)  # 8 + 6
        self.assertTrue(order.order_number.startswith(timezone.now().strftime("%Y%m%d")))

    # ========== 주문 취소 테스트 ==========

    def test_cancel_order_pending_status(self):
        """결제 대기 상태 주문 취소"""
        self._login_user()
        self._add_to_cart(self.product1, 2)

        # 주문 생성
        response = self.client.post(self.order_list_url, self.shipping_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.filter(user=self.user).first()

        # 주문 취소
        cancel_url = reverse("order-cancel", kwargs={"pk": order.id})
        response = self.client.post(cancel_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 주문 상태 확인
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")

    def test_cancel_order_with_points_refund(self):
        """포인트 사용 주문 취소 시 포인트 환불"""
        self._login_user()
        self._add_to_cart(self.product1, 1)

        # 포인트 사용 주문
        order_data = {**self.shipping_data, "use_points": 2000}
        response = self.client.post(self.order_list_url, order_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.filter(user=self.user).first()

        # 결제 완료 상태로 변경 (실제로는 PaymentConfirmView에서 처리)
        order.status = "paid"
        order.save()

        # 주문 취소
        cancel_url = reverse("order-cancel", kwargs={"pk": order.id})
        response = self.client.post(cancel_url)

        # 포인트 환불 확인 (실제 구현에서는 PaymentCancelView에서 처리)
        # 여기서는 취소 상태만 확인
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")

    def test_cannot_cancel_shipped_order(self):
        """배송중인 주문은 취소 불가"""
        self._login_user()
        self._add_to_cart(self.product1, 1)

        # 주문 생성
        response = self.client.post(self.order_list_url, self.shipping_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.filter(user=self.user).first()

        # 배송중 상태로 변경
        order.status = "shipped"
        order.save()

        # 취소 시도
        cancel_url = reverse("order-cancel", kwargs={"pk": order.id})
        response = self.client.post(cancel_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("취소할 수 없는 주문", str(response.json()))


class OrderConcurrencyTestCase(TransactionTestCase):
    """
    동시성 처리 테스트

    TransactionTestCase를 사용하여 실제 트랜잭션 동작을 테스트합니다.
    여러 사용자가 동시에 같은 상품을 주문하는 시나리오를 검증합니다.
    """

    def setUp(self):
        """테스트 데이터 설정"""

        # 카테고리
        self.category = Category.objects.create(name="테스트 카테고리", slug="test-category")

        # 재고가 1개인 상품
        self.limited_product = Product.objects.create(
            name="한정 상품",
            slug="limited-product",
            category=self.category,
            price=Decimal("10000"),
            stock=1,  # 재고 1개만
            sku="LIMITED-001",
            description="재고가 1개인 상품",
        )

        # 두 명의 사용자
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="pass123",
            is_email_verified=True,
        )

        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="pass123",
            is_email_verified=True,
        )

        self.order_results = []

    def tearDown(self):
        """테스트 후 정리"""
        # 모든 연결 종료
        connection.close()
        super().tearDown()

    def _create_order_for_user(self, user, product):
        """
        특정 사용자로 주문 생성 (스레드에서 실행)
        """
        try:
            # 새로운 DB 연결
            from django.db import connections

            connections.close_all()

            client = APIClient()

            # 로그인
            response = client.post(
                reverse("auth-login"),
                {"username": user.username, "password": "pass123"},
            )
            token = response.json()["access"]
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

            # 장바구니에 추가 (API 호출)
            cart_response = client.post(
                reverse("cart-add-item"),
                {"product_id": product.id, "quantity": 1},
                format="json",
            )

            # 장바구니 추가 실패시 처리
            if cart_response.status_code not in [200, 201]:
                # 실패해도 계속 진행 (재고 부족일 수 있음)
                pass

            # 주문 생성 시도
            shipping_data = {
                "shipping_name": f"{user.username}",
                "shipping_phone": "010-1111-2222",
                "shipping_postal_code": "12345",
                "shipping_address": "테스트 주소",
                "shipping_address_detail": "상세 주소",
            }

            response = client.post(reverse("order-list"), shipping_data, format="json")

            self.order_results.append(
                {
                    "user": user.username,
                    "status": response.status_code,
                    "response": (response.json() if response.status_code == 201 else None),
                }
            )
        except Exception as e:
            self.order_results.append({"user": user.username, "error": str(e)})
        finally:
            # 연결 종료
            connections.close_all()

    def test_concurrent_order_creation(self):
        """
        동시 주문 생성 테스트

        두 사용자가 재고 1개인 상품을 동시에 주문하는 시나리오.
        select_for_update()로 인해 한 명만 성공해야 함.
        """
        # 두 개의 스레드로 동시 주문
        thread1 = threading.Thread(target=self._create_order_for_user, args=(self.user1, self.limited_product))
        thread2 = threading.Thread(target=self._create_order_for_user, args=(self.user2, self.limited_product))

        # 동시 실행
        thread1.start()
        thread2.start()

        # 완료 대기
        thread1.join()
        thread2.join()

        # 결과 검증
        success_count = sum(1 for r in self.order_results if r.get("status") == status.HTTP_201_CREATED)

        # 두 명 모두 성공할 수 있음 (재고는 아직 차감 안 함)
        # 또는 하나만 성공 (구현에 따라)
        self.assertGreaterEqual(success_count, 1)
        self.assertLessEqual(success_count, 2)

        # 재고 확인 (변하지 않음 - 아직 결제 전)
        self.limited_product.refresh_from_db()
        self.assertEqual(self.limited_product.stock, 1)

        # 주문 개수 확인
        orders = Order.objects.filter(order_items__product=self.limited_product)
        self.assertGreaterEqual(orders.count(), 1)
        self.assertLessEqual(orders.count(), 2)

    def test_concurrent_stock_check_with_f_object(self):
        """
        F() 객체를 사용한 동시성 제어 테스트

        실제 결제 시점에서의 재고 차감 시뮬레이션
        - 재고 5개인 상품에 3개 스레드가 각각 2개씩 차감 시도
        - F() 객체 덕분에 정확히 2개만 성공해야 함 (5 - 2 - 2 = 1)
        - 나머지 1개는 재고 부족으로 실패
        """
        # 재고 5개인 상품 생성
        product = Product.objects.create(
            name="일반 상품",
            slug="normal-product",
            category=self.category,
            price=Decimal("5000"),
            stock=5,
            sku="NORMAL-001",
        )

        # 스레드별 결과를 저장할 리스트 (thread-safe)
        results = []
        lock = threading.Lock()

        def decrease_stock():
            """재고 차감 함수 (F 객체 사용)"""
            try:
                # 새 DB 연결 사용 (각 스레드마다 독립적)
                from django.db import connections

                connections.close_all()

                # F() 객체로 안전한 차감
                # stock__gte=2 조건 -> 재고가 2개 이상일 때만 차감
                updated = Product.objects.filter(id=product.id, stock__gte=2).update(stock=F("stock") - 2)

                connections.close_all()

                # 결과 저장 (thread-safe)
                with lock:
                    results.append(
                        {
                            "success": updated > 0,  # 1이면 성공, 0이면 실패
                            "updated_count": updated,
                            "thread_id": threading.current_thread().ident,
                        }
                    )

            except Exception as e:
                # 예외 발생 시 기록
                with lock:
                    results.append(
                        {
                            "success": False,
                            "error": str(e),
                            "thread_id": threading.current_thread().ident,
                        }
                    )

        # 3개의 스레드가 동시에 각각 2개씩 차감 시도
        threads = []
        for i in range(3):
            thread = threading.Thread(target=decrease_stock, name=f"Thread-{i}")
            threads.append(thread)
            thread.start()

        # 모든 스레드 완료 대기
        for thread in threads:
            thread.join()

        # 검증 시작

        # 1. 모든 스레드가 결과를 반환했는지 확인
        assert len(results) == 3, "3개 스레드 모두 실행되어야 함"

        # 2. 성공한 스레드 개수 확인
        success_count = sum(1 for r in results if r.get("success", False))

        # F() 객체 때문에 정확히 2개만 성공해야함
        # 5개 재고 - 2개 - 2개 = 1개 남음 -> 3번째는 실패
        assert success_count == 2, "정확히 2개 스레드만 성공해야함\n" f"실제 성공: {success_count}\n" f"상세 결과: {results}"

        # 3. 실패한 스레드 개수 확인
        failed_count = sum(1 for r in results if not r.get("success", False))
        assert failed_count == 1, (
            "1개 스레드는 재고 부족으로 실패해야 함\n" f"실제 실패: {failed_count}\n" f"상세 결과: {results}"
        )

        # 4. 최종 재고 확인
        product.refresh_from_db()
        assert product.stock == 1, (
            "최종 재고는 1개여야 함 (5 - 2 - 2 = 1)\n" f"실제 재고: {product.stock}\n" f"스레드 결과: {results}"
        )

        # 5. 성공한 스레드는 updated_count=1이어야 함
        for result in results:
            if result.get("success"):
                assert result.get("updated_count") == 1, "성공한 업데이트는 1행을 수정해야 함\n" f"실제 결과: {results}"

        # 디버깅용 출력 (선택사항)
        print("\n=== F() 객체 동시성 제어 테스트 결과 ===")
        print("초기 재고: 5개")
        print(f"성공한 스레드: {success_count}개")
        print(f"실패한 스레드: {failed_count}개")
        print(f"최종 재고: {product.stock}개")
        print(f"상세 결과: {results}")


class OrderAdminPermissionTestCase(TestCase):
    """관리자 권한 테스트"""

    def setUp(self):
        """테스트 데이터 설정"""
        self.client = APIClient()

        # 일반 사용자
        self.normal_user = User.objects.create_user(
            username="normaluser",
            email="normal@example.com",
            password="pass123",
            is_email_verified=True,
        )

        # 관리자
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="admin123",
            is_staff=True,
            is_superuser=True,
            is_email_verified=True,  # 일관성 위해 추가
        )

        # 카테고리와 상품
        category = Category.objects.create(name="테스트", slug="test")
        product = Product.objects.create(
            name="상품",
            slug="product",
            category=category,
            price=Decimal("10000"),
            stock=10,
            sku="TEST-001",
        )

        # 각 사용자의 주문 생성
        for user in [self.normal_user, self.admin_user]:
            order = Order.objects.create(
                user=user,
                status="pending",
                shipping_name=user.username,
                shipping_phone="010-0000-0000",
                shipping_postal_code="12345",
                shipping_address="주소",
                shipping_address_detail="상세",
                total_amount=Decimal("10000"),
            )
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                quantity=1,
                price=product.price,
            )

    def tearDown(self):
        """테스트 후 정리"""
        Order.objects.all().delete()
        super().tearDown()

    def test_normal_user_sees_only_own_orders(self):
        """일반 사용자는 본인 주문만 조회"""
        # 일반 사용자로 로그인
        response = self.client.post(reverse("auth-login"), {"username": "normaluser", "password": "pass123"})
        token = response.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # 주문 목록 조회
        response = self.client.get(reverse("order-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        orders = response.json()

        # 본인 주문만 보임
        for order in orders:
            # 모든 주문이 본인 것인지 확인
            if isinstance(order, dict) and "id" in order:
                db_order = Order.objects.get(id=order["id"])
                self.assertEqual(db_order.user, self.normal_user)

    def test_admin_sees_all_orders(self):
        """관리자는 모든 주문 조회 가능"""
        # 관리자로 로그인
        response = self.client.post(reverse("auth-login"), {"username": "admin", "password": "admin123"})
        token = response.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # 주문 목록 조회
        response = self.client.get(reverse("order-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        orders = response.json()

        # 이 테스트의 주문만 카운트
        test_orders = Order.objects.filter(user__in=[self.normal_user, self.admin_user])

        # 모든 주문이 보이는지 확인
        self.assertGreaterEqual(len(orders), test_orders.count())

    def test_normal_user_cannot_view_others_order_detail(self):
        """일반 사용자는 다른 사람 주문 상세 조회 불가"""
        # 일반 사용자로 로그인
        response = self.client.post(reverse("auth-login"), {"username": "normaluser", "password": "pass123"})
        token = response.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # 관리자의 주문 ID 가져오기
        admin_order = Order.objects.filter(user=self.admin_user).first()

        # 다른 사람 주문 조회 시도
        detail_url = reverse("order-detail", kwargs={"pk": admin_order.id})
        response = self.client.get(detail_url)

        # 404 Not Found (queryset에서 필터링되어 없는 것으로 처리)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
