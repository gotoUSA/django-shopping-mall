"""
Locust 로드 테스트 - 메인 파일

실행 방법:
    locust -f shopping/tests/performance/locustfile.py --host=http://localhost:8000

웹 UI:
    http://localhost:8089
"""
from locust import HttpUser, task, between, SequentialTaskSet
import random


class UserBehavior(SequentialTaskSet):
    """
    사용자 행동 시나리오 (순차적)

    SequentialTaskSet은 tasks를 위에서 아래 순서로 실행합니다.
    각 사이클마다: 상세보기 -> 장바구니 추가 -> 주문 생성 -> 결제 -> 다시 처음부터
    """

    def on_start(self):
        """시나리오 시작 전 실행 (로그인 및 초기화)"""
        # ✅ setup_test_data.py로 생성된 상품 ID 범위 (성능테스트 상품 0~99)
        # API 호출 없이 직접 ID 범위 사용 (페이지네이션 문제 해결)
        self.fetch_all_product_ids()
        self.cart_item_ids = []  # 장바구니 아이템 ID 저장
        self.order_id = None  # 생성된 주문 ID 저장
        self.payment_key = None  # 결제 키 저장
        self.login()

    def fetch_all_product_ids(self):
        """모든 상품 ID 가져오기 (실제 페이지네이션 사용)"""
        self.product_ids = []

        # 실제 프로덕션과 동일하게 12개씩 페이지네이션
        page = 1
        while True:
            response = self.client.get(f"/api/products/?page={page}")
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if results:
                    self.product_ids.extend([p["id"] for p in results])
                    # 다음 페이지가 없으면 종료
                    if not data.get("next"):
                        break
                    page += 1
                else:
                    break
            else:
                print(f"⚠️  상품 목록 조회 실패: status={response.status_code}")
                break

        if not self.product_ids:
            print("⚠️  상품 ID 조회 실패")

    def login(self):
        """로그인"""
        # 테스트 데이터로 생성한 사용자 (load_test_user_0 ~ load_test_user_999)
        user_id = random.randint(0, 999)
        response = self.client.post("/api/auth/login/", json={
            "username": f"load_test_user_{user_id}",
            "password": "testpass123"
        })
        if response.status_code == 200:
            self.token = response.json().get("access")
            self.client.headers.update({
                "Authorization": f"Bearer {self.token}"
            })

    @task
    def step1_view_product_detail(self):
        """1단계: 상품 상세 조회"""
        if self.product_ids:
            product_id = random.choice(self.product_ids)
            self.client.get(f"/api/products/{product_id}/")

    @task
    def step2_add_to_cart(self):
        """2단계: 장바구니에 상품 추가 (2~3개)"""
        # 여러 개 상품을 장바구니에 추가
        num_items = random.randint(2, 3)

        for _ in range(num_items):
            if self.product_ids:
                # ✅ 100개 상품을 균등하게 사용
                product_id = random.choice(self.product_ids)

                response = self.client.post("/api/cart-items/", json={
                    "product_id": product_id,
                    "quantity": random.randint(1, 2)
                })

                # 장바구니 아이템 ID 저장
                if response.status_code == 201:
                    cart_item = response.json()
                    if "id" in cart_item:
                        self.cart_item_ids.append(cart_item["id"])
                else:
                    print(f"❌ 장바구니 추가 실패: status={response.status_code}, product_id={product_id}")
                    print(f"   Response: {response.text[:200]}")

    @task
    def step3_create_order(self):
        """3단계: 주문 생성"""
        # 장바구니가 비어있으면 에러가 나므로, 비어있는 경우 다시 추가
        if not self.cart_item_ids:
            print(f"⚠️  장바구니 비어있음, 재추가 시도")
            self.step2_add_to_cart()

        # 여전히 비어있으면 건너뛰기
        if not self.cart_item_ids:
            print(f"❌ 장바구니 추가 실패로 주문 생성 스킵")
            return

        response = self.client.post("/api/orders/", json={
            "shipping_name": "테스트",
            "shipping_phone": "010-1234-5678",
            "shipping_postal_code": "12345",
            "shipping_address": "서울시 강남구",
            "shipping_address_detail": "101호"
        })

        # 생성된 주문 ID 저장 (결제 시 사용)
        # 201 Created (동기) 또는 202 Accepted (하이브리드 비동기) 모두 성공
        if response.status_code in [201, 202]:
            order = response.json()
            self.order_id = order.get("order_id")
            # 주문 생성하면 장바구니는 비워짐
            self.cart_item_ids = []
        else:
            print(f"❌ 주문 생성 실패: status={response.status_code}")
            print(f"   Cart items: {len(self.cart_item_ids)} items")
            print(f"   Response: {response.text[:300]}")

    @task
    def step4_confirm_payment(self):
        """4단계: 결제 승인"""
        # 주문이 없으면 건너뛰기 (이전 단계 실패 시)
        if not self.order_id:
            return

        # 고유한 payment_key 생성 (중복 방지)
        import time
        payment_key = f"test_key_{int(time.time() * 1000)}_{random.randint(1, 100000)}"

        response = self.client.post("/api/payments/confirm/", json={
            "payment_key": payment_key,
            "order_id": self.order_id,
            "amount": 13000  # 실제로는 주문 금액을 사용해야 함
        })

        # 결제 완료 후 order_id 초기화
        if response.status_code in [200, 202]:
            self.order_id = None

        # ✅ 사이클 완료! 다음 사이클은 step1부터 다시 시작


class WebsiteUser(HttpUser):
    """웹사이트 사용자"""
    tasks = [UserBehavior]
    wait_time = between(1, 5)  # 요청 간 1~5초 대기

    # 호스트는 실행 시 --host 옵션으로 지정
    # 또는 여기서 기본값 설정:
    # host = "http://localhost:8000"
