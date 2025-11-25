"""
Locust 로드 테스트 - 메인 파일

실행 방법:
    locust -f shopping/tests/performance/locustfile.py --host=http://localhost:8000

웹 UI:
    http://localhost:8089
"""
from locust import HttpUser, task, between, SequentialTaskSet
import random
from decimal import Decimal


class UserBehavior(SequentialTaskSet):
    """사용자 행동 시나리오 (순차적)"""

    def on_start(self):
        """시나리오 시작 전 실행 (로그인)"""
        self.login()

    def login(self):
        """로그인"""
        response = self.client.post("/api/auth/login/", json={
            "username": f"load_test_user_{random.randint(1, 1000)}",
            "password": "testpass123"
        })
        if response.status_code == 200:
            self.token = response.json().get("access")
            self.client.headers.update({
                "Authorization": f"Bearer {self.token}"
            })

    @task
    def browse_products(self):
        """상품 목록 조회"""
        self.client.get("/api/products/")

    @task
    def view_product_detail(self):
        """상품 상세 조회"""
        product_id = random.randint(1, 100)
        self.client.get(f"/api/products/{product_id}/")

    @task
    def add_to_cart(self):
        """장바구니 추가"""
        self.client.post("/api/cart/items/", json={
            "product": random.randint(1, 100),
            "quantity": 1
        })

    @task
    def create_order(self):
        """주문 생성"""
        self.client.post("/api/orders/", json={
            "shipping_name": "테스트",
            "shipping_phone": "010-1234-5678",
            "shipping_postal_code": "12345",
            "shipping_address": "서울시 강남구",
            "shipping_address_detail": "101호"
        })

    @task
    def confirm_payment(self):
        """결제 승인"""
        # 실제 시나리오에서는 order_id를 이전 단계에서 받아야 함
        self.client.post("/api/payments/confirm/", json={
            "payment_key": f"test_key_{random.randint(1, 10000)}",
            "order_id": f"ORDER_{random.randint(1, 10000)}",
            "amount": 13000
        })


class WebsiteUser(HttpUser):
    """웹사이트 사용자"""
    tasks = [UserBehavior]
    wait_time = between(1, 5)  # 요청 간 1~5초 대기

    # 호스트는 실행 시 --host 옵션으로 지정
    # 또는 여기서 기본값 설정:
    # host = "http://localhost:8000"
