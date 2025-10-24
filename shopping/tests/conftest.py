from decimal import Decimal

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

from shopping.models.cart import Cart, CartItem
from shopping.models.product import Category, Product
from shopping.models.user import User


# ==========================================
# 1. 전역 설정 (Session Scope)
# ==========================================


@pytest.fixture(scope="session", autouse=True)
def setup_celery_for_tests():
    """
    테스트 환경에서 Celery 동기 실행 설정

    Session scope: 전체 테스트 세션에서 한 번만 실행
    autouse: 자동으로 모든 테스트에 적용
    """
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """
    데이터베이스 초기 설정

    PostgreSQL 환경에서 테스트 DB 설정 최적화
    Session scope로 DB 연결 비용 최소화
    """
    with django_db_blocker.unblock():
        # 필요한 경우 초기 데이터 설정
        pass


# ==========================================
# 2. API 클라이언트 Fixture
# ==========================================


@pytest.fixture
def api_client():
    """
    DRF APIClient 인스턴스

    REST API 테스트용 클라이언트
    Function scope: 매 테스트마다 새로운 클라이언트 생성
    """
    return APIClient()


# ==========================================
# 3. 사용자(User) Fixture
# ==========================================


@pytest.fixture
def user(db):
    """
    기본 일반 사용자 (이메일 인증 완료)

    - username: testuser
    - 포인트: 5000
    - 이메일 인증: 완료
    """
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
        phone_number="010-1234-5678",
        points=5000,
        is_email_verified=True,
    )


@pytest.fixture
def seller_user(db):
    """
    판매자 사용자

    상품 등록/관리 권한을 가진 사용자
    """
    return User.objects.create_user(
        username="seller",
        email="seller@example.com",
        password="sellerpass123",
        phone_number="010-9999-8888",
        is_email_verified=True,
    )


@pytest.fixture
def unverified_user(db):
    """
    이메일 미인증 사용자

    결제 등 일부 기능 사용 제한
    """
    return User.objects.create_user(
        username="unverified",
        email="unverified@example.com",
        password="testpass123",
        is_email_verified=False,
    )


@pytest.fixture
def user_factory(db):
    """
    User Factory - 유연한 사용자 생성

    사용 예시:
        user1 = user_factory()  # 기본값
        user2 = user_factory(username="custom", points=10000)  # 커스텀
        user3 = user_factory(is_email_verified=False)  # 미인증
    """

    def _create_user(**kwargs):
        defaults = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "phone_number": "010-1234-5678",
            "points": 5000,
            "is_email_verified": True,
        }
        # kwargs로 받은 값으로 defaults 덮어쓰기
        defaults.update(kwargs)

        # username이 중복될 수 있으므로 카운터 추가
        username = defaults.pop("username")
        counter = 1
        original_username = username
        while User.objects.filter(username=username).exists():
            username = f"{original_username}{counter}"
            counter += 1

        return User.objects.create_user(username=username, **defaults)

    return _create_user


# ==========================================
# 4. 인증 관련 Fixture
# ==========================================


@pytest.fixture
def authenticated_client(api_client, user):
    """
    인증된 APIClient (가장 많이 사용)

    JWT 토큰이 설정된 클라이언트
    대부분의 API 테스트에서 사용
    """
    response = api_client.post(
        reverse("auth-login"),
        {"username": "testuser", "password": "testpass123"},
    )
    token = response.json()["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def seller_authenticated_client(api_client, seller_user):
    """
    판매자 인증 클라이언트

    상품 등록/관리 API 테스트용
    """
    response = api_client.post(
        reverse("auth-login"),
        {"username": "seller", "password": "sellerpass123"},
    )
    token = response.json()["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


# ==========================================
# 5. 카테고리/상품 Fixture
# ==========================================


@pytest.fixture
def category(db):
    """
    기본 카테고리

    대부분의 상품 테스트에서 사용
    """
    return Category.objects.create(
        name="테스트 카테고리",
        slug="test-category",
    )


@pytest.fixture
def product(db, category, seller_user):
    """
    기본 테스트 상품 (재고 있음)

    - 가격: 10,000원
    - 재고: 10개
    - 판매중
    """
    return Product.objects.create(
        name="테스트 상품",
        slug="test-product",
        category=category,
        seller=seller_user,
        price=Decimal("10000"),
        stock=10,
        sku="TEST-001",
        description="테스트 상품 설명",
        is_active=True,
    )


@pytest.fixture
def out_of_stock_product(db, category, seller_user):
    """
    품절 상품

    재고 부족 시나리오 테스트용
    """
    return Product.objects.create(
        name="품절 상품",
        slug="out-of-stock",
        category=category,
        seller=seller_user,
        price=Decimal("5000"),
        stock=0,  # 품절
        sku="TEST-003",
        is_active=True,
    )


@pytest.fixture
def inactive_product(db, category, seller_user):
    """
    판매 중단 상품

    비활성 상품 테스트용
    """
    return Product.objects.create(
        name="판매중단 상품",
        slug="inactive-product",
        category=category,
        seller=seller_user,
        price=Decimal("15000"),
        stock=10,
        sku="TEST-004",
        is_active=False,  # 판매 중단
    )


@pytest.fixture
def product_factory(db, category, seller_user):
    """
    Product Factory - 유연한 상품 생성

    사용 예시:
        product1 = product_factory()  # 기본값
        product2 = product_factory(price=Decimal("20000"), stock=5)
        product3 = product_factory(name="커스텀 상품", sku="CUSTOM-001")
    """

    def _create_product(**kwargs):
        defaults = {
            "name": "테스트 상품",
            "slug": "test-product",
            "category": category,
            "seller": seller_user,
            "price": Decimal("10000"),
            "stock": 10,
            "sku": "TEST-001",
            "description": "테스트 상품 설명",
            "is_active": True,
        }
        defaults.update(kwargs)

        # slug 중복 방지
        slug = defaults.pop("slug")
        counter = 1
        original_slug = slug
        while Product.objects.filter(slug=slug).exists():
            slug = f"{original_slug}-{counter}"
            counter += 1

        return Product.objects.create(slug=slug, **defaults)

    return _create_product


@pytest.fixture
def multiple_products(db, category, seller_user):
    """
    여러 상품 (리스트 테스트용)

    3개의 상품 리스트 반환
    가격: 10,000 / 20,000 / 30,000
    """
    return [
        Product.objects.create(
            name=f"상품 {i}",
            slug=f"product-{i}",
            category=category,
            seller=seller_user,
            price=Decimal(str(10000 * i)),
            stock=10,
            sku=f"MULTI-{i:03d}",
            is_active=True,
        )
        for i in range(1, 4)
    ]


# ==========================================
# 6. 장바구니/주문 Fixture
# ==========================================


@pytest.fixture
def cart(db, user):
    """
    빈 장바구니

    활성 상태의 빈 장바구니
    """
    return Cart.objects.create(user=user, is_active=True)


@pytest.fixture
def cart_with_items(db, user, product):
    """
    상품이 담긴 장바구니

    기본 상품 1개가 담긴 장바구니
    """
    cart = Cart.objects.create(user=user, is_active=True)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    return cart


@pytest.fixture
def shipping_data():
    """
    기본 배송 정보 (dict)

    주문 생성 시 사용하는 배송 정보
    """
    return {
        "shipping_name": "홍길동",
        "shipping_phone": "010-9999-8888",
        "shipping_postal_code": "12345",
        "shipping_address": "서울시 강남구 테스트로 123",
        "shipping_address_detail": "101동 202호",
        "order_memo": "부재시 경비실에 맡겨주세요",
    }


# ==========================================
# 7. 결제 관련 Fixture (Mock)
# ==========================================


@pytest.fixture
def mock_toss_payment_success():
    """
    토스 결제 성공 Mock 데이터

    정상적인 결제 승인 응답 데이터
    """
    return {
        "paymentKey": "test_payment_key_123",
        "orderId": "test_order_123",
        "status": "DONE",
        "totalAmount": 13000,
        "method": "카드",
        "approvedAt": "2025-01-15T10:00:00+09:00",
        "card": {
            "company": "신한카드",
            "number": "1234****",
            "installmentPlanMonths": 0,
            "isInterestFree": False,
        },
    }


@pytest.fixture
def mock_toss_payment_failed():
    """
    토스 결제 실패 Mock 데이터

    결제 실패 응답 데이터
    """
    return {
        "code": "PAY_PROCESS_CANCELED",
        "message": "사용자에 의해 결제가 취소되었습니다",
    }


@pytest.fixture
def mock_toss_client(mocker):
    """
    토스 API Mock 클라이언트 (pytest-mock 사용)

    실제 토스 API 호출을 대체하는 Mock 객체

    사용 예시:
        def test_payment(mock_toss_client):
            mock_toss_client.confirm_payment.return_value = {...}
            # 테스트 코드
    """
    mock = mocker.patch("shopping.utils.toss_payment.TossPaymentClient")
    return mock.return_value


# ==========================================
# 8. 기타 유틸리티 Fixture
# ==========================================


@pytest.fixture
def freeze_time(mocker):
    """
    시간 고정 유틸리티

    시간 의존적인 테스트에 사용

    사용 예시:
        def test_with_time(freeze_time):
            frozen_time = datetime(2025, 1, 15, 10, 0, 0)
            freeze_time(frozen_time)
            # 테스트 코드
    """
    from django.utils import timezone

    def _freeze(dt):
        return mocker.patch("django.utils.timezone.now", return_value=dt)

    return _freeze


# ==========================================
# 9. 주문/결제 Fixture (Order/Payment)
# ==========================================


@pytest.fixture
def order(db, user, product):
    """
    기본 주문 (pending 상태)

    - 상태: pending (결제 대기)
    - 상품 1개 포함
    """
    from shopping.models.order import Order, OrderItem

    order = Order.objects.create(
        user=user,
        status="pending",
        total_amount=product.price,
        shipping_name="홍길동",
        shipping_phone="010-9999-8888",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=1,
        price=product.price,
    )

    return order


@pytest.fixture
def paid_order(db, user, product):
    """
    결제 완료된 주문

    - 상태: paid (결제 완료)
    - 상품 1개 포함
    """
    from shopping.models.order import Order, OrderItem

    order = Order.objects.create(
        user=user,
        status="paid",
        total_amount=product.price,
        payment_method="card",
        shipping_name="홍길동",
        shipping_phone="010-9999-8888",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=1,
        price=product.price,
    )

    return order


@pytest.fixture
def order_with_multiple_items(db, user, multiple_products):
    """
    여러 상품이 포함된 주문

    - 상품 3개 포함
    - 총 금액: 60,000원 (10,000 + 20,000 + 30,000)
    """
    from shopping.models.order import Order, OrderItem

    total = sum(p.price for p in multiple_products)

    order = Order.objects.create(
        user=user,
        status="pending",
        total_amount=total,
        shipping_name="홍길동",
        shipping_phone="010-9999-8888",
        shipping_postal_code="12345",
        shipping_address="서울시 강남구 테스트로 123",
        shipping_address_detail="101동 202호",
    )

    for product in multiple_products:
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=1,
            price=product.price,
        )

    return order


@pytest.fixture
def payment(db, order):
    """
    기본 결제 (pending 상태)

    - 상태: pending (결제 대기)
    - 주문과 연결됨
    """
    from shopping.models.payment import Payment

    return Payment.objects.create(
        order=order,
        amount=order.total_amount,
        status="pending",
        toss_order_id=order.order_number,
    )


@pytest.fixture
def paid_payment(db, paid_order):
    """
    결제 완료된 Payment

    - 상태: done (결제 완료)
    - 토스 결제 정보 포함
    """
    from shopping.models.payment import Payment
    from django.utils import timezone

    return Payment.objects.create(
        order=paid_order,
        amount=paid_order.total_amount,
        status="done",
        toss_order_id=paid_order.order_number,
        payment_key="test_payment_key_123",
        method="카드",
        approved_at=timezone.now(),
        card_company="신한카드",
        card_number="1234****",
    )


@pytest.fixture
def canceled_payment(db, order):
    """
    취소된 결제

    - 상태: canceled (취소됨)
    """
    from shopping.models.payment import Payment
    from django.utils import timezone

    return Payment.objects.create(
        order=order,
        amount=order.total_amount,
        status="canceled",
        is_canceled=True,
        toss_order_id=order.order_number,
        payment_key="test_payment_key_canceled",
        canceled_at=timezone.now(),
        cancel_reason="사용자 요청",
    )


@pytest.fixture
def payment_factory(db):
    """
    Payment Factory - 유연한 결제 생성

    사용 예시:
        payment1 = payment_factory(order=order)  # 기본값
        payment2 = payment_factory(order=order, status="done", payment_key="key123")
    """
    from shopping.models.payment import Payment

    def _create_payment(order, **kwargs):
        defaults = {
            "amount": order.total_amount,
            "status": "pending",
            "toss_order_id": order.order_number,
        }
        defaults.update(kwargs)

        return Payment.objects.create(order=order, **defaults)

    return _create_payment
