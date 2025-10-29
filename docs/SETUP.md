# 설치 및 환경 설정 가이드

Django Shopping Mall API의 상세 설치 가이드입니다.

## 📋 목차

- [Docker 환경 설정 (권장)](#-docker-환경-설정-권장)
- [로컬 개발 환경 설정](#-로컬-개발-환경-설정)
- [환경 변수 설정](#-환경-변수-설정)
- [데이터베이스 설정](#-데이터베이스-설정)
- [프로덕션 배포](#-프로덕션-배포)

---

## 🐳 Docker 환경 설정 (권장)

### Prerequisites

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **Git**

### Docker 설치 확인

```bash
docker --version
docker-compose --version
```

### 1. 프로젝트 클론

```bash
git clone https://github.com/gotoUSA/django-shopping-mall.git
cd django-shopping-mall
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일 편집 (아래 필수 설정 섹션 참조)
```

### 3. Docker Compose로 전체 서비스 실행

```bash
# 백그라운드 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 서비스 상태 확인
docker-compose ps
```

**실행되는 서비스:**
- `web` - Django API 서버 (포트 8000)
- `db` - PostgreSQL 15 (포트 5432)
- `redis` - Redis 7 (포트 6379)
- `celery_worker` - Celery 워커 (비동기 작업 처리)
- `celery_beat` - Celery Beat (스케줄 작업)
- `flower` - Flower (Celery 모니터링, 포트 5555)

### 4. 마이그레이션 실행

```bash
docker-compose exec web python manage.py migrate
```

### 5. 관리자 계정 생성

```bash
docker-compose exec web python manage.py createsuperuser
```

### 6. 테스트 데이터 생성 (선택)

```bash
# 기본 데이터
docker-compose exec web python manage.py create_test_data --preset basic

# 전체 데이터
docker-compose exec web python manage.py create_test_data --preset full
```

### 7. 접속 확인

- **API**: http://localhost:8000/api/
- **Admin**: http://localhost:8000/admin/
- **Swagger**: http://localhost:8000/swagger/
- **Flower**: http://localhost:5555/

### Docker 명령어

```bash
# 서비스 재시작
docker-compose restart

# 특정 서비스만 재시작
docker-compose restart web

# 서비스 중지
docker-compose stop

# 서비스 중지 및 컨테이너 삭제
docker-compose down

# 볼륨까지 삭제 (데이터베이스 초기화)
docker-compose down -v

# 컨테이너 접속
docker-compose exec web bash

# Django 쉘 실행
docker-compose exec web python manage.py shell
```

---

## 🔧 로컬 개발 환경 설정

Docker 없이 로컬에서 직접 실행하는 방법입니다.

### 사전 요구사항

- **Python 3.12 이상**
- **Git**
- **Redis Server** (Celery용)

### Python 설치 확인

```bash
python --version  # Python 3.12+ 확인
pip --version
```

### Redis 설치

**macOS (Homebrew):**
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

**Windows:**
- [Redis for Windows](https://github.com/microsoftarchive/redis/releases) 다운로드
- 또는 WSL2 사용

### Redis 연결 확인
```bash
redis-cli ping
# 응답: PONG
```

---

## 🚀 개발 환경 설정

### 1. 저장소 클론

```bash
git clone https://github.com/gotoUSA/django-shopping-mall.git
cd django-shopping-mall
```

### 2. 가상환경 생성 및 활성화

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

가상환경이 활성화되면 프롬프트에 `(venv)`가 표시됩니다.

### 3. 패키지 설치

```bash
# 운영 환경 패키지
pip install -r requirements.txt

# 개발 환경 패키지 (선택)
pip install -r requirements-dev.txt
```

**requirements.txt 주요 패키지:**
- Django 5.2.4
- djangorestframework 3.14
- djangorestframework-simplejwt
- celery[redis]
- django-cors-headers
- pillow (이미지 처리)
- requests (토스페이먼츠 API)

**requirements-dev.txt 주요 패키지:**
- black (코드 포매팅)
- flake8 (린팅)
- pytest, pytest-django (테스트)
- coverage (커버리지 측정)

### 4. 설치 확인

```bash
python manage.py --version
# Django 버전이 출력되면 성공
```

---

## ⚙️ 환경 변수 설정

### 1. .env 파일 생성

```bash
cp .env.example .env
```

### 2. .env 파일 편집

```env
# ==============================================
# Django 기본 설정
# ==============================================
SECRET_KEY=your-secret-key-here-change-this-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# ==============================================
# 데이터베이스 설정
# ==============================================
# 개발 환경에서는 SQLite 사용 (기본값)
# 프로덕션에서는 PostgreSQL 사용 권장

# PostgreSQL 설정 (프로덕션)
# DATABASE_ENGINE=django.db.backends.postgresql
# DATABASE_NAME=shopping_mall
# DATABASE_USER=postgres
# DATABASE_PASSWORD=your-password
# DATABASE_HOST=localhost
# DATABASE_PORT=5432

# ==============================================
# 토스페이먼츠 설정
# ==============================================
# https://developers.tosspayments.com/ 에서 발급

# 클라이언트 키 (프론트엔드에서 결제창 열 때 사용)
TOSS_CLIENT_KEY=test_ck_YOUR_CLIENT_KEY_HERE

# 시크릿 키 (서버에서 API 호출 시 사용)
TOSS_SECRET_KEY=test_sk_YOUR_SECRET_KEY_HERE

# 웹훅 시크릿 (웹훅 서명 검증용)
TOSS_WEBHOOK_SECRET=YOUR_WEBHOOK_SECRET_HERE

# API 베이스 URL (기본값 사용 권장)
TOSS_BASE_URL=https://api.tosspayments.com

# ==============================================
# 프론트엔드 설정
# ==============================================
# 결제 완료/실패 후 리다이렉트할 URL
FRONTEND_URL=http://localhost:3000

# ==============================================
# Redis/Celery 설정
# ==============================================
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# ==============================================
# 이메일 설정 (선택사항)
# ==============================================
# 개발 시에는 console 백엔드 사용 (터미널에 출력)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# 운영 시에는 SMTP 사용
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# EMAIL_HOST=smtp.gmail.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_HOST_USER=your-email@gmail.com
# EMAIL_HOST_PASSWORD=your-app-password
# DEFAULT_FROM_EMAIL=noreply@shopping.com

# ==============================================
# 테스트 설정
# ==============================================
TEST_USER_PASSWORD=testpass123!
TEST_ADMIN_PASSWORD=admin123!
```

### 3. SECRET_KEY 생성

안전한 SECRET_KEY 생성:

```python
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 4. 토스페이먼츠 키 발급

1. https://developers.tosspayments.com/ 접속
2. 회원가입 및 로그인
3. 내 앱 만들기
4. 개발자센터에서 API 키 확인
5. 테스트 키를 `.env`에 복사

---

## 🗄 데이터베이스 설정

### 개발 환경 (SQLite)

별도 설정 없이 바로 사용 가능:

```bash
# 마이그레이션 실행
python manage.py migrate

# 데이터베이스 파일 생성 확인
ls -la db.sqlite3
```

### 프로덕션 환경 (PostgreSQL)

#### 1. PostgreSQL 설치

**Ubuntu/Debian:**
```bash
sudo apt-get install postgresql postgresql-contrib
```

**macOS:**
```bash
brew install postgresql
brew services start postgresql
```

#### 2. 데이터베이스 생성

```bash
# PostgreSQL 접속
sudo -u postgres psql

# 데이터베이스 생성
CREATE DATABASE shopping_mall;

# 사용자 생성 및 권한 부여
CREATE USER shopping_user WITH PASSWORD 'secure_password';
ALTER ROLE shopping_user SET client_encoding TO 'utf8';
ALTER ROLE shopping_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE shopping_user SET timezone TO 'Asia/Seoul';
GRANT ALL PRIVILEGES ON DATABASE shopping_mall TO shopping_user;

# 종료
\q
```

#### 3. .env 파일 수정

```env
DATABASE_ENGINE=django.db.backends.postgresql
DATABASE_NAME=shopping_mall
DATABASE_USER=shopping_user
DATABASE_PASSWORD=secure_password
DATABASE_HOST=localhost
DATABASE_PORT=5432
```

#### 4. psycopg2 설치

```bash
pip install psycopg2-binary
```

#### 5. 마이그레이션 실행

```bash
python manage.py migrate
```

---

## 👤 관리자 계정 생성

```bash
python manage.py createsuperuser
```

입력 항목:
- Username: admin
- Email: admin@example.com
- Password: (안전한 비밀번호 입력)

생성 후 접속:
```
http://localhost:8000/admin/
```

---

## 📦 테스트 데이터 생성

### 기본 데이터

```bash
python manage.py create_test_data --preset basic
```

**생성 내용:**
- 카테고리: 5개
- 상품: 약 25개
- 사용자: 5명
- 리뷰: 포함

### 최소 데이터 (빠른 테스트용)

```bash
python manage.py create_test_data --preset minimal
```

**생성 내용:**
- 카테고리: 3개
- 상품: 약 9개
- 사용자: 3명
- 리뷰: 미포함

### 전체 데이터 (성능 테스트용)

```bash
python manage.py create_test_data --preset full
```

**생성 내용:**
- 카테고리: 10개
- 상품: 약 100개
- 사용자: 20명
- 리뷰: 포함

### 기존 데이터 삭제 후 생성

```bash
python manage.py create_test_data --preset basic --clear
```

---

## 🔄 Redis 및 Celery 설정

### Celery Worker 실행

비동기 작업 처리를 위한 워커:

```bash
# Windows
celery -A myproject worker -l info --pool=solo

# macOS/Linux
celery -A myproject worker -l info
```

### Celery Beat 실행 (선택사항)

주기적 작업 스케줄러:

```bash
celery -A myproject beat -l info
```

### 동시 실행 (개발 환경)

터미널 3개를 열어서:

**터미널 1 - Django 서버:**
```bash
python manage.py runserver
```

**터미널 2 - Celery Worker:**
```bash
celery -A myproject worker -l info
```

**터미널 3 - Celery Beat:**
```bash
celery -A myproject beat -l info
```

---

## 🌐 서버 실행

### 개발 서버

```bash
python manage.py runserver
```

접속 URL:
- API: http://localhost:8000/api/
- Admin: http://localhost:8000/admin/
- Swagger: http://localhost:8000/api/schema/swagger-ui/

### 다른 포트로 실행

```bash
python manage.py runserver 8080
```

### 외부 접속 허용

```bash
python manage.py runserver 0.0.0.0:8000
```

`.env` 파일에서 `ALLOWED_HOSTS` 설정 필요:
```env
ALLOWED_HOSTS=localhost,127.0.0.1,your-ip-address
```

---

## 🐳 Docker 설정 (선택사항)

### Docker Compose로 실행

프로젝트에 포함된 Docker 설정 사용:

```bash
# 컨테이너 빌드 및 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 마이그레이션 실행
docker-compose exec web python manage.py migrate

# 슈퍼유저 생성
docker-compose exec web python manage.py createsuperuser

# 중지
docker-compose down
```

---

## ✅ 설치 확인

### API 테스트

```bash
# 헬스체크
curl http://localhost:8000/api/health/

# 상품 목록
curl http://localhost:8000/api/products/
```

### Admin 접속

브라우저에서:
```
http://localhost:8000/admin/
```

### Swagger UI 접속

브라우저에서:
```
http://localhost:8000/api/schema/swagger-ui/
```

---

## 🚨 문제 해결

### Port already in use

```bash
# 8000번 포트를 사용 중인 프로세스 확인
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# 프로세스 종료 후 다시 실행
```

### Redis 연결 오류

```bash
# Redis 서버 상태 확인
redis-cli ping

# Redis 시작
brew services start redis  # macOS
sudo systemctl start redis  # Linux
```

### 마이그레이션 오류

```bash
# 마이그레이션 파일 삭제 후 재생성
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete
python manage.py makemigrations
python manage.py migrate
```

### 패키지 설치 오류

```bash
# pip 업그레이드
pip install --upgrade pip

# 캐시 삭제 후 재설치
pip cache purge
pip install -r requirements.txt --no-cache-dir
```

---

## 📚 다음 단계

설치가 완료되었다면:

1. **[API 문서](API.md)** - API 사용법 학습
2. **[데이터 모델](MODELS.md)** - 데이터 구조 이해
3. **[테스트 가이드](TESTING.md)** - 테스트 코드 작성

---

## 💡 추가 참고

- [Django 공식 문서](https://docs.djangoproject.com/)
- [DRF 공식 문서](https://www.django-rest-framework.org/)
- [Celery 공식 문서](https://docs.celeryproject.org/)
- [토스페이먼츠 문서](https://docs.tosspayments.com/)