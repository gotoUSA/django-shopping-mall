# Django Shopping Mall API

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2.4-092E20?style=for-the-badge&logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.14-ff1709?style=for-the-badge&logo=django&logoColor=white)
![JWT](https://img.shields.io/badge/JWT-Auth-000000?style=for-the-badge&logo=jsonwebtokens&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)

> 🛍️ **Django REST Framework를 활용한 확장 가능한 이커머스 플랫폼 백엔드 API**

토스페이먼츠 결제 연동, JWT 인증, 포인트 시스템 등 실제 쇼핑몰 운영에 필요한 모든 기능을 구현한 RESTful API 서버입니다.

## 📌 Table of Contents
- [주요 기능](#-주요-기능)
- [기술 스택](#-기술-스택)
- [시작하기](#-시작하기)
- [프로젝트 구조](#-프로젝트-구조)
- [API 문서](#-api-문서)
- [주요 모델](#-주요-모델)
- [환경 설정](#-환경-설정)
- [테스트](#-테스트)
- [라이센스](#-라이센스)

## ✨ 주요 기능

### 🔐 **인증 & 보안**
- **JWT 토큰 기반 인증** (Access Token 30분 / Refresh Token 7일)
- 토큰 블랙리스트 관리 및 자동 갱신
- 마지막 로그인 IP 추적 및 보안 감사 로그
- 이메일 인증 및 비밀번호 재설정

### 💳 **결제 시스템**
- **토스페이먼츠 완전 통합** (카드/계좌이체/가상계좌)
- 실시간 웹훅을 통한 결제 상태 동기화
- 부분 취소 및 환불 처리
- 결제 실패 자동 복구 메커니즘

### 📦 **상품 관리**
- 무한 depth 계층형 카테고리 시스템
- 다중 이미지 업로드 및 썸네일 자동 생성
- 실시간 재고 추적 및 자동 차감
- 5점 평점 시스템 및 리뷰 관리

### 🛒 **장바구니**
- 실시간 재고 검증
- 일괄 상품 추가/수정/삭제
- 장바구니 상태 자동 동기화
- 게스트 장바구니 → 회원 장바구니 병합

### 💰 **포인트 시스템**
- 등급별 차등 적립 (1~5%)
- 포인트 유효기간 관리 (1년)
- 상세 적립/사용 이력 추적
- 만료 예정 포인트 자동 알림

### ⚡ **성능 최적화**
- **Celery** 기반 비동기 처리 (이메일, 대용량 작업)
- **Redis** 캐싱으로 응답 속도 개선
- Django ORM 최적화 (select_related, prefetch_related)
- 페이지네이션 및 필터링 최적화

## 🛠 기술 스택

| Category | Technologies |
|----------|-------------|
| **Backend Framework** | Python 3.12, Django 5.2.4, Django REST Framework |
| **Authentication** | Simple JWT, Token Blacklist |
| **Database** | SQLite (Development), PostgreSQL (Production Ready) |
| **Payment** | Toss Payments API, Webhook Integration |
| **Async Tasks** | Celery, Redis, Django-Celery-Beat |
| **Testing** | Django TestCase, APITestCase |
| **API Documentation** | drf-spectacular (OpenAPI 3.0) |
| **Security** | CORS Headers, Django Security Middleware |

## 🚀 시작하기

### Prerequisites
- Python 3.12+
- Redis Server (Celery용)
- Git

### Installation

1. **프로젝트 클론**
```bash
git clone https://github.com/gotoUSA/django-shopping-mall.git
cd django-shopping-mall
```

2. **가상환경 설정**
```bash
# 가상환경 생성
python -m venv venv

# 활성화 (Windows)
venv\Scripts\activate

# 활성화 (Mac/Linux)
source venv/bin/activate
```

3. **의존성 설치**
```bash
pip install -r requirements.txt
```

4. **환경 변수 설정**
```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집
# 필수 설정:
# - SECRET_KEY
# - TOSS_CLIENT_KEY
# - TOSS_SECRET_KEY
```

5. **데이터베이스 설정**
```bash
# 마이그레이션 실행
python manage.py migrate

# 슈퍼유저 생성
python manage.py createsuperuser

# 테스트 데이터 생성 (선택사항)
python manage.py create_test_data --preset full
```

6. **서버 실행**
```bash
# Django 개발 서버
python manage.py runserver

# Celery Worker (새 터미널)
celery -A myproject worker -l info

# Celery Beat (새 터미널, 선택사항)
celery -A myproject beat -l info
```

7. **API 테스트**
```bash
# 서버 상태 확인
curl http://localhost:8000/api/health/

# Admin 페이지
http://localhost:8000/admin/
```

## 📁 프로젝트 구조

```
django-shopping-mall/
│
├── 📂 myproject/               # 프로젝트 설정
│   ├── __init__.py
│   ├── settings.py            # Django 설정
│   ├── urls.py               # 루트 URL 설정
│   ├── celery.py            # Celery 설정
│   └── wsgi.py
│
├── 📂 shopping/                # 메인 애플리케이션
│   ├── 📂 models/             # 데이터 모델
│   │   ├── __init__.py
│   │   ├── user.py          # 사용자 모델
│   │   ├── product.py       # 상품/카테고리
│   │   ├── cart.py          # 장바구니
│   │   ├── order.py         # 주문
│   │   └── payment.py       # 결제
│   │
│   ├── 📂 views/              # API 뷰
│   │   ├── auth_views.py    # 인증 관련
│   │   ├── product_views.py # 상품 관련
│   │   ├── cart_views.py    # 장바구니
│   │   ├── order_views.py   # 주문
│   │   └── payment_views.py # 결제
│   │
│   ├── 📂 serializers/        # DRF 시리얼라이저
│   │   └── [모델별 시리얼라이저]
│   │
│   ├── 📂 services/           # 비즈니스 로직
│   │   └── point_service.py  # 포인트 관련 서비스
│   │
│   ├── 📂 utils/              # 유틸리티
│   │   └── toss_payment.py  # 토스페이먼츠 클라이언트
│   │
│   ├── 📂 tasks/              # Celery 태스크
│   ├── 📂 tests/              # 테스트 코드
│   └── 📂 management/         # Django 커맨드
│       └── commands/
│           └── create_test_data.py
│
├── 📄 requirements.txt         # 패키지 의존성
├── 📄 .env.example            # 환경변수 예시
├── 📄 .gitignore
└── 📄 README.md
```

## 📖 API 문서

### 주요 엔드포인트

| Category | Method | Endpoint | Description |
|----------|--------|----------|-------------|
| **Auth** | | | |
| | POST | `/api/auth/register/` | 회원가입 |
| | POST | `/api/auth/login/` | 로그인 |
| | POST | `/api/auth/logout/` | 로그아웃 |
| | POST | `/api/auth/token/refresh/` | 토큰 갱신 |
| | GET/PUT | `/api/auth/profile/` | 프로필 조회/수정 |
| **Products** | | | |
| | GET | `/api/products/` | 상품 목록 |
| | GET | `/api/products/{id}/` | 상품 상세 |
| | POST | `/api/products/{id}/reviews/` | 리뷰 작성 |
| | GET | `/api/categories/tree/` | 카테고리 트리 |
| **Cart** | | | |
| | GET | `/api/cart/` | 장바구니 조회 |
| | POST | `/api/cart/add_item/` | 상품 추가 |
| | PATCH | `/api/cart/items/{id}/` | 수량 변경 |
| | DELETE | `/api/cart/items/{id}/` | 상품 제거 |
| **Orders** | | | |
| | POST | `/api/orders/` | 주문 생성 |
| | GET | `/api/orders/` | 주문 목록 |
| | GET | `/api/orders/{id}/` | 주문 상세 |
| | POST | `/api/orders/{id}/cancel/` | 주문 취소 |
| **Payments** | | | |
| | POST | `/api/payments/request/` | 결제 요청 |
| | POST | `/api/payments/confirm/` | 결제 승인 |
| | POST | `/api/payments/cancel/` | 결제 취소 |
| | GET | `/api/payments/` | 결제 내역 |

### 검색 및 필터링

```bash
# 상품 검색
GET /api/products/?search=노트북

# 카테고리 필터
GET /api/products/?category=1

# 가격 범위
GET /api/products/?min_price=10000&max_price=50000

# 정렬
GET /api/products/?ordering=-created_at

# 페이지네이션
GET /api/products/?page=2&page_size=20
```

## 🗃 주요 모델

| Model | Description | Key Fields |
|-------|-------------|------------|
| **User** | 확장된 사용자 모델 | email, phone, address, points, grade |
| **Product** | 상품 정보 | name, price, stock, category, images |
| **Category** | 계층형 카테고리 | name, parent, slug, ordering |
| **Cart** | 장바구니 | user, created_at, updated_at |
| **Order** | 주문 | user, status, total_amount, payment |
| **Payment** | 결제 정보 | order, amount, method, toss_payment_key |
| **PointHistory** | 포인트 이력 | user, amount, type, expires_at |

## ⚙️ 환경 설정

### 필수 환경 변수

```env
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (Production)
DATABASE_ENGINE=django.db.backends.postgresql
DATABASE_NAME=shopping_mall
DATABASE_USER=postgres
DATABASE_PASSWORD=password
DATABASE_HOST=localhost
DATABASE_PORT=5432

# Toss Payments
TOSS_CLIENT_KEY=test_ck_...
TOSS_SECRET_KEY=test_sk_...
TOSS_WEBHOOK_SECRET=...

# Redis/Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Email (선택사항)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

## 🧪 테스트

```bash
# 전체 테스트 실행
python manage.py test

# 특정 앱 테스트
python manage.py test shopping.tests

# 커버리지 측정
coverage run --source='.' manage.py test
coverage report
```

### 테스트 데이터 생성

```bash
# 최소 데이터 (개발용)
python manage.py create_test_data --preset minimal

# 기본 데이터
python manage.py create_test_data --preset basic

# 전체 데이터 (성능 테스트용)
python manage.py create_test_data --preset full
```

## 📈 성능 특징

- **응답 시간**: 평균 50ms 이하 (캐싱 적용 시)
- **동시 처리**: 100+ 동시 요청 처리 가능
- **확장성**: 수평 확장 가능한 아키텍처
- **안정성**: 트랜잭션 처리 및 롤백 메커니즘

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이센스

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 개발자

**GitHub**: [@gotoUSA](https://github.com/gotoUSA)

---

<div align="center">
  
**[⬆ back to top](#django-shopping-mall-api)**

Made with ❤️ using Django

</div>