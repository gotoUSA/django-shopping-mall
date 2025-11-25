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
locust -f shopping/tests/performance/locustfile.py --host=http://localhost:8000
```

웹 브라우저에서 http://localhost:8089 접속:
- Number of users: 1000 (총 가상 사용자 수)
- Spawn rate: 10 (초당 증가 사용자 수)
- Host: http://localhost:8000

### 2. CLI 모드 (CI/CD용)

```bash
locust -f shopping/tests/performance/locustfile.py \
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
locust -f shopping/tests/performance/scenarios/payment.py --host=http://localhost:8000
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
