# Payment 테스트 리팩토링 가이드

## 📋 개요

Factory Boy를 활용하여 `shopping/tests/payment` 디렉토리의 테스트를 개선하는 가이드입니다.

## 🎯 개선 목표

1. **하드코딩 제거**: 배송 정보, 금액, 날짜 등의 하드코딩 제거
2. **코드 중복 제거**: Order, Payment, PointHistory 생성 코드 중복 제거
3. **가독성 향상**: Factory를 사용하여 테스트 의도를 명확하게 표현
4. **유지보수성 향상**: 공통 값 변경 시 한 곳만 수정하면 됨

## 🏭 Factory 사용법

### 1. 기본 Factory 사용

```python
from shopping.tests.factories import (
    UserFactory,
    ProductFactory,
    OrderFactory,
    PaymentFactory,
    PointHistoryFactory,
    TestConstants,
    TossResponseBuilder,
)

# 기본 사용자 생성
user = UserFactory()

# 커스터마이징
user = UserFactory(points=10000, membership_level="gold")

# 상품 생성
product = ProductFactory(price=Decimal("50000"))
```

### 2. 주문 생성

```python
# 기본 pending 주문
order = OrderFactory(user=user)

# 결제 완료 주문
order = PaidOrderFactory(user=user, earned_points=100)

# OrderItem 포함
order = OrderFactory(user=user)
OrderItemFactory(order=order, product=product)
```

### 3. Payment 생성

```python
# 기본 ready 상태
payment = PaymentFactory(order=order)

# 완료된 payment
payment = CompletedPaymentFactory(order=order)
```

### 4. PointHistory 생성

```python
# 포인트 적립
history = PointHistoryFactory(
    user=user,
    points=1000,
    balance=6000,
    description="적립 테스트"
)
```

### 5. Toss API 응답

```python
# 성공 응답
toss_response = TossResponseBuilder.success_response(
    payment_key="test_key",
    amount=10000
)

# 취소 응답
cancel_response = TossResponseBuilder.cancel_response(
    payment_key="test_key"
)

# 에러 응답
error_response = TossResponseBuilder.error_response(
    code="INVALID_REQUEST",
    message="잘못된 요청입니다"
)
```

## 📊 Before/After 비교

### Before (하드코딩)

```python
def test_example(self, authenticated_client, user, product):
    # Arrange
    order = Order.objects.create(
        user=user,
        status="pending",
        total_amount=product.price,
        final_amount=product.price,
        shipping_name="홍길동",  # 하드코딩
        shipping_phone="010-1234-5678",  # 하드코딩
        shipping_postal_code="12345",  # 하드코딩
        shipping_address="서울시 강남구",  # 하드코딩
        shipping_address_detail="101동",  # 하드코딩
        order_number="20250115999001",  # 하드코딩
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=1,
        price=product.price,
    )

    payment = Payment.objects.create(
        order=order,
        amount=order.total_amount,
        status="ready",
        toss_order_id=order.order_number,
        payment_key="test_key",  # 하드코딩
        method="카드",
    )

    toss_response = {  # 구조 하드코딩
        "status": "DONE",
        "approvedAt": "2025-01-15T10:00:00+09:00",
        "totalAmount": int(payment.amount),
    }
```

### After (Factory 사용)

```python
def test_example(self, authenticated_client, user):
    # Arrange
    product = ProductFactory()
    order = OrderFactory(user=user, status="pending")
    OrderItemFactory(order=order, product=product)
    payment = PaymentFactory(order=order)

    toss_response = TossResponseBuilder.success_response(
        payment_key=payment.payment_key,
        amount=int(payment.amount),
    )
```

**개선 효과:**
- 코드 라인 수: 30줄 → 7줄 (76% 감소)
- 하드코딩: 10개 → 0개
- 가독성: 테스트 의도가 명확함

## 🔧 리팩토링 절차

### 1. 단계별 접근

1. **새 테스트 작성 시**: 무조건 Factory 사용
2. **기존 테스트 수정 시**: Factory로 교체
3. **대규모 리팩토링**: 파일 단위로 점진적 개선

### 2. 우선순위

#### 우선순위 1: 매우 높음
- [ ] `test_payment_points.py` - 가장 많은 하드코딩
- [ ] `test_payment_confirm.py` - Toss 응답 하드코딩
- [ ] `test_payment_cancel.py` - Toss 응답 하드코딩

#### 우선순위 2: 높음
- [ ] `test_payment_validation.py` - Order 생성 하드코딩
- [ ] `test_payment_fail.py` - 배송 정보 하드코딩
- [ ] `test_payment_request.py` - 배송 정보 하드코딩

#### 우선순위 3: 중간
- [ ] `test_payment_concurrency.py` - 동시성 테스트
- [ ] `test_payment_detail.py` - Payment 조회
- [ ] `test_payment_list.py` - Payment 목록

### 3. 리팩토링 체크리스트

파일 리팩토링 시 다음을 확인하세요:

- [ ] `from shopping.tests.factories import ...` 추가
- [ ] 배송 정보 하드코딩 제거 (`TestConstants` 사용)
- [ ] `Order.objects.create()` → `OrderFactory()` 교체
- [ ] `Payment.objects.create()` → `PaymentFactory()` 교체
- [ ] `PointHistory.create_history()` → `PointHistoryFactory()` 교체
- [ ] Toss 응답 딕셔너리 → `TossResponseBuilder` 교체
- [ ] 매직 넘버 → `TestConstants` 교체
- [ ] 테스트 실행하여 정상 동작 확인

## 📝 TestConstants 사용

```python
from shopping.tests.factories import TestConstants

# 금액
TestConstants.DEFAULT_PRODUCT_PRICE  # Decimal("10000")
TestConstants.DEFAULT_SHIPPING_FEE   # Decimal("3000")
TestConstants.DEFAULT_TOTAL_AMOUNT   # Decimal("13000")

# 포인트
TestConstants.DEFAULT_POINTS         # 5000
TestConstants.DEFAULT_EARN_POINTS    # 100

# 배송 정보
TestConstants.DEFAULT_SHIPPING_NAME  # "홍길동"
TestConstants.DEFAULT_SHIPPING_PHONE # "010-1234-5678"
# ... 등등
```

## 🔍 자체 코드 리뷰 체크리스트

리팩토링 후 다음을 확인하세요:

### 기능 검증
- [ ] 모든 테스트가 통과하는가?
- [ ] 테스트의 의도가 변경되지 않았는가?
- [ ] 테스트 커버리지가 유지되는가?

### 코드 품질
- [ ] 하드코딩이 제거되었는가?
- [ ] 중복 코드가 제거되었는가?
- [ ] 코드가 더 읽기 쉬워졌는가?
- [ ] 주석이 필요한가? (코드로 설명 가능한가?)

### 성능 & 보안
- [ ] Factory 생성이 과도하지 않은가?
- [ ] 민감한 정보 (비밀번호 등)가 하드코딩되지 않았는가?
- [ ] 테스트 데이터 격리가 잘 되어 있는가?

### 유지보수성
- [ ] 공통 값 변경 시 한 곳만 수정하면 되는가?
- [ ] 새 테스트 추가가 쉬워졌는가?
- [ ] Factory의 의미가 명확한가?

## 🚀 예시: test_payment_points_refactored.py

`test_payment_points_refactored.py` 파일을 참고하세요. 기존 `test_payment_points.py`의 일부 테스트를 Factory로 리팩토링한 예시입니다.

**주요 개선 사항:**
- 배송 정보 하드코딩 10곳 → 0곳
- Order 생성 코드 30줄 → 5줄
- Toss 응답 하드코딩 제거
- PointHistory 생성 간소화

## 💡 Best Practices

1. **의미 있는 변수명 사용**
   ```python
   # Good
   paid_order = PaidOrderFactory(user=user)

   # Bad
   o = OrderFactory()
   ```

2. **필요한 것만 커스터마이징**
   ```python
   # Good - 필요한 것만 오버라이드
   user = UserFactory(points=10000)

   # Bad - 모든 것을 지정
   user = UserFactory(
       username="user1",
       email="user1@test.com",
       phone_number="010-1234-5678",
       password="testpass123",
       points=10000,
       membership_level="bronze"
   )
   ```

3. **테스트 의도 명확히**
   ```python
   # Good - 테스트 의도가 명확함
   def test_gold_member_earns_3_percent_points(self):
       user = UserFactory(membership_level="gold")
       # ...

   # Bad - 의도가 불명확
   def test_points(self):
       user = UserFactory()
       user.membership_level = "gold"
       user.save()
       # ...
   ```

## 📚 참고 자료

- [Factory Boy 공식 문서](https://factoryboy.readthedocs.io/)
- [Django Testing Best Practices](https://docs.djangoproject.com/en/stable/topics/testing/)
- [Pytest Best Practices](https://docs.pytest.org/en/stable/goodpractices.html)

## 🎯 다음 단계

1. `test_payment_points_refactored.py` 검토
2. 다른 파일에 패턴 적용
3. 점진적으로 모든 테스트 파일 개선
4. 레거시 하드코딩 완전 제거

---

**작성일**: 2025-01-15
**작성자**: Claude Code Refactoring
