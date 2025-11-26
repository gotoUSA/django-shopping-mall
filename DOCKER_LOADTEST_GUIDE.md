# Docker 환경에서 부하 테스트 가이드

## 📌 현재 상황

Docker 환경에서 Locust 부하 테스트를 진행하기 위해 **Production-like 환경**을 구성했습니다.

## 🎯 선택 가능한 옵션

### 옵션 1: Gunicorn만 사용 (현재 기본 설정) ⭐ 추천

**장점:**
- 설정이 간단함
- 이미 `docker-compose.yml`에 적용됨
- Nginx 없이도 충분히 production-like 환경

**사용 방법:**
```bash
# 1. 컨테이너 재빌드 및 실행
docker-compose down
docker-compose up --build

# 2. 테스트 데이터 생성 (컨테이너 내부에서 실행)
docker-compose exec web python shopping/tests/performance/setup_test_data.py

# 3. 로컬에서 Locust 실행 (호스트 머신에서)
locust -f shopping/tests/performance/locustfile.py --host=http://localhost:8000
```

**확인:**
- 브라우저에서 http://localhost:8000/admin 접속 가능
- Gunicorn 로그에서 `Booting worker` 메시지 확인
- 4개의 worker가 동작 중인지 확인

---

### 옵션 2: Gunicorn + Nginx 사용 (완전한 Production 환경)

**장점:**
- 실제 production 환경과 거의 동일
- 정적 파일 서빙 최적화
- 리버스 프록시를 통한 부하 분산

**사용 방법:**
```bash
# 1. 부하 테스트용 Docker Compose 사용
docker-compose -f docker-compose.loadtest.yml down
docker-compose -f docker-compose.loadtest.yml up --build

# 2. 테스트 데이터 생성
docker-compose -f docker-compose.loadtest.yml exec web python shopping/tests/performance/setup_test_data.py

# 3. 로컬에서 Locust 실행
locust -f shopping/tests/performance/locustfile.py --host=http://localhost
```

**포트 차이:**
- `docker-compose.yml`: http://localhost:8000 (Gunicorn 직접)
- `docker-compose.loadtest.yml`: http://localhost:80 (Nginx를 통해)

**확인:**
- 브라우저에서 http://localhost/admin 접속 (포트 80)
- Nginx 헬스 체크: http://localhost/health/
- Flower 대시보드: http://localhost:5555

---

## 🚀 부하 테스트 실행

### 1단계: 환경 선택 및 실행

#### Gunicorn만 사용 (옵션 1)
```bash
docker-compose down
docker-compose up --build -d
```

#### Gunicorn + Nginx 사용 (옵션 2)
```bash
docker-compose -f docker-compose.loadtest.yml down
docker-compose -f docker-compose.loadtest.yml up --build -d
```

### 2단계: 테스트 데이터 생성

```bash
# 옵션 1 (기본)
docker-compose exec web python shopping/tests/performance/setup_test_data.py

# 옵션 2 (Nginx)
docker-compose -f docker-compose.loadtest.yml exec web python shopping/tests/performance/setup_test_data.py
```

**확인:**
- 사용자 1000명 생성됨
- 상품 100개 생성됨

### 3단계: Locust 실행

```bash
# 옵션 1: Gunicorn 직접 (포트 8000)
locust -f shopping/tests/performance/locustfile.py --host=http://localhost:8000

# 옵션 2: Nginx 경유 (포트 80)
locust -f shopping/tests/performance/locustfile.py --host=http://localhost
```

브라우저에서 http://localhost:8089 접속하여 부하 테스트 시작!

---

## 📊 모니터링

### Docker 컨테이너 로그 확인

```bash
# 전체 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f web        # Django/Gunicorn
docker-compose logs -f nginx      # Nginx (옵션 2)
docker-compose logs -f celery_worker
```

### 리소스 사용량 모니터링

```bash
# 실시간 CPU/메모리 사용량
docker stats

# 특정 컨테이너만 확인
docker stats myproject-web-1 myproject-db-1
```

### DB 커넥션 확인

```bash
# PostgreSQL 컨테이너에 접속
docker-compose exec db psql -U shopping_user -d shopping_db

# 커넥션 수 확인
SELECT count(*) FROM pg_stat_activity;
```

### Flower (Celery 모니터링)

http://localhost:5555 접속하여:
- 활성 Task 확인
- Worker 상태 확인
- 큐 적체 여부 확인

---

## 🔧 성능 튜닝

### Gunicorn Workers 조정

`docker-compose.yml` 또는 `docker-compose.loadtest.yml`에서:

```yaml
# 권장: (2 × CPU 코어 수) + 1
command: gunicorn myproject.wsgi:application --bind 0.0.0.0:8000 --workers 8 --timeout 120
```

### Celery Workers 동시성 조정

```yaml
command: celery -A myproject worker -l info --concurrency=16
```

### DB 커넥션 풀 설정

`.env` 또는 `settings.py`에서:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'CONN_MAX_AGE': 600,  # 10분
        'OPTIONS': {
            'connect_timeout': 10,
        }
    }
}
```

---

## 💡 추천 시나리오

### 처음 시작 (1주차)
- **옵션 1 (Gunicorn만)**로 시작
- Smoke Test: 10-100명
- 기본 병목 지점 파악

### 본격 테스트 (2-3주차)
- **옵션 2 (Gunicorn + Nginx)**로 전환
- Stress Test: 500-1000명
- 성능 최적화 적용

---

## 🚨 주의 사항

1. **테스트 후 정리:**
   ```bash
   # 컨테이너 중지 및 삭제
   docker-compose down
   docker-compose -f docker-compose.loadtest.yml down

   # 볼륨까지 완전 삭제 (주의!)
   docker-compose down -v
   ```

2. **포트 충돌 확인:**
   - 기본 설정: 8000 (Gunicorn)
   - Nginx 설정: 80 (Nginx)
   - 로컬에서 이미 사용 중인 포트가 있다면 `docker-compose.yml`에서 변경

3. **로그 크기 관리:**
   ```bash
   # 로그 파일 정리
   docker-compose logs --no-color > test_logs.txt
   docker system prune -a
   ```

---

## 🎓 FAQ

**Q: Gunicorn과 Nginx 중 어느 것을 선택해야 하나요?**
A: 처음에는 **Gunicorn만 (옵션 1)** 사용하세요. 충분히 production-like 환경이고, 설정도 간단합니다. Nginx는 필요 시 나중에 추가하면 됩니다.

**Q: Worker 수를 몇 개로 설정해야 하나요?**
A: Gunicorn은 `(2 × CPU 코어 수) + 1`, Celery는 CPU 코어 수만큼 권장. 로컬 테스트에서는 4-8개가 적당합니다.

**Q: Locust를 Docker 내부에서 실행해야 하나요?**
A: 아니요. Locust는 **호스트 머신(로컬)**에서 실행하는 것을 권장합니다. 이렇게 하면 부하 테스트 도구와 대상 시스템이 분리되어 더 정확한 측정이 가능합니다.

**Q: 테스트 데이터는 매번 새로 생성해야 하나요?**
A: 처음 한 번만 생성하면 됩니다. 단, DB 볼륨을 삭제(`docker-compose down -v`)했다면 다시 생성해야 합니다.
