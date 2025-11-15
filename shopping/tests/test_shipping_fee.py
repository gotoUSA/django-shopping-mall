from decimal import Decimal

from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from shopping.models import Cart, CartItem, Category, Order, Product, User
from shopping.services.shipping_service import ShippingService


class ShippingFeeTestCase(TestCase):
    """배송비 계산 기본 테스트 (ShippingService)"""

    def test_shipping_fee_under_threshold(self):
        """무료배송 기준 미만 주문 테스트 (3만원 미만)"""
        result = ShippingService.calculate_fee(
            total_amount=Decimal("25000"),
            postal_code="12345"
        )

        # 검증
        self.assertEqual(result["shipping_fee"], Decimal("3000"))
        self.assertEqual(result["additional_fee"], Decimal("0"))
        self.assertFalse(result["is_free_shipping"])

    def test_free_shipping_over_threshold(self):
        """무료배송 기준 이상 주문 테스트 (3만원 이상)"""
        result = ShippingService.calculate_fee(
            total_amount=Decimal("35000"),
            postal_code="12345"
        )

        # 검증
        self.assertEqual(result["shipping_fee"], Decimal("0"))
        self.assertEqual(result["additional_fee"], Decimal("0"))
        self.assertTrue(result["is_free_shipping"])

    def test_remote_area_additional_fee(self):
        """도서산간 지역 추가 배송비 테스트"""
        result = ShippingService.calculate_fee(
            total_amount=Decimal("25000"),
            postal_code="63000"  # 제주
        )

        # 검증: 기본 배송비 3000 + 추가 3000 = 6000
        self.assertEqual(result["shipping_fee"], Decimal("3000"))
        self.assertEqual(result["additional_fee"], Decimal("3000"))
        self.assertFalse(result["is_free_shipping"])

    def test_remote_area_free_shipping(self):
        """도서산간 지역 무료배송 테스트 (기본 배송비는 무료, 추가비만 부과)"""
        result = ShippingService.calculate_fee(
            total_amount=Decimal("35000"),
            postal_code="63000"  # 제주
        )

        # 검증: 무료배송이지만 도서산간 추가비는 받음
        self.assertEqual(result["shipping_fee"], Decimal("0"))
        self.assertEqual(result["additional_fee"], Decimal("3000"))
        self.assertTrue(result["is_free_shipping"])

    def test_is_remote_area(self):
        """도서산간 지역 판별 테스트"""
        # 제주
        self.assertTrue(ShippingService.is_remote_area("63000"))
        self.assertTrue(ShippingService.is_remote_area("63999"))

        # 울릉도
        self.assertTrue(ShippingService.is_remote_area("59000"))

        # 일반 지역
        self.assertFalse(ShippingService.is_remote_area("12345"))
        self.assertFalse(ShippingService.is_remote_area("06000"))

        # 빈 우편번호
        self.assertFalse(ShippingService.is_remote_area(""))


class OrderCreateWithShippingFeeTest(TransactionTestCase):
    """주문 생성 API에서 배송비 자동 적용 테스트"""

    def setUp(self):
        """테스트 데이터 설정"""
        self.client = APIClient()

        # 테스트 사용자
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            points=5000,
            is_email_verified=True,
        )

        # 로그인
        self.client.force_authenticate(user=self.user)

        # 카테고리 및 상품 생성
        self.category = Category.objects.create(name="테스트 카테고리", slug="test-category")

        self.product = Product.objects.create(
            name="테스트 상품",
            slug="test-product",
            category=self.category,
            price=Decimal("20000"),
            stock=10,
            sku="TEST-001",
        )

        # 장바구니 생성 및 상품 추가
        self.cart = Cart.objects.create(user=self.user, is_active=True)
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)  # 20,000원 (무료배송 미달)

    def test_order_create_with_shipping_fee(self):
        """주문 생성시 배송비 자동 적용 테스트"""
        # 주문 생성 요청 데이터
        order_data = {
            "shipping_name": "홍길동",
            "shipping_phone": "010-9999-8888",
            "shipping_postal_code": "12345",
            "shipping_address": "서울시 강남구 테스트로 123",
            "shipping_address_detail": "101동 202호",
            "order_memo": "부재시 경비실에 맡겨주세요",
            "use_points": 0,
        }

        # 주문 생성 API 호출
        response = self.client.post(reverse("order-list"), data=order_data, format="json")

        # 응답 확인
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 생성된 주문 확인
        order = Order.objects.get(user=self.user)

        # 배송비 적용 확인
        self.assertEqual(order.total_amount, Decimal("20000"))
        self.assertEqual(order.shipping_fee, Decimal("3000"))
        self.assertEqual(order.additional_shipping_fee, Decimal("0"))
        self.assertFalse(order.is_free_shipping)
        self.assertEqual(order.final_amount, Decimal("23000"))  # 20000 + 3000

    def test_order_create_remote_area(self):
        """제주 지역 주문 생성시 추가 배송비 테스트"""
        # 주문 생성 요청 데이터 (제주 우편번호)
        order_data = {
            "shipping_name": "홍길동",
            "shipping_phone": "010-9999-8888",
            "shipping_postal_code": "63000",  # 제주
            "shipping_address": "제주시 테스트로 123",
            "shipping_address_detail": "101호",
            "order_memo": "부재시 경비실에 맡겨주세요",
            "use_points": 0,
        }

        # 주문 생성 API 호출
        response = self.client.post(reverse("order-list"), data=order_data, format="json")

        # 응답 확인
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 생성된 주문 확인
        order = Order.objects.get(user=self.user)

        # 도서산간 배송비 적용 확인
        self.assertEqual(order.total_amount, Decimal("20000"))
        self.assertEqual(order.shipping_fee, Decimal("3000"))
        self.assertEqual(order.additional_shipping_fee, Decimal("3000"))
        self.assertFalse(order.is_free_shipping)
        self.assertEqual(order.final_amount, Decimal("26000"))  # 20000 + 3000 + 3000

    def test_order_create_free_shipping(self):
        """무료배송 금액 달성시 테스트"""
        # 두 번째 상품 생성 (무료배송 금액 달성용)
        product2 = Product.objects.create(
            name="테스트 상품2",
            slug="test-product-2",
            category=self.category,
            price=Decimal("20000"),
            stock=10,
            sku="TEST-002",
        )

        # 장바구니에 상품 추가 (총 40,000원)
        CartItem.objects.create(cart=self.cart, product=product2, quantity=1)  # 추가 20,000원

        # 주문 생성 요청 데이터
        order_data = {
            "shipping_name": "홍길동",
            "shipping_phone": "010-9999-8888",
            "shipping_postal_code": "12345",
            "shipping_address": "서울시 강남구 테스트로 123",
            "shipping_address_detail": "101동 202호",
            "order_memo": "부재시 경비실에 맡겨주세요",
            "use_points": 0,
        }

        # 주문 생성 API 호출
        response = self.client.post(reverse("order-list"), data=order_data, format="json")

        # 응답 확인
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 생성된 주문 확인
        order = Order.objects.get(user=self.user)

        # 무료배송 확인
        self.assertEqual(order.total_amount, Decimal("40000"))
        self.assertEqual(order.shipping_fee, Decimal("0"))
        self.assertEqual(order.additional_shipping_fee, Decimal("0"))
        self.assertTrue(order.is_free_shipping)
        self.assertEqual(order.final_amount, Decimal("40000"))
