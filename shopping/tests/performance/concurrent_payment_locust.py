"""
500명 동시 결제 승인 테스트용 Locust 스크립트

사용법:
    locust -f concurrent_payment_locust.py --host=http://localhost:8000 --headless -u 500 -r 50 -t 60s

설명:
    -u 500: 500명의 동시 사용자
    -r 50: 초당 50명씩 동시 시작
    -t 60s: 60초간 실행

전제조건:
    - setup_test_data.py로 테스트 데이터 미리 생성 필요
    - Django 서버가 http://localhost:8000 에서 실행 중이어야 함
"""

import random
import time

from locust import HttpUser, between, events, task


class ConcurrentPaymentUser(HttpUser):
    """500명 동시 결제 승인 시도"""

    wait_time = between(0, 0)  # 대기 없이 즉시 실행

    # 전역 카운터 (모든 사용자가 공유)
    payment_attempts = []

    def on_start(self):
        """각 사용자 시작 시 로그인 및 주문/결제 생성"""
        # 고유한 사용자 생성
        timestamp = int(time.time() * 1000)
        user_id = id(self)

        # 미리 생성된 사용자 사용
        self.user_id = random.randint(0, 999)
        self.username = f"load_test_user_{self.user_id}"
        self.password = "testpass123"

        # 로그인
        login_response = self.client.post(
            "/api/auth/login/",
            json={"username": self.username, "password": self.password},
            name="/api/auth/login/",
        )

        if login_response.status_code != 200:
            self.login_error = f"Login failed: {login_response.status_code}"
            return

        self.access_token = login_response.json().get("access")

        # 장바구니에 상품 추가 (product_id=1 사용, 미리 생성되어 있어야 함)
        cart_response = self.client.post(
            "/api/cart-items/",
            json={"product_id": 1, "quantity": 1},
            headers={"Authorization": f"Bearer {self.access_token}"},
            name="/api/cart-items/",
        )

        if cart_response.status_code not in [200, 201]:
            self.cart_error = f"Cart add failed: {cart_response.status_code}"
            return

        # 주문 생성
        order_response = self.client.post(
            "/api/orders/",
            json={
                "shipping_name": f"테스트유저{self.user_id}",
                "shipping_phone": f"010-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                "shipping_postal_code": "12345",
                "shipping_address": "서울시 강남구",
                "shipping_address_detail": "101동",
            },
            headers={"Authorization": f"Bearer {self.access_token}"},
            name="/api/orders/",
        )

        if order_response.status_code != 202:
            self.order_error = f"Order create failed: {order_response.status_code}"
            return

        self.order_id = order_response.json().get("order_id")
        time.sleep(1)  # 주문 처리 대기

        # 결제 요청
        payment_request_response = self.client.post(
            "/api/payments/request/",
            json={"order_id": self.order_id},
            headers={"Authorization": f"Bearer {self.access_token}"},
            name="/api/payments/request/",
        )

        if payment_request_response.status_code != 201:
            self.payment_request_error = f"Payment request failed: {payment_request_response.status_code}"
            return

        payment_data = payment_request_response.json()
        self.payment_id = payment_data.get("payment_id")
        self.order_number = payment_data.get("order_id")
        self.amount = payment_data.get("amount")

    @task
    def confirm_payment(self):
        """결제 승인 시도"""
        if not hasattr(self, "access_token") or not hasattr(self, "payment_id"):
            # 준비 실패 시 건너뛰기
            result = {
                "username": getattr(self, "username", "unknown"),
                "success": False,
                "error": getattr(self, "register_error", None)
                        or getattr(self, "login_error", None)
                        or getattr(self, "cart_error", None)
                        or getattr(self, "order_error", None)
                        or getattr(self, "payment_request_error", None)
                        or "Setup failed",
                "timestamp": time.time(),
            }
            self.__class__.payment_attempts.append(result)
            self.environment.runner.quit()
            return

        # 결제 승인
        response = self.client.post(
            "/api/payments/confirm/",
            json={
                "order_id": self.order_number,
                "payment_key": f"test_payment_{self.payment_id}",
                "amount": self.amount,
            },
            headers={"Authorization": f"Bearer {self.access_token}"},
            name="/api/payments/confirm/",
        )

        # 결과 기록
        result = {
            "username": self.username,
            "status_code": response.status_code,
            "timestamp": time.time(),
        }

        if response.status_code == 202:
            result["success"] = True
            result["message"] = "✅ 202 Accepted - 성공"
        else:
            result["success"] = False
            result["message"] = f"❌ {response.status_code} - {response.text[:100]}"

        self.__class__.payment_attempts.append(result)

        # 한 번만 실행하고 종료
        self.environment.runner.quit()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """테스트 종료 시 결과 출력"""
    attempts = ConcurrentPaymentUser.payment_attempts

    print("\n" + "=" * 70)
    print("🔍 500명 동시 결제 승인 테스트 결과")
    print("=" * 70)

    success_count = sum(1 for a in attempts if a.get("success"))
    fail_count = len(attempts) - success_count
    setup_error_count = sum(1 for a in attempts if "error" in a and not a.get("status_code"))

    print(f"\n📊 총 시도: {len(attempts)}명")
    print(f"✅ 성공 (202): {success_count}명")
    print(f"❌ 실패: {fail_count}명")
    print(f"⚠️  준비 실패: {setup_error_count}명")

    # 샘플 출력 (처음 10개)
    print("\n📝 샘플 결과 (처음 10개):")
    for i, attempt in enumerate(attempts[:10], 1):
        status = "✅" if attempt.get("success") else "❌"
        msg = attempt.get("message", attempt.get("error", "Unknown"))
        print(f"{i}. {status} {attempt.get('username', 'unknown')} - {msg}")

    print("\n" + "=" * 70)
    print("🎯 예상 결과:")
    print("  - 성공: 500명 (202 Accepted)")
    print("  - 실패: 0명")
    print("=" * 70)

    # 검증
    if success_count == 500:
        print("\n✅ 테스트 통과! 500명 모두 성공했습니다.")
    elif success_count > 400:
        print(f"\n⚠️  대부분 성공: {success_count}/500 성공 ({success_count/500*100:.1f}%)")
    else:
        print(f"\n❌ 테스트 실패! 성공: {success_count}/500 ({success_count/500*100:.1f}%)")
