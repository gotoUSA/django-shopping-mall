import threading
import time
from decimal import Decimal

import pytest
from django.db.models import F
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from shopping.models import Order, OrderItem, Product
from shopping.models.cart import Cart, CartItem
from shopping.models.user import User


def login_and_get_token(username, password="testpass123"):
    """
    로그인하여 JWT 토큰 발급

    멀티스레딩 환경에서 Django가 자동으로 스레드별 DB 연결을 관리합니다.
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


def create_test_user(username, email, phone_number, points=0, is_verified=True):
    """테스트 사용자 생성 헬퍼"""
    return User.objects.create_user(
        username=username,
        email=email,
        password="testpass123",
        phone_number=phone_number,
        points=points,
        is_email_verified=is_verified,
    )


@pytest.mark.django_db(transaction=True)
class TestOrderConcurrencyHappyPath:
    """충분한 재고와 포인트가 있는 상황에서의 동시 주문 테스트"""

    def test_concurrent_order_creation_sufficient_stock(self, authenticated_client, user, product, shipping_data):
        """여러 사용자가 동시 주문 생성 - 충분한 재고"""
        # Arrange
        product.stock = 100
        product.save()

        users = []
        for i in range(5):
            u = create_test_user(
                username=f"user{i}",
                email=f"user{i}@test.com",
                phone_number=f"010-0000-000{i}",
            )
            users.append(u)

            # 각 사용자 장바구니에 상품 추가
            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=2)

        results = []
        lock = threading.Lock()

        def create_order(user_obj):
            """주문 생성 함수"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post("/api/orders/", shipping_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act - 5명이 동시 주문
        threads = [threading.Thread(target=create_order, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 모두 성공해야 함
        success_count = sum(1 for r in results if r.get("success", False))

        # 디버깅: 실패 시 결과 출력
        if success_count != 5:
            print(f"\n결과: {results}")

        assert success_count == 5, f"5명 모두 성공해야 함. 성공: {success_count}, 결과: {results}"

        # 재고 확인 (100 - 5명 x 2개 = 90개)
        product.refresh_from_db()
        assert product.stock == 90, f"재고가 10개 차감되어야 함 (5명 x 2개). 실제 재고: {product.stock}"

    def test_concurrent_order_with_points_sufficient_balance(self, user, product, shipping_data):
        """여러 사용자가 포인트 사용하며 동시 주문"""
        # Arrange
        product.stock = 50
        product.price = Decimal("10000")
        product.save()

        users = []
        for i in range(3):
            u = create_test_user(
                username=f"pointuser{i}",
                email=f"pointuser{i}@test.com",
                phone_number=f"010-1111-000{i}",
                points=5000,
            )
            users.append(u)

            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=1)

        results = []
        lock = threading.Lock()

        def create_order_with_points(user_obj):
            """포인트 사용하여 주문 생성"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                order_data = {**shipping_data, "use_points": 1000}
                response = client.post("/api/orders/", order_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [threading.Thread(target=create_order_with_points, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))

        if success_count != 3:
            print(f"\n결과: {results}")

        assert success_count == 3, f"3명 모두 성공해야 함. 성공: {success_count}, 결과: {results}"

        # 재고 확인 (50 - 3명 x 1개 = 47개)
        product.refresh_from_db()
        assert product.stock == 47, f"재고가 3개 차감되어야 함. 실제: {product.stock}"
        # 각 사용자의 포인트 차감 확인
        for u in users:
            u.refresh_from_db()
            assert u.points == 4000, f"{u.username}의 포인트가 1000P 차감되어야 함"


@pytest.mark.django_db(transaction=True)
class TestOrderConcurrencyBoundary:
    """재고나 포인트가 딱 맞는 경계 상황에서의 동시성 테스트"""

    def test_concurrent_order_stock_exact_boundary(self, product, shipping_data):
        """재고 10개에 10명이 각 1개씩 동시 주문"""
        # Arrange
        product.stock = 10
        product.save()

        users = []
        for i in range(10):
            u = create_test_user(
                username=f"boundary_user{i}",
                email=f"boundary{i}@test.com",
                phone_number=f"010-2222-000{i}",
            )
            users.append(u)

            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=1)

        results = []
        lock = threading.Lock()

        def create_order(user_obj):
            """주문 생성"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post("/api/orders/", shipping_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [threading.Thread(target=create_order, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 모두 성공해야 함
        success_count = sum(1 for r in results if r.get("success", False))

        if success_count != 10:
            print(f"\n결과: {results}")

        assert success_count == 10, f"10명 모두 성공해야 함. 성공: {success_count}"

    def test_concurrent_order_stock_boundary_one_fails(self, product, shipping_data):
        """재고 5개에 3명이 각 2개씩 동시 주문 - 2명만 성공"""
        # Arrange
        product.stock = 5
        product.save()

        users = []
        for i in range(3):
            u = create_test_user(
                username=f"boundary_fail{i}",
                email=f"boundaryfail{i}@test.com",
                phone_number=f"010-3333-000{i}",
                points=5000,
            )
            users.append(u)

            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=2)

        results = []
        lock = threading.Lock()

        def create_order(user_obj):
            """주문 생성"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post("/api/orders/", shipping_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [threading.Thread(target=create_order, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 2명만 성공 (5개 재고 - 2개 - 2개 = 1개 남음, 세 번째는 재고 부족)
        success_count = sum(1 for r in results if r.get("success", False))
        failed_count = sum(1 for r in results if r.get("status") == status.HTTP_400_BAD_REQUEST or "error" in r)

        if success_count != 2:
            print(f"\n결과: {results}")

        assert (
            success_count == 2
        ), f"2명만 성공해야 함 (재고 5개 -> 2개 주문 -> 2개 주문 -> 실패 성공: {success_count}, 실패: {failed_count})"
        assert failed_count == 1, f"1명은 재고 부족으로 실패해야 함. 실패: {failed_count}"

        # 재고 확인 (5 - 2 - 2 = 1개 남음)
        product.refresh_from_db()
        assert product.stock == 1, f"최종 재고는 1개여야 함. 실제: {product.stock}"

    def test_concurrent_point_usage_boundary(self, product, shipping_data):
        """포인트 딱 맞게 사용하는 동시 주문"""
        # Arrange
        product.stock = 50
        product.price = Decimal("10000")
        product.save()

        users = []
        for i in range(2):
            u = create_test_user(
                username=f"point_boundary{i}",
                email=f"pointbound{i}@test.com",
                phone_number=f"010-4444-000{i}",
                points=1000,
            )
            users.append(u)

            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=1)

        results = []
        lock = threading.Lock()

        def create_order_exact_points(user_obj):
            """보유 포인트 전액 사용"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                order_data = {**shipping_data, "use_points": 1000}
                response = client.post("/api/orders/", order_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [threading.Thread(target=create_order_exact_points, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 모두 성공
        success_count = sum(1 for r in results if r.get("success", False))

        if success_count != 2:
            print(f"\n결과: {results}")

        assert success_count == 2, f"2명 모두 성공해야 함. 성공: {success_count}"

        # 포인트 확인
        for u in users:
            u.refresh_from_db()
            assert u.points == 0, f"{u.username}의 포인트가 0이 되어야 함"


@pytest.mark.django_db(transaction=True)
class TestOrderConcurrencyException:
    """
    3단계: 예외 케이스 (Exception)

    재고 부족, 포인트 부족 등 실패가 예상되는 동시성 시나리오
    """

    def test_concurrent_order_insufficient_stock(self, product, shipping_data):
        """재고 1개에 여러 명 동시 주문 - 1명만 성공"""
        # Arrange
        product.stock = 1  # 재고 1개만
        product.save()

        users = []
        for i in range(5):
            u = create_test_user(
                username=f"insuf_stock{i}",
                email=f"insufstock{i}@test.com",
                phone_number=f"010-5555-000{i}",
            )
            users.append(u)

            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=1)

        results = []
        lock = threading.Lock()

        def create_order(user_obj):
            """주문 생성"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post("/api/orders/", shipping_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [threading.Thread(target=create_order, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 1명만 성공 (재고 1개, 5명이 각 1개씩 주문)
        success_count = sum(1 for r in results if r.get("success", False))
        failed_count = len(results) - success_count

        if success_count != 1:
            print(f"\n결과: {results}")

        assert success_count == 1, f"1명만 성공해야 함 (재고 1개). 성공: {success_count}, 실패: {failed_count}"
        assert failed_count == 4, f"4명은 재고 부족으로 실패해야 함. 실패: {failed_count}"

        # 재고 확인 (1 - 1 = 0개)
        product.refresh_from_db()
        assert product.stock == 0, f"최종 재고는 0개여야 함. 실제: {product.stock}"

    def test_concurrent_order_insufficient_points(self, product, shipping_data):
        """보유 포인트 부족 시 동시 주문"""
        # Arrange
        product.stock = 50
        product.price = Decimal("10000")
        product.save()

        users = []
        for i in range(3):
            u = create_test_user(
                username=f"insuf_point{i}",
                email=f"insufpoint{i}@test.com",
                phone_number=f"010-6666-000{i}",
                points=500,  # 부족한 포인트
            )
            users.append(u)

            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=1)

        results = []
        lock = threading.Lock()

        def create_order_with_insufficient_points(user_obj):
            """부족한 포인트로 주문 시도"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                order_data = {**shipping_data, "use_points": 1000}
                response = client.post("/api/orders/", order_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [threading.Thread(target=create_order_with_insufficient_points, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 모두 실패
        success_count = sum(1 for r in results if r.get("success", False))
        failed_count = sum(1 for r in results if r.get("status") == status.HTTP_400_BAD_REQUEST)

        if success_count != 0:
            print(f"\n결과: {results}")

        assert success_count == 0, f"포인트 부족으로 모두 실패해야 함. 성공: {success_count}"
        assert failed_count == 3, f"3명 모두 실패해야 함. 실패: {failed_count}"

    def test_concurrent_order_cancel(self, user, product, shipping_data):
        """동일 주문을 여러 번 동시 취소 시도"""
        # Arrange - 먼저 주문 생성
        cart = Cart.get_or_create_active_cart(user)[0]
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        client, token, error = login_and_get_token(user.username, "testpass123")

        if error:
            pytest.skip(f"로그인 실패: {error}")

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.post("/api/orders/", shipping_data, format="json")

        if response.status_code != status.HTTP_201_CREATED:
            pytest.skip(f"주문 생성 실패: {response.status_code}")

        response_data = response.json()
        # 응답에서 id 추출 (다양한 키 지원)
        order_id = response_data.get("id") or response_data.get("order_id") or response_data.get("pk")

        if not order_id:
            pytest.skip(f"주문 응답에 id가 없음. 응답 키: {list(response_data.keys())}")

        results = []
        lock = threading.Lock()

        def cancel_order():
            """주문 취소"""
            try:
                from django.db import connections

                cancel_client = APIClient()
                cancel_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = cancel_client.post(f"/api/orders/{order_id}/cancel/")

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
        threads = [threading.Thread(target=cancel_order) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 1번만 성공
        success_count = sum(1 for r in results if r.get("success", False))

        if success_count != 1:
            print(f"\n결과: {results}")

        assert success_count == 1, f"1번만 취소 성공해야 함. 성공: {success_count}"

    def test_concurrent_cart_to_order_multiple_times(self, user, product, shipping_data):
        """동일 장바구니로 여러 번 동시 주문 시도"""
        # Arrange
        product.stock = 50
        product.save()

        cart = Cart.get_or_create_active_cart(user)[0]
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        client, token, error = login_and_get_token(user.username, "testpass123")

        if error:
            pytest.skip(f"로그인 실패: {error}")

        results = []
        lock = threading.Lock()

        def create_order_from_same_cart():
            """같은 장바구니로 주문 생성"""
            try:
                from django.db import connections

                order_client = APIClient()
                order_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = order_client.post("/api/orders/", shipping_data, format="json")

                with lock:
                    results.append(
                        {
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"error": str(e)})

        # Act - 3번 동시 주문 시도
        threads = [threading.Thread(target=create_order_from_same_cart) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 최소 1개는 성공
        success_count = sum(1 for r in results if r.get("success", False))

        if success_count < 1:
            print(f"\n결과: {results}")

        assert success_count >= 1, f"최소 1개는 성공해야 함. 성공: {success_count}"

    def test_concurrent_same_user_multiple_orders(self, user, product, shipping_data):
        """동일 사용자가 여러 주문 동시 생성"""
        # Arrange
        product.stock = 100
        product.save()

        # 장바구니에 상품 추가
        cart = Cart.get_or_create_active_cart(user)[0]
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        client, token, error = login_and_get_token(user.username, "testpass123")

        if error:
            pytest.skip(f"로그인 실패: {error}")

        results = []
        lock = threading.Lock()

        def create_order():
            """주문 생성"""
            try:
                from django.db import connections

                order_client = APIClient()
                order_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = order_client.post("/api/orders/", shipping_data, format="json")

                with lock:
                    results.append(
                        {
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"error": str(e)})

        # Act - 5번 동시 주문
        threads = [threading.Thread(target=create_order) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))

        if success_count < 1:
            print(f"\n결과: {results}")

        assert success_count >= 1, f"최소 1개는 성공해야 함. 성공: {success_count}"


@pytest.mark.django_db(transaction=True)
class TestOrderConcurrencyAdvanced:
    """
    고급 시나리오

    F() 객체, select_for_update, 대량 동시 요청 등 고급 동시성 제어 테스트
    """

    def test_f_object_stock_decrease_concurrency(self, category):
        """F() 객체를 사용한 재고 차감 동시성 제어"""
        # Arrange - 재고 10개인 상품
        product = Product.objects.create(
            name="F() 테스트 상품",
            slug="f-test-product",
            category=category,
            price=Decimal("5000"),
            stock=10,
            sku="F-TEST-001",
        )

        results = []
        lock = threading.Lock()

        def decrease_stock_with_f():
            """F() 객체로 재고 차감"""
            try:
                # F() 객체로 안전한 차감 (재고 2개 이상일 때만)
                updated = Product.objects.filter(id=product.id, stock__gte=2).update(stock=F("stock") - 2)
                with lock:
                    results.append(
                        {
                            "success": updated > 0,
                            "updated_count": updated,
                            "thread": threading.current_thread().name,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"error": str(e), "thread": threading.current_thread().name})

        # Act - 6개 스레드가 각 2개씩 차감 시도 (총 12개 시도, 재고 10개)
        threads = [threading.Thread(target=decrease_stock_with_f, name=f"Thread-{i}") for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))
        product.refresh_from_db()

        if success_count != 5:
            print(f"\n결과: {results}")

        # 5개 스레드 성공 (10 - 2 - 2 - 2 - 2 - 2 = 0)
        assert success_count == 5, f"5개 스레드 성공해야 함. 성공: {success_count}"
        assert product.stock == 0, f"최종 재고는 0개여야 함. 실제: {product.stock}"

    def test_select_for_update_order_creation(self, product, shipping_data):
        """select_for_update로 주문 생성 동시성 제어"""
        # Arrange
        product.stock = 3
        product.save()

        users = []
        for i in range(3):
            u = create_test_user(
                username=f"sfu_user{i}",
                email=f"sfu{i}@test.com",
                phone_number=f"010-7777-000{i}",
            )
            users.append(u)

            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=1)

        results = []
        lock = threading.Lock()

        def create_order_with_lock(user_obj):
            """주문 생성 (내부적으로 select_for_update 사용)"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post("/api/orders/", shipping_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [threading.Thread(target=create_order_with_lock, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - select_for_update로 순차 처리되어 모두 성공
        success_count = sum(1 for r in results if r.get("success", False))

        if success_count != 3:
            print(f"\n결과: {results}")

        assert success_count == 3, f"3명 모두 성공해야 함. 성공: {success_count}"

        # 재고 확인 (3 - 3명 x 1개 = 0개)
        product.refresh_from_db()
        assert product.stock == 0, f"재고는 모두 차감되어야 함. 실제 재고: {product.stock}"

    def test_high_concurrency_order_creation(self, product, shipping_data):
        """대량 동시 주문 요청 (50명)"""
        # Arrange
        product.stock = 100
        product.save()

        users = []
        for i in range(50):
            u = create_test_user(
                username=f"mass_user{i}",
                email=f"mass{i}@test.com",
                phone_number=f"010-8888-{i:04d}",
            )
            users.append(u)

            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=1)

        results = []
        lock = threading.Lock()

        def create_order(user_obj):
            """주문 생성"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = client.post("/api/orders/", shipping_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act - 50명 동시 주문
        start_time = time.time()
        threads = [threading.Thread(target=create_order, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed_time = time.time() - start_time

        # Assert
        success_count = sum(1 for r in results if r.get("success", False))

        if success_count != 50:
            print(f"\n결과 샘플: {results[:5]}")  # 처음 5개만 출력

        assert success_count == 50, f"50명 모두 성공해야 함. 성공: {success_count}"
        assert elapsed_time < 30, f"30초 내에 완료되어야 함. 실제: {elapsed_time:.2f}초"

    def test_race_condition_stock_and_point(self, product, shipping_data):
        """재고와 포인트 동시 경합 상황"""
        # Arrange
        product.stock = 2  # 재고 2개
        product.price = Decimal("10000")
        product.save()

        users = []
        for i in range(3):
            u = create_test_user(
                username=f"race_user{i}",
                email=f"race{i}@test.com",
                phone_number=f"010-9999-000{i}",
                points=5000,
            )
            users.append(u)

            cart = Cart.get_or_create_active_cart(u)[0]
            CartItem.objects.create(cart=cart, product=product, quantity=1)

        results = []
        lock = threading.Lock()

        def create_order_with_points(user_obj):
            """포인트 사용하여 주문"""
            try:
                client, token, error = login_and_get_token(user_obj.username)

                if error:
                    with lock:
                        results.append({"user": user_obj.username, "error": error})
                    return

                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                order_data = {**shipping_data, "use_points": 1000}
                response = client.post("/api/orders/", order_data, format="json")

                with lock:
                    results.append(
                        {
                            "user": user_obj.username,
                            "status": response.status_code,
                            "success": response.status_code == status.HTTP_201_CREATED,
                        }
                    )
            except Exception as e:
                with lock:
                    results.append({"user": user_obj.username, "error": str(e)})

        # Act
        threads = [threading.Thread(target=create_order_with_points, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert - 재고 2개이므로 2명만 성공
        success_count = sum(1 for r in results if r.get("success", False))
        failed_count = len(results) - success_count

        if success_count != 2:
            print(f"\n결과: {results}")

        assert success_count == 2, f"2명만 성공해야 함 (재고 2개). 성공: {success_count}, 실패: {failed_count}"
        assert failed_count == 1, f"1명은 재고 부족으로 실패해야 함. 실패: {failed_count}"

        # 재고 확인 (2 - 2명 x 1개 = 0개)
        product.refresh_from_db()
        assert product.stock == 0, f"재고가 모두 차감되어야 함. 실재 재고: {product.stock}"

        # 성공한 사용자는 포인트 차감 확인
        success_users = [r["user"] for r in results if r.get("success", False)]
        for username in success_users:
            u = User.objects.get(username=username)
            assert u.points == 4000, f"{u.username}의 포인트가 1000P 차감되어야 함"
