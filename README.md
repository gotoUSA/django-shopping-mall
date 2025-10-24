# Django Shopping Mall API

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2.4-092E20?style=for-the-badge&logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.16-ff1709?style=for-the-badge&logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.5-37814A?style=for-the-badge&logo=celery&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)

> 🛍️ **Django REST Framework 기반의 프로덕션 레디 이커머스 백엔드 API**

토스페이먼츠 결제, JWT 인증, 소셜 로그인, 포인트 시스템, 비동기 작업 처리 등 실제 쇼핑몰 운영에 필요한 모든 기능을 구현한 엔터프라이즈급 RESTful API 서버입니다.

---

## 📌 Table of Contents

- [주요 기능](#-주요-기능)
- [기술 스택](#-기술-스택)
- [시스템 아키텍처](#-시스템-아키텍처)
- [시작하기](#-시작하기)
  - [로컬 환경 설치](#1-로컬-환경-설치)
  - [Docker 환경 설치](#2-docker-환경-설치-추천)
- [프로젝트 구조](#-프로젝트-구조)
- [API 문서](#-api-문서)
- [주요 모델](#-주요-모델)
- [환경 설정](#-환경-설정)
- [테스트](#-테스트)
- [개발 도구](#-개발-도구)
- [배포](#-배포)
- [트러블슈팅](#-트러블슈팅)

---

## ✨ 주요 기능

### 🔐 **인증 & 보안**
- **JWT 토큰 인증** (Access Token 30분 / Refresh Token 7일)
- **소셜 로그인** (Google, Kakao, Naver OAuth 2.0)
- 토큰 블랙리스트 자동 관리
- 이메일 인증 시스템 (비동기 발송)
- 마지막 로그인 IP 추적 및 보안 로그
- 미인증 계정 자동 정리 (7일)

### 💳 **결제 시스템**
- **토스페이먼츠 완전 통합** (카드/계좌이체/가상계좌)
- 실시간 웹훅을 통한 결제 상태 동기화
- 부분 취소 및 전체 환불 처리
- 결제 실패 자동 복구 메커니즘
- 결제 로그 상세 추적

### 📦 **상품 관리**
- 무한 depth 계층형 카테고리 (django-mptt)
- 다중 이미지 업로드 (최대 5개)
- 실시간 재고 추적 및 동시성 제어 (select_for_update)
- 5점 평점 시스템 및 리뷰 관리
- 상품 문의/답변 시스템
- 찜하기(Wishlist) 기능

### 🛒 **장바구니 & 주문**
- 실시간 재고 검증 및 가격 확인
- 일괄 상품 추가/수정/삭제
- 게스트 장바구니 지원
- 주문 상태 자동 관리 (결제대기→결제완료→배송준비→배송중→배송완료)
- 주문 취소 및 환불 처리

### 💰 **포인트 시스템**
- 등급별 차등 적립 (Bronze 1% ~ VIP 5%)
- 포인트 유효기간 관리 (1년)
- FIFO 방식 포인트 차감
- 상세 적립/사용/만료 이력 추적
- 만료 예정 포인트 자동 이메일 알림 (7일 전)
- 매일 자동 만료 처리 (Celery Beat)

### 🔔 **알림 시스템**
- 실시간 알림 (주문, 배송, 문의 답변 등)
- 읽음/안읽음 상태 관리
- 알림 일괄 삭제 및 관리

### ⚡ **성능 & 비동기 처리**
- **Celery** 기반 비동기 작업 처리
  - 이메일 발송 (실패 시 5분마다 재시도)
  - 포인트 만료 처리 (매일 새벽 2시)
  - 미인증 계정 정리 (매일 새벽 3시)
  - 오래된 로그 정리 (주 1회)
- **Redis** 캐싱으로 응답 속도 개선
- Django ORM 최적화 (select_related, prefetch_related)
- 페이지네이션 및 필터링 최적화

---

## 🛠 기술 스택

### Backend Core
| Component | Technology | Version |
|-----------|------------|---------|
| **Language** | Python | 3.12 |
| **Framework** | Django | 5.2.4 |
| **REST API** | Django REST Framework | 3.16 |
| **Authentication** | Simple JWT | 5.5.1 |
| **Social Auth** | django-allauth | 65.12 |

### Database & Cache
| Component | Technology | Version |
|-----------|------------|---------|
| **Development DB** | SQLite | 3.x |
| **Production DB** | PostgreSQL | 15 (Ready) |
| **Cache & Queue** | Redis | 7 |

### Async & Tasks
| Component | Technology | Version |
|-----------|------------|---------|
| **Task Queue** | Celery | 5.5.3 |
| **Scheduler** | django-celery-beat | 2.8 |
| **Monitoring** | Flower | 2.0.1 |

### Payment & External APIs
| Component | Technology |
|-----------|------------|
| **Payment Gateway** | Toss Payments API |
| **Webhook** | Real-time Payment Sync |

### Development Tools
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Testing** | pytest, pytest-django | 단위/통합 테스트 |
| **Code Quality** | black, isort, flake8 | 코드 포맷팅 & 린팅 |
| **Pre-commit** | pre-commit hooks | Git commit 전 자동 검사 |
| **API Docs** | drf-yasg (Swagger/ReDoc) | 자동 API 문서 생성 |
| **Debug** | django-debug-toolbar | 개발 환경 디버깅 |

### DevOps
| Component | Technology |
|-----------|------------|
| **Containerization** | Docker, Docker Compose |
| **Process Management** | Gunicorn (Production Ready) |

---

## 🏗 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client (Frontend)                       │
│                    (React, Vue, Mobile App)                     │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Django REST Framework                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   Auth API   │  │ Product API  │  │ Payment API  │           │
│  │  (JWT/OAuth) │  │  (CRUD)      │  │  (Toss)      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└────────┬─────────────────┬─────────────────┬────────────────────┘
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────────┐ ┌──────────────────┐
│   PostgreSQL    │ │      Redis      │ │  Toss Payments   │
│  (Main DB)      │ │ (Cache/Queue)   │ │   (Webhook)      │
└─────────────────┘ └────────┬────────┘ └──────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Celery Worker  │
                    │  (Async Tasks)  │
                    │  + Celery Beat  │
                    │  (Scheduler)    │
                    └─────────────────┘
```

---

## 🚀 시작하기

### Prerequisites

**필수 요구사항:**
- Python 3.12 이상
- Git

**선택 (로컬 환경):**
- PostgreSQL (프로덕션용, 개발은 SQLite 사용 가능)
- Redis Server (Celery용)

**선택 (Docker 환경 - 추천):**
- Docker
- Docker Compose

---

### 1. 로컬 환경 설치

#### 1.1 프로젝트 클론
```bash
git clone https://github.com/gotoUSA/django-shopping-mall.git
cd django-shopping-mall
```

#### 1.2 가상환경 설정
```bash
# 가상환경 생성
python -m venv venv

# 활성화
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

#### 1.3 의존성 설치
```bash
# 운영 패키지만 설치
pip install -r requirements.txt

# 또는 개발 패키지 포함 설치 (추천)
pip install -r requirements-dev.txt
```

#### 1.4 환경 변수 설정
```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집 (필수 설정)
nano .env  # 또는 원하는 에디터 사용
```

**필수 환경 변수:**
```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here  # 반드시 변경!
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# 토스페이먼츠 (테스트 키)
TOSS_CLIENT_KEY=test_ck_...
TOSS_SECRET_KEY=test_sk_...
TOSS_WEBHOOK_SECRET=...

# Redis (로컬 Redis 설치 필요)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
```

**Secret Key 생성 방법:**
```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

#### 1.5 데이터베이스 설정
```bash
# 마이그레이션 실행
python manage.py migrate

# 슈퍼유저 생성
python manage.py createsuperuser

# 테스트 데이터 생성 (선택사항)
python manage.py create_test_data --preset basic
```

**테스트 데이터 프리셋:**
- `minimal`: 최소 데이터 (개발 테스트용)
- `basic`: 기본 데이터 (일반 테스트용) - 추천
- `full`: 전체 데이터 (성능 테스트용)

#### 1.6 Redis 실행 (별도 터미널)
```bash
# Redis 설치 후 실행
redis-server

# 또는 Docker로 Redis만 실행
docker run -d -p 6379:6379 redis:7-alpine
```

#### 1.7 서버 실행

**터미널 1 - Django 개발 서버**
```bash
python manage.py runserver
```

**터미널 2 - Celery Worker**
```bash
celery -A myproject worker -l info
```

**터미널 3 - Celery Beat (스케줄러, 선택사항)**
```bash
celery -A myproject beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

**터미널 4 - Flower (Celery 모니터링, 선택사항)**
```bash
celery -A myproject flower
```

#### 1.8 접속 확인
```bash
# API 서버
http://localhost:8000/

# Admin 페이지
http://localhost:8000/admin/

# Swagger API 문서
http://localhost:8000/swagger/

# ReDoc API 문서
http://localhost:8000/redoc/

# Flower (Celery 모니터링)
http://localhost:5555/
```

---

### 2. Docker 환경 설치 (추천)

Docker를 사용하면 PostgreSQL, Redis, Celery를 모두 자동으로 설정할 수 있습니다.

#### 2.1 프로젝트 클론
```bash
git clone https://github.com/gotoUSA/django-shopping-mall.git
cd django-shopping-mall
```

#### 2.2 환경 변수 설정
```bash
# .env 파일 생성
cp .env.example .env

# Docker 환경에 맞게 수정
nano .env
```

**Docker 환경 변수 예시:**
```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# PostgreSQL (docker-compose.yml과 동일하게)
DATABASE_ENGINE=django.db.backends.postgresql
DATABASE_NAME=shopping_db
DATABASE_USER=shopping_user
DATABASE_PASSWORD=shopping_pass
DATABASE_HOST=db  # ← Docker 서비스명
DATABASE_PORT=5432

# Redis (docker-compose.yml과 동일하게)
REDIS_URL=redis://redis:6379/0  # ← Docker 서비스명
CELERY_BROKER_URL=redis://redis:6379/0

# 토스페이먼츠
TOSS_CLIENT_KEY=test_ck_...
TOSS_SECRET_KEY=test_sk_...
```

#### 2.3 Docker Compose로 실행
```bash
# 모든 서비스 빌드 및 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 특정 서비스만 로그 확인
docker-compose logs -f web
```

#### 2.4 데이터베이스 초기화
```bash
# 마이그레이션 실행
docker-compose exec web python manage.py migrate

# 슈퍼유저 생성
docker-compose exec web python manage.py createsuperuser

# 테스트 데이터 생성
docker-compose exec web python manage.py create_test_data --preset basic
```

#### 2.5 Docker 서비스 관리
```bash
# 전체 서비스 중지
docker-compose stop

# 전체 서비스 시작
docker-compose start

# 전체 서비스 재시작
docker-compose restart

# 특정 서비스만 재시작
docker-compose restart web

# 전체 서비스 종료 및 삭제
docker-compose down

# 볼륨까지 모두 삭제 (데이터베이스 초기화)
docker-compose down -v
```

#### 2.6 Docker 접속 정보
```bash
# API 서버
http://localhost:8000/

# Admin 페이지
http://localhost:8000/admin/

# Swagger
http://localhost:8000/swagger/

# PostgreSQL (외부 접속)
localhost:5432

# Redis (외부 접속)
localhost:6373  # ← 포트 주의! (내부는 6379)

# Flower
http://localhost:5555/
```

**Docker Compose 서비스 구성:**
- `db` - PostgreSQL 15
- `redis` - Redis 7
- `web` - Django 애플리케이션
- `celery_worker` - Celery Worker
- `celery_beat` - Celery Beat 스케줄러
- `flower` - Celery 모니터링

---

## 📁 프로젝트 구조

```
django-shopping-mall/
│
├── 📂 myproject/                    # Django 프로젝트 설정
│   ├── __init__.py                 # Celery 앱 로드
│   ├── settings.py                 # 전체 설정
│   ├── urls.py                     # 루트 URL (Admin, Swagger)
│   ├── celery.py                   # Celery 설정 & Beat 스케줄
│   ├── wsgi.py                     # WSGI 진입점
│   └── asgi.py                     # ASGI 진입점
│
├── 📂 shopping/                     # 메인 애플리케이션
│   │
│   ├── 📂 models/                   # 데이터 모델 (분리)
│   │   ├── __init__.py             # 모델 통합 import
│   │   ├── user.py                 # 사용자 (확장 User 모델)
│   │   ├── product.py              # 상품/카테고리/리뷰
│   │   ├── product_qa.py           # 상품 문의/답변
│   │   ├── cart.py                 # 장바구니/아이템
│   │   ├── order.py                # 주문/주문아이템
│   │   ├── payment.py              # 결제/결제로그
│   │   ├── point.py                # 포인트 이력
│   │   ├── notification.py         # 알림
│   │   └── email_verification.py   # 이메일 인증/로그
│   │
│   ├── 📂 views/                    # API 뷰 (분리)
│   │   ├── auth_views.py           # 인증 (회원가입/로그인/프로필)
│   │   ├── social_auth_views.py    # 소셜 로그인
│   │   ├── product_views.py        # 상품 CRUD
│   │   ├── cart_views.py           # 장바구니 관리
│   │   ├── order_views.py          # 주문 관리
│   │   ├── payment_views.py        # 결제 처리
│   │   ├── point_views.py          # 포인트 조회
│   │   ├── wishlist_views.py       # 찜하기
│   │   ├── notification_views.py   # 알림
│   │   └── webhook_views.py        # 토스 웹훅
│   │
│   ├── 📂 serializers/              # DRF Serializer (분리)
│   │   ├── user_serializers.py
│   │   ├── product_serializers.py
│   │   ├── cart_serializers.py
│   │   ├── order_serializers.py
│   │   ├── payment_serializers.py
│   │   └── ...
│   │
│   ├── 📂 services/                 # 비즈니스 로직 레이어
│   │   └── point_service.py        # 포인트 적립/사용/만료 로직
│   │
│   ├── 📂 utils/                    # 유틸리티
│   │   ├── toss_payment.py         # 토스페이먼츠 API 클라이언트
│   │   └── email_utils.py          # 이메일 발송 헬퍼
│   │
│   ├── 📂 tasks/                    # Celery 태스크 (분리)
│   │   ├── __init__.py
│   │   ├── email_tasks.py          # 이메일 발송/재시도
│   │   ├── point_tasks.py          # 포인트 만료/알림
│   │   └── cleanup_tasks.py        # 데이터 정리
│   │
│   ├── 📂 tests/                    # 테스트 코드
│   │   ├── conftest.py             # pytest Fixture 정의
│   │   ├── test_auth.py
│   │   ├── test_products.py
│   │   ├── test_cart.py
│   │   ├── test_orders.py
│   │   ├── test_payments.py
│   │   ├── test_points.py
│   │   ├── test_toss_webhook.py
│   │   ├── test_integration_flow.py
│   │   └── test_cleanup_tasks.py
│   │
│   ├── 📂 management/commands/      # Django 커맨드
│   │   ├── create_test_data.py     # 테스트 데이터 생성
│   │   └── test_point_expiry.py    # 포인트 만료 테스트
│   │
│   ├── admin.py                     # Django Admin 설정
│   ├── urls.py                      # shopping 앱 URL
│   └── apps.py
│
├── 📂 logs/                         # 로그 파일 (자동 생성)
│   └── django.log
│
├── 📄 manage.py                     # Django 관리 스크립트
├── 📄 requirements.txt              # 운영 패키지
├── 📄 requirements-dev.txt          # 개발 패키지 (테스트/린팅)
├── 📄 Dockerfile                    # Docker 이미지 정의
├── 📄 docker-compose.yml            # Docker Compose 설정
├── 📄 .env.example                  # 환경 변수 템플릿
├── 📄 .gitignore
├── 📄 pyproject.toml                # Black/isort/pytest 설정
├── 📄 .flake8                       # Flake8 설정
├── 📄 .pre-commit-config.yaml      # Pre-commit hooks
└── 📄 README.md
```

---

## 📖 API 문서

### 자동 생성 API 문서

프로젝트는 **drf-yasg**를 사용하여 OpenAPI 3.0 스펙의 API 문서를 자동 생성합니다.

**접속 방법:**
- **Swagger UI**: http://localhost:8000/swagger/
  - 인터랙티브 API 테스트 가능
  - Try it out 기능으로 직접 요청 테스트
  
- **ReDoc**: http://localhost:8000/redoc/
  - 깔끔한 문서 형식
  - 읽기 전용

### 주요 API 엔드포인트

#### 🔐 인증 (Authentication)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/auth/register/` | 회원가입 | ❌ |
| POST | `/api/auth/login/` | 로그인 (JWT 발급) | ❌ |
| POST | `/api/auth/logout/` | 로그아웃 (토큰 블랙리스트) | ✅ |
| POST | `/api/auth/token/refresh/` | Access Token 갱신 | ❌ (Refresh Token 필요) |
| GET | `/api/auth/token/verify/` | 토큰 유효성 확인 | ✅ |
| GET/PUT/PATCH | `/api/auth/profile/` | 프로필 조회/수정 | ✅ |
| POST | `/api/auth/password/change/` | 비밀번호 변경 | ✅ |
| POST | `/api/auth/withdraw/` | 회원 탈퇴 | ✅ |

#### 📧 이메일 인증

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/email/send/` | 인증 이메일 발송 |
| POST | `/api/auth/email/verify/` | 이메일 인증 확인 |
| POST | `/api/auth/email/resend/` | 인증 이메일 재발송 |
| GET | `/api/auth/email/status/` | 인증 상태 조회 |

#### 🌐 소셜 로그인

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/social/google/` | Google 로그인 |
| POST | `/api/auth/social/kakao/` | Kakao 로그인 |
| POST | `/api/auth/social/naver/` | Naver 로그인 |

#### 📦 상품 (Products)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/products/` | 상품 목록 | ❌ |
| POST | `/api/products/` | 상품 생성 | ✅ (판매자) |
| GET | `/api/products/{id}/` | 상품 상세 | ❌ |
| PUT/PATCH | `/api/products/{id}/` | 상품 수정 | ✅ (판매자) |
| DELETE | `/api/products/{id}/` | 상품 삭제 | ✅ (판매자) |
| GET | `/api/products/{id}/reviews/` | 상품 리뷰 목록 | ❌ |
| POST | `/api/products/{id}/add_review/` | 리뷰 작성 | ✅ |
| GET | `/api/products/popular/` | 인기 상품 | ❌ |
| GET | `/api/products/best_rating/` | 평점 높은 상품 | ❌ |
| GET | `/api/products/low_stock/` | 재고 부족 상품 | ✅ (관리자) |

**검색 및 필터링:**
```bash
# 상품 검색
GET /api/products/?search=노트북

# 카테고리 필터
GET /api/products/?category=1

# 가격 범위
GET /api/products/?min_price=10000&max_price=50000

# 정렬 (최신순, 가격순, 인기순)
GET /api/products/?ordering=-created_at
GET /api/products/?ordering=price
GET /api/products/?ordering=-sold_count

# 재고 있는 상품만
GET /api/products/?in_stock=true

# 판매자별 상품
GET /api/products/?seller=3

# 페이지네이션
GET /api/products/?page=2&page_size=20
```

#### 🗂 카테고리 (Categories)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/categories/` | 카테고리 목록 |
| GET | `/api/categories/{id}/` | 카테고리 상세 |
| GET | `/api/categories/tree/` | 계층형 카테고리 트리 |
| GET | `/api/categories/{id}/products/` | 카테고리별 상품 |

#### 💬 상품 문의 (Product Q&A)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/products/{product_id}/questions/` | 문의 목록 | ❌ |
| POST | `/api/products/{product_id}/questions/` | 문의 작성 | ✅ |
| GET | `/api/products/{product_id}/questions/{id}/` | 문의 상세 | ✅ |
| PATCH | `/api/products/{product_id}/questions/{id}/` | 문의 수정 | ✅ (작성자) |
| DELETE | `/api/products/{product_id}/questions/{id}/` | 문의 삭제 | ✅ (작성자) |
| POST | `/api/products/{product_id}/questions/{id}/answer/` | 답변 작성 | ✅ (판매자) |
| GET | `/api/my/questions/` | 내 문의 목록 | ✅ |

#### 🛒 장바구니 (Cart)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/cart/` | 내 장바구니 조회 | ✅ |
| GET | `/api/cart/summary/` | 장바구니 요약 (총액, 개수) | ✅ |
| POST | `/api/cart/add_item/` | 상품 추가 | ✅ |
| GET | `/api/cart/items/` | 장바구니 아이템 목록 | ✅ |
| PATCH | `/api/cart/items/{id}/` | 아이템 수량 변경 | ✅ |
| DELETE | `/api/cart/items/{id}/` | 아이템 삭제 | ✅ |
| POST | `/api/cart/clear/` | 장바구니 비우기 | ✅ |
| POST | `/api/cart/bulk_add/` | 여러 상품 일괄 추가 | ✅ |
| GET | `/api/cart/check_stock/` | 재고 확인 | ✅ |

#### 📋 주문 (Orders)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/orders/` | 주문 목록 | ✅ |
| POST | `/api/orders/` | 주문 생성 | ✅ |
| GET | `/api/orders/{id}/` | 주문 상세 | ✅ |
| PATCH | `/api/orders/{id}/` | 주문 수정 | ✅ |
| POST | `/api/orders/{id}/cancel/` | 주문 취소 | ✅ |

#### 💳 결제 (Payments)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/payments/request/` | 결제 요청 (결제창 열기 전) | ✅ |
| POST | `/api/payments/confirm/` | 결제 승인 (결제창 완료 후) | ✅ |
| POST | `/api/payments/cancel/` | 결제 취소/환불 | ✅ |
| GET | `/api/payments/` | 내 결제 목록 | ✅ |
| GET | `/api/payments/{id}/` | 결제 상세 정보 | ✅ |

#### 🔔 웹훅 (Webhooks)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/webhooks/toss/` | 토스페이먼츠 웹훅 수신 |

#### 💰 포인트 (Points)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/points/my/` | 내 포인트 조회 | ✅ |
| GET | `/api/points/history/` | 포인트 이력 | ✅ |
| POST | `/api/points/check/` | 사용 가능 포인트 확인 | ✅ |
| GET | `/api/points/expiring/` | 만료 예정 포인트 | ✅ |
| GET | `/api/points/statistics/` | 포인트 통계 | ✅ |

#### ❤️ 찜하기 (Wishlist)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/wishlist/` | 찜 목록 조회 | ✅ |
| POST | `/api/wishlist/toggle/` | 찜하기 토글 (추가/제거) | ✅ |
| POST | `/api/wishlist/add/` | 찜 목록에 추가 | ✅ |
| DELETE | `/api/wishlist/remove/` | 찜 목록에서 제거 | ✅ |
| POST | `/api/wishlist/bulk_add/` | 여러 상품 일괄 찜하기 | ✅ |
| DELETE | `/api/wishlist/clear/` | 찜 목록 전체 삭제 | ✅ |
| GET | `/api/wishlist/check/` | 특정 상품 찜 상태 확인 | ✅ |
| GET | `/api/wishlist/stats/` | 찜 목록 통계 | ✅ |
| POST | `/api/wishlist/move_to_cart/` | 찜→장바구니 이동 | ✅ |

#### 🔔 알림 (Notifications)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/notifications/` | 알림 목록 | ✅ |
| GET | `/api/notifications/{id}/` | 알림 상세 | ✅ |
| GET | `/api/notifications/unread/` | 읽지 않은 알림 개수 | ✅ |
| POST | `/api/notifications/mark_read/` | 알림 읽음 처리 | ✅ |
| DELETE | `/api/notifications/clear/` | 읽은 알림 삭제 | ✅ |

---

## 🗃 주요 모델

### User (사용자)
```python
# 확장된 Django User 모델
- username, email, password (기본)
- phone_number: 휴대폰 번호
- address, postal_code: 배송지 정보
- points: 보유 포인트
- membership_level: 회원 등급 (bronze/silver/gold/vip)
- is_email_verified: 이메일 인증 여부
- last_login_ip: 마지막 로그인 IP
- agree_marketing_email/sms: 마케팅 수신 동의
```

### Product (상품)
```python
- name: 상품명
- slug: URL 슬러그
- category: 카테고리 (ForeignKey)
- seller: 판매자 (ForeignKey → User)
- price: 가격
- stock: 재고
- sold_count: 판매 수량
- sku: 재고 관리 코드
- description: 상세 설명
- is_active: 판매 여부
- average_rating: 평균 평점 (계산 필드)
```

### Category (카테고리)
```python
# django-mptt로 계층 구조 지원
- name: 카테고리명
- slug: URL 슬러그
- parent: 상위 카테고리
- ordering: 정렬 순서
- is_active: 활성 여부
```

### Cart & CartItem (장바구니)
```python
# Cart
- user: 사용자 (ForeignKey)
- session_key: 게스트용 세션 키
- is_active: 활성 상태

# CartItem
- cart: 장바구니 (ForeignKey)
- product: 상품 (ForeignKey)
- quantity: 수량
- added_at: 추가 시간
```

### Order & OrderItem (주문)
```python
# Order
- user: 주문자
- order_number: 주문번호 (자동 생성)
- status: 주문 상태 (pending/paid/preparing/shipped/delivered/canceled/refunded)
- total_amount: 총 금액
- payment_method: 결제 수단
- shipping_*: 배송 정보 필드들

# OrderItem
- order: 주문 (ForeignKey)
- product: 상품 (ForeignKey)
- quantity: 수량
- price: 주문 당시 가격 (스냅샷)
```

### Payment (결제)
```python
- order: 연결된 주문 (OneToOne)
- amount: 결제 금액
- status: 결제 상태 (pending/done/canceled/failed)
- method: 결제 수단 (카드/계좌이체/가상계좌)
- payment_key: 토스 결제 키
- toss_order_id: 토스 주문 ID
- approved_at: 승인 시간
- card_company, card_number: 카드 정보
- is_canceled: 취소 여부
- cancel_reason: 취소 사유
```

### PointHistory (포인트 이력)
```python
- user: 사용자
- points: 포인트 금액 (적립: +, 사용/만료: -)
- type: 유형 (earn/use/expire)
- description: 설명
- remaining_points: 남은 포인트
- expires_at: 만료일 (적립 시 설정)
- created_at: 생성 시간
```

### Notification (알림)
```python
- user: 수신자
- title: 알림 제목
- message: 알림 내용
- type: 알림 유형 (order/payment/inquiry 등)
- is_read: 읽음 여부
- read_at: 읽은 시간
- created_at: 생성 시간
```

### ProductReview (상품 리뷰)
```python
- product: 상품
- user: 작성자
- rating: 평점 (1~5)
- content: 리뷰 내용
- created_at: 작성 시간
```

### ProductQuestion & ProductAnswer (상품 문의)
```python
# ProductQuestion
- product: 상품
- user: 질문자
- title: 제목
- content: 내용
- is_answered: 답변 여부

# ProductAnswer
- question: 질문 (OneToOne)
- content: 답변 내용
- answered_by: 답변자 (판매자)
```

### EmailVerificationToken (이메일 인증)
```python
- user: 사용자
- token: 인증 토큰 (UUID)
- expires_at: 만료 시간
- is_used: 사용 여부
- used_at: 사용 시간
```

---

## ⚙️ 환경 설정

### 환경 변수 전체 목록

`.env.example` 파일에 모든 환경 변수가 설명과 함께 포함되어 있습니다.

#### Django 기본 설정
```env
DJANGO_SECRET_KEY=your-secret-key-here  # 필수! 반드시 변경
DJANGO_DEBUG=True  # 프로덕션: False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1  # 콤마로 구분
```

#### 데이터베이스 설정
```env
# SQLite (기본값, 개발용)
DATABASE_ENGINE=django.db.backends.sqlite3

# PostgreSQL (프로덕션)
DATABASE_ENGINE=django.db.backends.postgresql
DATABASE_NAME=shopping_db
DATABASE_USER=shopping_user
DATABASE_PASSWORD=your-db-password
DATABASE_HOST=localhost  # Docker: db
DATABASE_PORT=5432
```

#### Redis & Celery
```env
# 로컬 환경
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0

# Docker 환경
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
```

#### 토스페이먼츠
```env
# 테스트 키 (test_로 시작)
TOSS_CLIENT_KEY=test_ck_YOUR_CLIENT_KEY
TOSS_SECRET_KEY=test_sk_YOUR_SECRET_KEY
TOSS_WEBHOOK_SECRET=YOUR_WEBHOOK_SECRET

# 운영 키 (live_로 시작, 프로덕션)
TOSS_CLIENT_KEY=live_ck_YOUR_CLIENT_KEY
TOSS_SECRET_KEY=live_sk_YOUR_SECRET_KEY
```

#### 이메일 설정 (선택사항)
```env
# 개발 환경: 콘솔에 출력
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# 프로덕션: SMTP 사용 (Gmail 예시)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password  # Gmail 앱 비밀번호
DEFAULT_FROM_EMAIL=noreply@shopping.com
```

#### 소셜 로그인 (선택사항)
```env
# Google OAuth 2.0
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Kakao
KAKAO_REST_API_KEY=your_kakao_rest_api_key
KAKAO_CLIENT_SECRET=your_kakao_client_secret

# Naver
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret

# 리다이렉트 URI
SOCIAL_LOGIN_REDIRECT_URI=http://localhost:8000/social/test/
```

#### 프론트엔드 URL
```env
# 결제 완료 후 리다이렉트 URL
FRONTEND_URL=http://localhost:3000  # 개발
FRONTEND_URL=https://yourdomain.com  # 프로덕션
```

---

## 🧪 테스트

이 프로젝트는 **pytest**와 **pytest-django**를 사용하여 테스트합니다.

### 테스트 실행

```bash
# 전체 테스트 실행
pytest

# 특정 앱만 테스트
pytest shopping/tests/

# 특정 파일만 테스트
pytest shopping/tests/test_auth.py

# 특정 테스트만 실행
pytest shopping/tests/test_auth.py::TestLoginView::test_login_success

# 커버리지 측정과 함께 실행
pytest --cov=shopping --cov-report=html

# 병렬 실행 (속도 향상)
pytest -n auto
```

### 테스트 커버리지

```bash
# 커버리지 리포트 생성
pytest --cov=shopping --cov-report=html --cov-report=term-missing

# HTML 리포트 확인
# htmlcov/index.html 파일을 브라우저에서 열기
```

**현재 목표 커버리지: 70% 이상**

### Fixture 활용

`shopping/tests/conftest.py`에 다양한 Fixture가 정의되어 있습니다:

```python
# 사용 예시
def test_create_order(authenticated_client, user, product, shipping_data):
    """주문 생성 테스트"""
    # authenticated_client: JWT 인증된 클라이언트
    # user: 테스트 사용자
    # product: 테스트 상품
    # shipping_data: 배송 정보 dict
    
    response = authenticated_client.post('/api/orders/', shipping_data)
    assert response.status_code == 201
```

**주요 Fixture:**
- `api_client` - APIClient 인스턴스
- `authenticated_client` - JWT 인증된 클라이언트
- `user` - 일반 사용자
- `seller_user` - 판매자 사용자
- `product` - 테스트 상품
- `cart` - 장바구니
- `order` - 주문
- `payment` - 결제
- `mock_toss_client` - 토스 API Mock

### Django 테스트 실행 (기존 방식)

```bash
# Django 기본 테스트 러너로도 실행 가능
python manage.py test

# 특정 앱만
python manage.py test shopping.tests
```

---

## 🔧 개발 도구

### 코드 품질 도구

프로젝트는 다음 도구들을 사용하여 코드 품질을 유지합니다:

#### Black (코드 포맷팅)
```bash
# 전체 코드 포맷팅
black .

# 특정 파일만
black shopping/models/user.py

# 확인만 하고 변경하지 않음
black --check .
```

#### isort (import 정렬)
```bash
# import 정렬
isort .

# 확인만
isort --check .
```

#### Flake8 (코드 스타일 검사)
```bash
# 코드 스타일 체크
flake8

# 특정 디렉토리만
flake8 shopping/
```

#### 전체 검사 실행
```bash
# 한 번에 모든 검사 실행
black . && isort . && flake8
```

### Pre-commit Hooks

Git commit 전에 자동으로 코드 검사를 실행합니다.

```bash
# Pre-commit 설치
pip install pre-commit

# Git hooks 설치
pre-commit install

# 수동으로 전체 파일 검사
pre-commit run --all-files
```

**Pre-commit이 실행하는 검사:**
1. autoflake - 사용하지 않는 import 제거
2. isort - import 정렬
3. black - 코드 포맷팅
4. flake8 - 코드 스타일 검사
5. trailing-whitespace - 줄 끝 공백 제거
6. check-yaml - YAML 문법 검사
7. check-json - JSON 문법 검사

### Django Debug Toolbar

개발 환경에서 SQL 쿼리 및 성능 분석:

```python
# DEBUG=True일 때만 활성화
# 접속: http://localhost:8000/__debug__/
```

---

## 🚀 배포

### 프로덕션 체크리스트

프로덕션 배포 전 반드시 확인하세요:

```env
# ❌ 개발 환경
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=django-insecure-...

# ✅ 프로덕션 환경
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=your-secure-random-key
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# 데이터베이스
DATABASE_ENGINE=django.db.backends.postgresql
DATABASE_HOST=your-rds-endpoint.amazonaws.com

# Redis
REDIS_URL=redis://your-elasticache-endpoint:6379/0

# 토스페이먼츠 (운영 키)
TOSS_CLIENT_KEY=live_ck_...
TOSS_SECRET_KEY=live_sk_...

# HTTPS 강제
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

### 정적 파일 수집

```bash
# 정적 파일 수집 (배포 전 필수)
python manage.py collectstatic --noinput
```

### Gunicorn으로 실행

```bash
# 설치
pip install gunicorn

# 실행 (4 workers)
gunicorn myproject.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
```

### Docker 프로덕션 빌드

```bash
# 프로덕션 이미지 빌드
docker build -t shopping-mall-api:latest .

# 실행
docker run -p 8000:8000 --env-file .env shopping-mall-api:latest
```

---

## 🔍 트러블슈팅

### 자주 발생하는 문제

#### 1. Celery Worker가 작업을 처리하지 않음

**문제:** 결제 후 포인트가 적립되지 않음

**해결:**
```bash
# Redis 연결 확인
redis-cli ping
# 응답: PONG

# Celery Worker 로그 확인
celery -A myproject worker -l debug

# .env에서 Redis URL 확인
CELERY_BROKER_URL=redis://localhost:6379/0  # 로컬
CELERY_BROKER_URL=redis://redis:6379/0      # Docker
```

#### 2. 토스 웹훅이 실행되지 않음

**문제:** 결제 승인 후 주문 상태가 변경되지 않음

**해결:**
1. `.env`에서 `TOSS_WEBHOOK_SECRET` 확인
2. 토스 대시보드에서 웹훅 URL 확인: `https://yourdomain.com/api/webhooks/toss/`
3. 로그 확인:
   ```bash
   tail -f logs/django.log | grep webhook
   ```

#### 3. 테스트 실패: Celery 동기 실행 안 됨

**문제:** pytest 실행 시 Celery 작업이 대기 중

**해결:**
`conftest.py`에서 자동 설정되지만, 수동 확인:
```python
# settings.py에 추가
import sys
if 'test' in sys.argv:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
```

#### 4. Docker Compose에서 DB 연결 실패

**문제:** `django.db.utils.OperationalError: could not connect to server`

**해결:**
```bash
# DB 컨테이너 상태 확인
docker-compose ps

# DB 로그 확인
docker-compose logs db

# .env 확인
DATABASE_HOST=db  # ← 반드시 'db' (서비스명)
DATABASE_PORT=5432

# 완전 재시작
docker-compose down -v
docker-compose up -d
```

#### 5. Redis 포트 충돌

**문제:** Docker Redis 접근 시 연결 거부

**해결:**
```bash
# docker-compose.yml에서 외부 포트 확인
redis:
  ports:
    - "6373:6379"  # ← 외부: 6373, 내부: 6379

# 로컬에서 Docker Redis 접근
REDIS_URL=redis://localhost:6373/0  # 6373 사용!

# 컨테이너 내부에서는
REDIS_URL=redis://redis:6379/0      # 6379 사용
```

#### 6. Migration 충돌

**문제:** `django.db.migrations.exceptions.InconsistentMigrationHistory`

**해결:**
```bash
# 방법 1: 마이그레이션 초기화 (개발 환경)
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete
python manage.py makemigrations
python manage.py migrate

# 방법 2: 특정 앱만 초기화
python manage.py migrate shopping zero
python manage.py migrate shopping
```

#### 7. 정적 파일이 로드되지 않음

**문제:** Admin 페이지 CSS가 깨짐

**해결:**
```bash
# 정적 파일 수집
python manage.py collectstatic --noinput

# settings.py 확인
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# 개발 서버에서는 자동 서빙
# 프로덕션에서는 Nginx 등으로 서빙
```

### 로그 확인

```bash
# Django 로그
tail -f logs/django.log

# Celery 로그
celery -A myproject worker -l info

# Docker 로그
docker-compose logs -f web
docker-compose logs -f celery_worker
```

---

## 📞 문의 및 기여

### 버그 리포트 및 기능 제안

GitHub Issues를 통해 버그 리포트나 기능 제안을 해주세요.

### 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

**코드 스타일:**
- Black (line-length=127)
- isort (profile=black)
- Flake8

**커밋 전 실행:**
```bash
pre-commit run --all-files
pytest
```

---

## 📝 라이센스

This project is private and proprietary.

---

## 🙏 감사의 말

이 프로젝트는 다음 오픈소스 프로젝트들을 사용합니다:
- Django & Django REST Framework
- Celery & Redis
- PostgreSQL
- drf-yasg
- django-allauth
- django-mptt

그리고 많은 훌륭한 오픈소스 커뮤니티 기여자들께 감사드립니다.

---

**Made with ❤️ by Django Shopping Mall Team**

*Last Updated: 2025-10-25*