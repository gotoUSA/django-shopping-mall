# Locust 로드 테스트 도입 계획

> 다음 세션에서 이 파일을 참고하여 2단계부터 구현하세요.

## 배경

PostgreSQL "too many clients already" 에러를 해결하기 위해 성능 테스트(`test_concurrent_load.py`)를 작성했으나:
- pytest는 단위 테스트용으로 대규모 로드 테스트에 부적합
- DB Lock 데드락/타임아웃 발생 (9/10 실패)
- 동시성 테스트는 이미 `test_payment_concurrency.py`에 충분히 있음

**결론**: pytest 대신 Locust 로드 테스트 도구 도입

## 완료된 작업

- [x] 1단계: `shopping/tests/performance/test_concurrent_load.py` 삭제

## 2단계: Locust 설정 파일 생성

### 2-1. 디렉토리 구조

```
myproject/
├── performance/          # 새로 생성
│   ├── __init__.py
│   ├── locustfile.py    # 메인 시나리오
│   ├── scenarios/       # 시나리오별 분리
│   │   ├── __init__.py
│   │   ├── payment.py   # 결제 시나리오
│   │   ├── order.py     # 주문 시나리오
│   │   └── browse.py    # 상품 조회 시나리오
│   ├── setup_test_data.py  # 테스트 데이터 준비
│   └── README.md        # 실행 방법
└── docs/
    └── PERFORMANCE_TESTING.md  # 성능 테스트 가이드
```

### 2-2. Locust 설치

```bash
pip install locust
pip freeze > requirements.txt  # 의존성 업데이트
```

### 2-3. 메인 파일 작성: `performance/locustfile.py`

```python
"""Locust 로드 테스트 - 메인 파일

실행 방법:
    locust -f performance/locustfile.py --host=http://localhost:8000

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
```

### 2-4. 결제 시나리오 파일: `performance/scenarios/payment.py`

```python
"""결제 시나리오 - 대규모 동시 결제 테스트

목적: 1000명이 동시에 결제할 때 시스템 안정성 검증
"""
from locust import HttpUser, task, between
import random


class PaymentUser(HttpUser):
    """결제만 집중 테스트하는 사용자"""
    wait_time = between(0.1, 0.5)  # 빠른 요청 (부하 테스트)

    def on_start(self):
        """테스트 시작 전 로그인 및 주문 생성"""
        # 1. 로그인
        response = self.client.post("/api/auth/login/", json={
            "username": f"perf_user_{random.randint(1, 1000)}",
            "password": "testpass123"
        })
        if response.status_code == 200:
            self.token = response.json().get("access")
            self.client.headers.update({
                "Authorization": f"Bearer {self.token}"
            })

        # 2. 주문 생성 (미리 준비)
        # 실제로는 주문을 미리 생성해두고 시작하는 것이 좋음

    @task
    def concurrent_payment(self):
        """동시 결제 승인 요청"""
        self.client.post("/api/payments/confirm/", json={
            "payment_key": f"load_key_{random.randint(1, 100000)}",
            "order_id": f"ORDER_{random.randint(1, 10000)}",
            "amount": 13000
        }, name="/api/payments/confirm/ [Concurrent]")
```

### 2-5. README 작성: `performance/README.md`

```markdown
# 성능 테스트 가이드 (Locust)

## 설치

```bash
pip install locust
```

## 실행 방법

### 1. 웹 UI 모드 (개발용)

```bash
# Django 서버 실행 (터미널 1)
python manage.py runserver

# Locust 실행 (터미널 2)
locust -f performance/locustfile.py --host=http://localhost:8000
```

웹 브라우저에서 http://localhost:8089 접속:
- Number of users: 1000 (총 가상 사용자 수)
- Spawn rate: 10 (초당 증가 사용자 수)
- Host: http://localhost:8000

### 2. CLI 모드 (CI/CD용)

```bash
locust -f performance/locustfile.py \
    --host=http://localhost:8000 \
    --users 1000 \
    --spawn-rate 10 \
    --run-time 5m \
    --headless \
    --html report.html
```

### 3. 특정 시나리오만 실행

```bash
# 결제 시나리오만
locust -f performance/scenarios/payment.py --host=http://localhost:8000
```

## 결과 분석

### 주요 지표

1. **RPS (Requests Per Second)**: 초당 처리 요청 수
2. **Response Time**: 응답 시간 (평균, P50, P95, P99)
3. **Failure Rate**: 실패율 (5% 이하 목표)
4. **Concurrent Users**: 동시 사용자 수

### 목표

- 1000 동시 사용자 처리
- 평균 응답 시간 < 1초
- P95 응답 시간 < 2초
- 실패율 < 5%
```

### 2-6. 테스트 데이터 준비: `performance/setup_test_data.py`

```python
"""로드 테스트용 데이터 생성

1000명의 사용자와 100개의 상품을 미리 생성합니다.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from shopping.tests.factories import UserFactory, ProductFactory


def setup_test_data():
    """테스트 데이터 생성"""
    print("테스트 사용자 생성 중...")
    users = []
    for i in range(1000):
        user = UserFactory(
            username=f'load_test_user_{i}',
            email=f'load_test_{i}@example.com',
            is_email_verified=True
        )
        user.set_password('testpass123')
        user.save()
        users.append(user)

        if (i + 1) % 100 == 0:
            print(f"{i + 1}/1000 사용자 생성 완료")

    print("\n테스트 상품 생성 중...")
    products = []
    for i in range(100):
        product = ProductFactory(
            name=f'성능테스트 상품 {i}',
            price=10000 + (i * 1000),
            stock=1000,
            is_active=True
        )
        products.append(product)

    print(f"100개 상품 생성 완료")
    print(f"\n총 {len(users)}명 사용자, {len(products)}개 상품 생성 완료")


if __name__ == '__main__':
    setup_test_data()
```

## 3단계: 문서화 (`docs/PERFORMANCE_TESTING.md`)

전체 내용은 너무 길어서 주요 섹션만 요약:

```markdown
# 성능 테스트 가이드

## 개요
- 단위 테스트 (pytest): 비즈니스 로직 동시성 검증
- 로드 테스트 (Locust): 대규모 트래픽 처리 능력 검증

## 성능 목표
- P50: < 500ms
- P95: < 1000ms
- P99: < 2000ms

## 병목 지점 및 해결 방법
- DB 연결 풀 고갈 → PgBouncer 도입
- 느린 쿼리 → 인덱스 추가, N+1 최적화
- Celery Task 적체 → Worker 수 증가
```

## 4단계: Git 커밋

```bash
# 현재 세션 작업 커밋
git add -A
git commit -m "chore: remove redundant pytest performance test"

# 다음 세션에서 Locust 구현 완료 후:
git add performance/ docs/PERFORMANCE_TESTING.md requirements.txt
git commit -m "feat: add Locust load testing framework

- Add Locust configuration and scenarios
- Add performance testing documentation
- Add test data setup script
- Remove redundant pytest performance test

Load testing features:
- 1000+ concurrent users simulation
- Payment, order, browsing scenarios
- Web UI for real-time monitoring
- CLI mode for CI/CD integration"
```

## 요약

### 다음 세션 작업 순서
1. `performance/` 디렉토리 생성
2. 위 코드 복사하여 파일 생성
3. `docs/PERFORMANCE_TESTING.md` 작성
4. `pip install locust` 실행
5. Git 커밋

### 예상 소요 시간: 약 1시간

파일 생성 완료 후 이 가이드는 삭제해도 됩니다!
