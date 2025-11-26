# Advanced Concurrency Tests Implementation Plan

포인트 만료 race condition과 로그인 동시성 테스트를 추가하여 동시성 테스트 커버리지를 완성합니다.

## User Review Required

> [!IMPORTANT]
> **스케일 검증 테스트 범위**
>
> pytest에 500명 동시성 테스트를 추가할 예정입니다. 이는 로직 검증용이며, Locust는 1000명 이상 부하 테스트로 역할을 분리합니다.
> - pytest: 로직 정확성 + 중간 스케일 검증 (10~500명)
> - Locust: 대규모 부하 + 성능 측정 (1000명 이상)

> [!NOTE]
> **기존 테스트와의 관계**
>
> 이미 구현된 강력한 테스트들을 보완하는 형태입니다:
> - 주문/결제/장바구니 동시성 테스트: 이미 완성도 높음 ✅
> - 포인트 적립/차감 동시성: 이미 구현됨 ✅
> - **신규 추가**: 포인트 만료 race, 로그인 동시성, 스케일 검증

---

## Proposed Changes

### Test Files

#### [NEW] [test_point_expiry_concurrency.py](file:///c:/Users/admin/Desktop/python/CRUD/myproject/shopping/tests/test_point_expiry_concurrency.py)

**목적**: 포인트 만료 스케줄러와 사용자의 포인트 사용 간 race condition 검증

**테스트 시나리오**:

1. **만료 처리 중 포인트 사용 시도**
   - 시나리오: 만료 예정 포인트를 스케줄러가 만료 처리하는 중에 사용자가 사용 시도
   - 예상 결과: `select_for_update`로 인해 한 작업만 성공
   - 검증: 만료된 포인트는 사용 불가, 사용된 포인트는 만료 불가

2. **포인트 사용 중 만료 처리 시도**
   - 시나리오: 사용자가 포인트를 사용하는 트랜잭션 중에 만료 스케줄러 실행
   - 예상 결과: 트랜잭션 격리로 인해 순차 처리
   - 검증: 데이터 일관성 유지

3. **FIFO 순서 보장 동시성**
   - 시나리오: 여러 사용자가 동시에 포인트 사용, 만료일이 다른 포인트들
   - 예상 결과: 가장 오래된 포인트부터 차감 (FIFO)
   - 검증: 포인트 히스토리 생성 순서 확인

4. **만료 임박 포인트의 경합 상황**
   - 시나리오: 10명이 동시에 만료 임박 포인트 사용 시도
   - 예상 결과: 선착순으로 처리, 나머지는 다음 포인트로 차감
   - 검증: 총 사용 포인트와 잔액 일치

**구현 기법**:
- `threading` 사용하여 다중 스레드 시뮬레이션
- `select_for_update` 동작 검증
- Celery task (만료 스케줄러)와 API 요청(포인트 사용) 동시 실행

---

#### [NEW] [test_auth_concurrency.py](file:///c:/Users/admin/Desktop/python/CRUD/myproject/shopping/tests/auth/test_auth_concurrency.py)

**목적**: 로그인/JWT 발급/토큰 갱신의 동시성 검증

**테스트 시나리오**:

1. **100명 동시 로그인**
   - 시나리오: 100개 스레드에서 동시에 로그인 API 호출
   - 예상 결과: 모두 성공, 각각 고유한 JWT 발급
   - 검증:
     - 100개 JWT 토큰 모두 유효
     - DB 커넥션 풀 고갈 없음
     - 응답 시간 합리적 범위 내

2. **동일 사용자 동시 로그인**
   - 시나리오: 같은 계정으로 10개 스레드 동시 로그인
   - 예상 결과: 모두 성공, 각각 별도 세션
   - 검증:
     - 10개 토큰 모두 유효
     - `OutstandingToken` 테이블에 10개 레코드 생성

3. **Refresh Token 동시 갱신**
   - 시나리오: 같은 refresh token으로 5개 스레드 동시 갱신 시도
   - 예상 결과: 1개만 성공 (ROTATE_REFRESH_TOKENS=True)
   - 검증:
     - 성공 1개, 나머지 실패 (blacklist)
     - 새 refresh token 1개만 발급

4. **Rate Limiting 동시 요청**
   - 시나리오: 100개 스레드 동시 로그인 → rate limit 초과
   - 예상 결과: 일부만 성공, 나머지 429 응답
   - 검증:
     - Rate limit 설정대로 제한됨
     - Redis 캐시 경합 처리 정상

5. **동시 회원가입**
   - 시나리오: 같은 이메일로 5명 동시 회원가입 시도
   - 예상 결과: 1명만 성공 (unique constraint)
   - 검증:
     - DB level unique 제약 동작
     - 나머지 4명은 400 에러

**구현 기법**:
- `threading` + `APIClient` per thread
- Rate limiting: Redis 동시성 검증
- JWT blacklist: `select_for_update` 검증

---

### Scale Validation Tests

기존 테스트 파일에 **스케일 검증용 테스트 메서드** 추가:

#### [MODIFY] [test_order_concurrency.py](file:///c:/Users/admin/Desktop/python/CRUD/myproject/shopping/tests/order/test_order_concurrency.py)

**추가 테스트**:
```python
@pytest.mark.slow
def test_concurrent_order_creation_500_users(self, product, shipping_data):
    """500명 동시 주문 생성 - 스케일 검증"""
    # 재고: 1000개
    # 사용자: 500명, 각 1개씩 주문
    # 예상: 500개 주문 성공, 재고 500개 남음
```

---

#### [MODIFY] [test_payment_concurrency.py](file:///c:/Users/admin/Desktop/python/CRUD/myproject/shopping/tests/payment/test_payment_concurrency.py)

**추가 테스트**:
```python
@pytest.mark.slow
def test_concurrent_payment_confirm_500_users(self, product, user_factory, ...):
    """500명 동시 결제 승인 - 스케일 검증"""
    # 사용자: 500명
    # 재고: 1000개
    # 예상: 500개 결제 성공, 재고 500개 남음
```

---

#### [MODIFY] [test_point_service.py](file:///c:/Users/admin/Desktop/python/CRUD/myproject/shopping/tests/services/test_point_service.py)

**추가 테스트**:
```python
@pytest.mark.slow
def test_use_points_concurrency_500_users(self):
    """500명 동시 포인트 사용 - 스케일 검증"""
    # 포인트: 500,000P
    # 사용자: 500명, 각 1,000P씩 사용
    # 예상: 500명 모두 성공, 잔액 0
```

---

### Configuration

#### [MODIFY] [pytest.ini](file:///c:/Users/admin/Desktop/python/CRUD/myproject/pytest.ini) 또는 [pyproject.toml](file:///c:/Users/admin/Desktop/python/CRUD/myproject/pyproject.toml)

`@pytest.mark.slow` 마커 추가:
```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (500+ concurrent users)",
]
```

실행 방법:
```bash
# 일반 테스트 (빠른 것만)
pytest -m "not slow"

# 스케일 검증 테스트 포함
pytest

# 스케일 검증 테스트만
pytest -m slow
```

---

## Verification Plan

### Automated Tests

각 테스트는 자체적으로 검증 로직 포함:

1. **포인트 만료 race 테스트**
   ```bash
   pytest shopping/tests/test_point_expiry_concurrency.py -v
   ```
   - 만료/사용 race 검증
   - FIFO 순서 보장 확인
   - 트랜잭션 격리 확인

2. **로그인 동시성 테스트**
   ```bash
   pytest shopping/tests/auth/test_auth_concurrency.py -v
   ```
   - JWT 발급 동시성
   - Refresh token 갱신 race
   - Rate limiting 동작

3. **스케일 검증 테스트**
   ```bash
   pytest -m slow -v
   ```
   - 500명 주문/결제/포인트 동시성
   - DB connection pool 충분성
   - 응답 시간 합리성

### Manual Verification

**테스트 실행 시간 확인**:
- 일반 테스트: 5분 이내 완료
- 스케일 검증: 10~15분 소요 예상
- 너무 느리면 동시성 수 조정 (500 → 300)

**리소스 사용 확인**:
- PostgreSQL 커넥션 수: 100개 이하 유지
- 메모리 사용량: 과도한 증가 없음
- 테스트 간 격리: 각 테스트 독립 실행 가능

---

## Implementation Order

1. ✅ **포인트 만료 race 테스트** (1시간)
   - 가장 중요하고 임팩트 큼
   - 기존 포인트 테스트 참고 가능

2. ✅ **로그인 동시성 테스트** (1시간)
   - JWT 관련 로직 집중
   - 기존 auth 테스트 참고

3. ✅ **스케일 검증 테스트 추가** (30분)
   - 기존 테스트 패턴 확장
   - 단순히 사용자 수만 증가

4. ✅ **pytest 마커 설정** (10분)
   - `@pytest.mark.slow` 추가
   - 실행 옵션 문서화

**총 예상 시간**: 3시간
