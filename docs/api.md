# API 문서

Django Shopping Mall API의 전체 엔드포인트 가이드입니다.

## 📋 목차

- [인증 (Authentication)](#-인증-authentication)
- [상품 (Products)](#-상품-products)
- [카테고리 (Categories)](#-카테고리-categories)
- [장바구니 (Cart)](#-장바구니-cart)
- [주문 (Orders)](#-주문-orders)
- [결제 (Payments)](#-결제-payments)
- [포인트 (Points)](#-포인트-points)
- [찜하기 (Wishlist)](#-찜하기-wishlist)
- [상품 문의 (Q&A)](#-상품-문의-qa)
- [알림 (Notifications)](#-알림-notifications)
- [검색 및 필터링](#-검색-및-필터링)

---

## 🔐 인증 (Authentication)

### 회원가입
```http
POST /api/auth/register/
```

**요청 바디:**
```json
{
  "username": "user123",
  "email": "user@example.com",
  "password": "securepass123!",
  "password2": "securepass123!",
  "phone": "010-1234-5678",
  "address": "서울시 강남구"
}
```

**응답:**
```json
{
  "message": "회원가입이 완료되었습니다. 인증 이메일을 확인해주세요.",
  "access": "eyJ0eXAiOiJKV1QiLCJ...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJ...",
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com",
    "points": 0,
    "grade": "bronze",
    "is_email_verified": false
  }
}
```

### 로그인
```http
POST /api/auth/login/
```

**요청 바디:**
```json
{
  "username": "user123",
  "password": "securepass123!"
}
```

**응답:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJ...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJ...",
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com",
    "points": 5000,
    "grade": "silver",
    "is_email_verified": true
  }
}
```

### 로그아웃
```http
POST /api/auth/logout/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJ..."
}
```

**응답:**
```json
{
  "message": "로그아웃 되었습니다."
}
```

### 토큰 갱신
```http
POST /api/auth/token/refresh/
```

**요청 바디:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJ..."
}
```

**응답:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJ...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJ..."
}
```

### 토큰 유효성 확인
```http
GET /api/auth/token/verify/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "valid": true,
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com"
  },
  "message": "유효한 토큰입니다."
}
```

### 프로필 조회
```http
GET /api/auth/profile/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "id": 1,
  "username": "user123",
  "email": "user@example.com",
  "phone": "010-1234-5678",
  "address": "서울시 강남구",
  "points": 5000,
  "grade": "silver",
  "is_email_verified": true,
  "date_joined": "2025-01-01T00:00:00Z"
}
```

### 프로필 수정
```http
PATCH /api/auth/profile/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "phone": "010-9999-8888",
  "address": "서울시 서초구"
}
```

### 비밀번호 변경
```http
POST /api/auth/password/change/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "old_password": "oldpass123!",
  "new_password": "newpass456!",
  "new_password2": "newpass456!"
}
```

**응답:**
```json
{
  "message": "비밀번호가 변경되었습니다."
}
```

### 회원 탈퇴
```http
POST /api/auth/withdraw/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "password": "securepass123!"
}
```

**응답:**
```json
{
  "message": "회원 탈퇴가 완료되었습니다."
}
```

### 소셜 로그인

```http
# Google 로그인
POST /api/auth/social/google/

# Kakao 로그인
POST /api/auth/social/kakao/

# Naver 로그인
POST /api/auth/social/naver/
```

**요청 바디:**
```json
{
  "access_token": "소셜_로그인_액세스_토큰"
}
```

**응답:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJ...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJ...",
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com"
  }
}
```

### 이메일 인증

```http
# 인증 이메일 발송
POST /api/auth/email/send/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "message": "인증 이메일이 발송되었습니다.",
  "email": "user@example.com"
}
```

```http
# 인증 코드 확인
POST /api/auth/email/verify/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "code": "123456"
}
```

**응답:**
```json
{
  "message": "이메일 인증이 완료되었습니다."
}
```

```http
# 인증 이메일 재발송
POST /api/auth/email/resend/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "message": "인증 이메일이 재발송되었습니다."
}
```

```http
# 인증 상태 조회
GET /api/auth/email/status/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "is_verified": true,
  "email": "user@example.com",
  "verified_at": "2025-01-15T10:30:00Z"
}
```

---

## 📦 상품 (Products)

### 상품 목록 조회
```http
GET /api/products/
```

**쿼리 파라미터:**
- `search`: 검색어
- `category`: 카테고리 ID
- `min_price`: 최소 가격
- `max_price`: 최대 가격
- `ordering`: 정렬 (`-created_at`, `price`, `-price`, `-average_rating`)
- `page`: 페이지 번호
- `page_size`: 페이지당 개수 (기본 12, 최대 100)

**예시:**
```http
GET /api/products/?search=노트북&min_price=500000&ordering=-created_at&page=1&page_size=20
```

**응답:**
```json
{
  "count": 150,
  "next": "http://localhost:8000/api/products/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "삼성 노트북 갤럭시북",
      "price": 1200000,
      "compare_price": 1500000,
      "discount_rate": 20,
      "stock": 50,
      "category": {
        "id": 1,
        "name": "전자제품"
      },
      "images": [
        {
          "id": 1,
          "image": "/media/products/laptop.jpg",
          "is_primary": true
        }
      ],
      "average_rating": 4.5,
      "review_count": 120
    }
  ]
}
```

### 상품 상세 조회
```http
GET /api/products/{id}/
```

**응답:**
```json
{
  "id": 1,
  "name": "삼성 노트북 갤럭시북",
  "description": "고성능 노트북",
  "price": 1200000,
  "compare_price": 1500000,
  "discount_rate": 20,
  "stock": 50,
  "is_active": true,
  "category": {
    "id": 1,
    "name": "전자제품",
    "slug": "electronics"
  },
  "seller": {
    "id": 2,
    "username": "seller1"
  },
  "images": [
    {
      "id": 1,
      "image": "/media/products/laptop.jpg",
      "alt_text": "노트북 정면",
      "order": 1,
      "is_primary": true
    }
  ],
  "average_rating": 4.5,
  "review_count": 120,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

### 상품 생성
```http
POST /api/products/
Authorization: Bearer {access_token}
Content-Type: multipart/form-data
```

**요청 바디 (FormData):**
```
name: 삼성 노트북
description: 고성능 노트북
price: 1200000
compare_price: 1500000
stock: 50
category: 1
images: [파일1, 파일2, ...]
```

### 상품 수정
```http
PATCH /api/products/{id}/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "price": 1100000,
  "stock": 45
}
```

**참고:** 판매자 본인의 상품만 수정 가능

### 상품 삭제
```http
DELETE /api/products/{id}/
Authorization: Bearer {access_token}
```

**참고:** 판매자 본인의 상품만 삭제 가능

### 상품 리뷰 목록
```http
GET /api/products/{id}/reviews/
```

**응답:**
```json
[
  {
    "id": 1,
    "user": {
      "id": 3,
      "username": "user123"
    },
    "rating": 5,
    "content": "정말 좋은 상품입니다!",
    "created_at": "2025-01-15T10:30:00Z"
  }
]
```

### 리뷰 작성
```http
POST /api/products/{id}/add_review/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "rating": 5,
  "content": "정말 좋은 상품입니다!"
}
```

**응답:**
```json
{
  "id": 1,
  "rating": 5,
  "content": "정말 좋은 상품입니다!",
  "created_at": "2025-01-15T10:30:00Z"
}
```

**참고:** 동일 상품에 대해 1회만 리뷰 작성 가능

### 인기 상품
```http
GET /api/products/popular/
```

**설명:** 리뷰가 많은 순으로 상위 12개 상품 반환

### 평점 높은 상품
```http
GET /api/products/best_rating/
```

**설명:** 평균 평점이 높은 순으로 상위 12개 상품 반환 (최소 3개 이상의 리뷰 필요)

### 재고 부족 상품 (판매자 전용)
```http
GET /api/products/low_stock/
Authorization: Bearer {access_token}
```

**설명:** 현재 로그인한 판매자의 상품 중 재고가 10개 이하인 상품 목록

**응답:**
```json
[
  {
    "id": 1,
    "name": "삼성 노트북",
    "stock": 5,
    "price": 1200000,
    "category": {
      "id": 1,
      "name": "전자제품"
    }
  }
]
```

---

## 🏷 카테고리 (Categories)

### 카테고리 목록
```http
GET /api/categories/
```

**응답:**
```json
[
  {
    "id": 1,
    "name": "전자제품",
    "slug": "electronics",
    "parent": null,
    "products_count": 150,
    "is_active": true
  },
  {
    "id": 2,
    "name": "컴퓨터",
    "slug": "computer",
    "parent": 1,
    "products_count": 50,
    "is_active": true
  }
]
```

### 카테고리 상세
```http
GET /api/categories/{id}/
```

### 카테고리 트리 구조
```http
GET /api/categories/tree/
```

**응답:**
```json
[
  {
    "id": 1,
    "name": "전자제품",
    "slug": "electronics",
    "product_count": 150,
    "children": [
      {
        "id": 2,
        "name": "컴퓨터",
        "slug": "computer",
        "product_count": 50,
        "children": [
          {
            "id": 3,
            "name": "노트북",
            "slug": "laptop",
            "product_count": 30,
            "children": []
          }
        ]
      }
    ]
  }
]
```

### 카테고리별 상품
```http
GET /api/categories/{id}/products/
```

**설명:** 해당 카테고리와 하위 카테고리의 모든 상품 조회 (페이지네이션 적용)

**응답:**
```json
{
  "count": 50,
  "next": "http://localhost:8000/api/categories/1/products/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "삼성 노트북",
      "price": 1200000,
      "category": {
        "id": 3,
        "name": "노트북"
      }
    }
  ]
}
```

---

## 🛒 장바구니 (Cart)

### 장바구니 전체 조회
```http
GET /api/cart/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "id": 1,
  "user": 1,
  "items": [
    {
      "id": 1,
      "product": {
        "id": 1,
        "name": "삼성 노트북",
        "price": 1200000,
        "stock": 50
      },
      "quantity": 2,
      "subtotal": 2400000,
      "added_at": "2025-01-15T10:00:00Z"
    }
  ],
  "total_price": 2400000,
  "total_items": 1,
  "total_quantity": 2,
  "created_at": "2025-01-15T09:00:00Z"
}
```

### 장바구니 요약
```http
GET /api/cart/summary/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "total_items": 3,
  "total_quantity": 5,
  "total_price": 3500000
}
```

### 장바구니 아이템 목록
```http
GET /api/cart/items/
Authorization: Bearer {access_token}
```

**응답:**
```json
[
  {
    "id": 1,
    "product": {
      "id": 1,
      "name": "삼성 노트북",
      "price": 1200000
    },
    "quantity": 2,
    "subtotal": 2400000
  }
]
```

### 상품 추가
```http
POST /api/cart/add_item/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "product_id": 1,
  "quantity": 2
}
```

**응답:**
```json
{
  "message": "상품이 장바구니에 추가되었습니다.",
  "cart_item": {
    "id": 1,
    "product": {
      "id": 1,
      "name": "삼성 노트북"
    },
    "quantity": 2,
    "subtotal": 2400000
  }
}
```

### 여러 상품 한번에 추가
```http
POST /api/cart/bulk_add/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "items": [
    {
      "product_id": 1,
      "quantity": 2
    },
    {
      "product_id": 2,
      "quantity": 1
    }
  ]
}
```

**응답:**
```json
{
  "message": "2개의 상품이 장바구니에 추가되었습니다.",
  "added_count": 2,
  "failed_items": []
}
```

### 수량 변경
```http
PATCH /api/cart/items/{id}/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "quantity": 5
}
```

**응답:**
```json
{
  "id": 1,
  "product": {
    "id": 1,
    "name": "삼성 노트북"
  },
  "quantity": 5,
  "subtotal": 6000000
}
```

### 상품 삭제
```http
DELETE /api/cart/items/{id}/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "message": "장바구니 아이템이 삭제되었습니다."
}
```

### 장바구니 비우기
```http
POST /api/cart/clear/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "message": "장바구니가 비워졌습니다."
}
```

### 재고 확인
```http
GET /api/cart/check_stock/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "has_issues": false,
  "message": "모든 상품을 구매할 수 있습니다."
}
```

또는 재고 부족 시:

```json
{
  "has_issues": true,
  "issues": [
    {
      "product_id": 1,
      "product_name": "삼성 노트북",
      "requested": 10,
      "available": 5,
      "message": "재고가 부족합니다. (요청: 10, 재고: 5)"
    }
  ]
}
```

### RESTful 스타일 장바구니 아이템 관리

```http
# 아이템 목록
GET /api/cart-items/
Authorization: Bearer {access_token}

# 아이템 추가
POST /api/cart-items/
Authorization: Bearer {access_token}

# 아이템 수정
PUT /api/cart-items/{id}/
Authorization: Bearer {access_token}

# 아이템 삭제
DELETE /api/cart-items/{id}/
Authorization: Bearer {access_token}
```

---

## 📋 주문 (Orders)

### 주문 생성
```http
POST /api/orders/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "cart_item_ids": [1, 2, 3],
  "use_points": 1000,
  "shipping_address": "서울시 강남구 테헤란로 123",
  "shipping_memo": "문 앞에 놓아주세요"
}
```

**응답:**
```json
{
  "id": 1,
  "order_number": "20250115000001",
  "user": 1,
  "order_items": [
    {
      "id": 1,
      "product": {
        "id": 1,
        "name": "삼성 노트북"
      },
      "quantity": 2,
      "price": 1200000,
      "subtotal": 2400000
    }
  ],
  "total_amount": 2400000,
  "used_points": 1000,
  "final_amount": 2399000,
  "shipping_address": "서울시 강남구 테헤란로 123",
  "shipping_memo": "문 앞에 놓아주세요",
  "status": "pending",
  "created_at": "2025-01-15T10:30:00Z"
}
```

**참고:** 
- 이메일 인증이 완료된 사용자만 주문 생성 가능
- 주문 생성 시 장바구니에서 해당 아이템들이 자동으로 제거됨

### 주문 목록
```http
GET /api/orders/
Authorization: Bearer {access_token}
```

**쿼리 파라미터:**
- `status`: 주문 상태 필터 (`pending`, `paid`, `shipped`, `delivered`, `cancelled`)
- `ordering`: 정렬 (`-created_at`, `created_at`)
- `page`: 페이지 번호
- `page_size`: 페이지당 개수

**예시:**
```http
GET /api/orders/?status=paid&ordering=-created_at
```

**응답:**
```json
{
  "count": 10,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "order_number": "20250115000001",
      "total_amount": 2400000,
      "final_amount": 2399000,
      "status": "paid",
      "status_display": "결제 완료",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ]
}
```

### 주문 상세
```http
GET /api/orders/{id}/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "id": 1,
  "order_number": "20250115000001",
  "user": {
    "id": 1,
    "username": "user123"
  },
  "order_items": [
    {
      "id": 1,
      "product": {
        "id": 1,
        "name": "삼성 노트북",
        "price": 1200000
      },
      "quantity": 2,
      "price": 1200000,
      "subtotal": 2400000
    }
  ],
  "total_amount": 2400000,
  "used_points": 1000,
  "earned_points": 24000,
  "final_amount": 2399000,
  "shipping_address": "서울시 강남구 테헤란로 123",
  "shipping_memo": "문 앞에 놓아주세요",
  "status": "paid",
  "status_display": "결제 완료",
  "can_cancel": true,
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:35:00Z"
}
```

### 주문 취소
```http
POST /api/orders/{id}/cancel/
Authorization: Bearer {access_token}
```

**요청 바디 (선택):**
```json
{
  "reason": "단순 변심"
}
```

**응답:**
```json
{
  "message": "주문이 취소되었습니다."
}
```

**참고:**
- `pending` (결제 대기) 상태의 주문만 취소 가능
- 주문 취소 시 재고가 자동으로 복구됨
- 결제된 주문의 취소는 결제 취소 API를 사용해야 함

---

## 💳 결제 (Payments)

### 결제 요청
```http
POST /api/payments/request/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "order_id": 1
}
```

**응답:**
```json
{
  "payment_id": 1,
  "order_id": "20250115000001",
  "order_name": "삼성 노트북 외 1건",
  "customer_name": "홍길동",
  "customer_email": "user@example.com",
  "amount": 2399000,
  "client_key": "test_ck_...",
  "success_url": "http://localhost:8000/api/payments/success",
  "fail_url": "http://localhost:8000/api/payments/fail"
}
```

**참고:** 
- 이메일 인증이 완료된 사용자만 결제 요청 가능
- 반환된 정보로 토스페이먼츠 결제창을 띄움

### 결제 승인
```http
POST /api/payments/confirm/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "payment_key": "tpk_...",
  "order_key": "20250115000001",
  "amount": 2399000
}
```

**응답:**
```json
{
  "message": "결제가 승인되었습니다.",
  "payment": {
    "id": 1,
    "payment_key": "tpk_...",
    "order_key": "20250115000001",
    "amount": 2399000,
    "method": "카드",
    "status": "DONE",
    "is_paid": true,
    "approved_at": "2025-01-15T10:35:00Z"
  },
  "earned_points": 24000
}
```

**참고:**
- 결제 승인 성공 시:
  - 주문 상태가 `paid`로 변경
  - 포인트 자동 적립 (구매 금액의 1-3%, 등급별 차등)
  - 사용한 포인트 차감

### 결제 취소
```http
POST /api/payments/cancel/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "payment_id": 1,
  "cancel_reason": "단순 변심",
  "cancel_amount": 2399000
}
```

**응답:**
```json
{
  "message": "결제가 취소되었습니다.",
  "payment": {
    "id": 1,
    "status": "CANCELED",
    "canceled_amount": 2399000
  },
  "refund_amount": 2399000,
  "refunded_points": 1000,
  "deducted_points": 24000
}
```

**참고:**
- 결제 취소 시:
  - 사용한 포인트 환불
  - 적립된 포인트 차감
  - 재고 복구
  - 주문 상태 `cancelled`로 변경

### 결제 실패 처리
```http
POST /api/payments/fail/
```

**요청 바디:**
```json
{
  "code": "USER_CANCEL",
  "message": "사용자가 결제를 취소했습니다",
  "order_key": "20250115000001"
}
```

**참고:** 토스페이먼츠 결제창에서 실패/취소 시 자동 호출

### 결제 성공 콜백
```http
GET /api/payment/success/?paymentKey={key}&orderId={id}&amount={amount}
```

**참고:** 
- 이것은 웹페이지 엔드포인트입니다 (HTML 렌더링)
- 토스페이먼츠 결제창에서 성공 시 리다이렉트되는 페이지

### 결제 실패 콜백
```http
GET /api/payment/fail/?code={code}&message={message}&orderId={id}
```

**참고:**
- 이것은 웹페이지 엔드포인트입니다 (HTML 렌더링)
- 토스페이먼츠 결제창에서 실패/취소 시 리다이렉트되는 페이지

### 결제 내역 목록
```http
GET /api/payments/
Authorization: Bearer {access_token}
```

**쿼리 파라미터:**
- `page`: 페이지 번호
- `page_size`: 페이지당 개수 (기본 10)

**응답:**
```json
{
  "count": 5,
  "page": 1,
  "page_size": 10,
  "results": [
    {
      "id": 1,
      "payment_key": "tpk_...",
      "order": {
        "id": 1,
        "order_number": "20250115000001"
      },
      "amount": 2399000,
      "method": "카드",
      "status": "DONE",
      "is_paid": true,
      "approved_at": "2025-01-15T10:35:00Z"
    }
  ]
}
```

### 결제 상세 조회
```http
GET /api/payments/{payment_id}/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "id": 1,
  "payment_key": "tpk_...",
  "order": {
    "id": 1,
    "order_number": "20250115000001",
    "total_amount": 2400000,
    "final_amount": 2399000
  },
  "amount": 2399000,
  "method": "카드",
  "status": "DONE",
  "is_paid": true,
  "approved_at": "2025-01-15T10:35:00Z",
  "canceled_at": null,
  "cancel_reason": null,
  "canceled_amount": 0
}
```

---

## 💰 포인트 (Points)

### 내 포인트 조회
```http
GET /api/points/my/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "point_info": {
    "points": 5000,
    "grade": "silver",
    "grade_display": "실버",
    "earn_rate": 2
  },
  "recent_histories": [
    {
      "id": 1,
      "points": 500,
      "type": "earn",
      "description": "상품 구매 적립",
      "created_at": "2025-01-15T10:30:00Z"
    },
    {
      "id": 2,
      "points": -1000,
      "type": "use",
      "description": "주문 시 사용",
      "created_at": "2025-01-15T09:00:00Z"
    }
  ]
}
```

### 포인트 이력
```http
GET /api/points/history/
Authorization: Bearer {access_token}
```

**쿼리 파라미터:**
- `type`: 타입 필터 (`earned`, `used`)
- `start_date`: 시작일 (YYYY-MM-DD)
- `end_date`: 종료일 (YYYY-MM-DD)
- `page`: 페이지 번호
- `page_size`: 페이지당 개수 (기본 20)

**예시:**
```http
GET /api/points/history/?type=earned&start_date=2025-01-01&page=1
```

**응답:**
```json
{
  "count": 50,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "id": 1,
      "points": 500,
      "type": "earn",
      "description": "상품 구매 적립",
      "order": {
        "id": 1,
        "order_number": "20250115000001"
      },
      "expires_at": "2026-01-15T10:30:00Z",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ]
}
```

### 포인트 사용 가능 여부 확인
```http
POST /api/points/check/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "order_amount": 10000,
  "use_points": 500
}
```

**응답:**
```json
{
  "can_use": true,
  "message": "포인트를 사용할 수 있습니다.",
  "available_points": 5000,
  "requested_points": 500
}
```

또는 사용 불가 시:

```json
{
  "can_use": false,
  "message": "사용 가능한 포인트가 부족합니다.",
  "available_points": 5000,
  "requested_points": 10000
}
```

### 만료 예정 포인트
```http
GET /api/points/expiring/
Authorization: Bearer {access_token}
```

**쿼리 파라미터:**
- `days`: 조회 기간 (기본 30일)

**예시:**
```http
GET /api/points/expiring/?days=7
```

**응답:**
```json
{
  "expiring_soon": [
    {
      "expires_at": "2025-01-22T10:30:00Z",
      "points": 500,
      "days_left": 7
    }
  ],
  "total_expiring_points": 500
}
```

### 포인트 통계
```http
GET /api/points/statistics/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "current_points": 5000,
  "total_earned": 50000,
  "total_used": 45000,
  "total_expired": 0,
  "this_month_earned": 2400,
  "this_month_used": 1000
}
```

---

## ❤️ 찜하기 (Wishlist)

### 찜 목록 조회
```http
GET /api/wishlist/
Authorization: Bearer {access_token}
```

**쿼리 파라미터:**
- `ordering`: 정렬 (`created_at`, `-created_at`, `price`, `-price`, `name`)
- `is_available`: 구매 가능한 상품만 필터링 (`true`, `false`)
- `on_sale`: 세일 중인 상품만 필터링 (`true`, `false`)

**예시:**
```http
GET /api/wishlist/?ordering=-created_at&is_available=true
```

**응답:**
```json
{
  "count": 5,
  "results": [
    {
      "id": 1,
      "name": "삼성 노트북",
      "price": 1200000,
      "compare_price": 1500000,
      "discount_rate": 20,
      "stock": 50,
      "is_active": true,
      "category": {
        "id": 1,
        "name": "전자제품"
      },
      "images": [
        {
          "image": "/media/products/laptop.jpg",
          "is_primary": true
        }
      ],
      "wished_at": "2025-01-15T10:00:00Z"
    }
  ]
}
```

### 찜 추가/제거 토글
```http
POST /api/wishlist/toggle/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "product_id": 1
}
```

**응답:**
```json
{
  "is_wished": true,
  "message": "찜 목록에 추가되었습니다.",
  "wishlist_count": 123
}
```

### 찜 추가만 하기
```http
POST /api/wishlist/add/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "product_id": 1
}
```

**응답:**
```json
{
  "message": "찜 목록에 추가되었습니다.",
  "is_wished": true,
  "wishlist_count": 123
}
```

**참고:** 이미 찜한 상품이면 무시하고 200 OK 반환

### 찜 제거만 하기
```http
DELETE /api/wishlist/remove/?product_id=1
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "message": "찜 목록에서 제거되었습니다."
}
```

### 여러 상품 한번에 찜하기
```http
POST /api/wishlist/bulk_add/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "product_ids": [1, 2, 3, 4, 5]
}
```

**응답:**
```json
{
  "message": "3개 상품이 찜 목록에 추가되었습니다.",
  "added_count": 3,
  "skipped_count": 2,
  "total_wishlist_count": 10
}
```

**참고:** 이미 찜한 상품은 건너뜀

### 찜 목록 전체 삭제
```http
DELETE /api/wishlist/clear/?confirm=true
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "message": "5개의 상품이 찜 목록에서 삭제되었습니다."
}
```

**참고:** `confirm=true` 파라미터 필수 (실수 방지)

### 찜 상태 확인
```http
GET /api/wishlist/check/?product_id=1
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "product_id": 1,
  "is_wished": true
}
```

또는 여러 상품 동시 확인:

```http
GET /api/wishlist/check/?product_ids=1,2,3,4,5
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "1": true,
  "2": false,
  "3": true,
  "4": false,
  "5": true
}
```

### 찜 통계
```http
GET /api/wishlist/stats/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "total_count": 10,
  "available_count": 8,
  "out_of_stock_count": 2,
  "on_sale_count": 3,
  "total_value": 5000000,
  "average_price": 500000
}
```

### 찜 상품을 장바구니로 이동
```http
POST /api/wishlist/move_to_cart/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "wishlist_item_ids": [1, 2, 3]
}
```

또는 전체 이동:

```json
{
  "wishlist_item_ids": []
}
```

**응답:**
```json
{
  "message": "3개 상품이 장바구니로 이동되었습니다.",
  "added_to_cart": 3,
  "already_in_cart": 0,
  "out_of_stock": 0,
  "removed_from_wishlist": 3
}
```

---

## 💬 상품 문의 (Q&A)

### 상품별 문의 목록
```http
GET /api/products/{product_id}/questions/
```

**쿼리 파라미터:**
- `page`: 페이지 번호
- `page_size`: 페이지당 개수 (기본 10)

**응답:**
```json
{
  "count": 20,
  "next": "http://localhost:8000/api/products/1/questions/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "user": {
        "id": 3,
        "username": "user123"
      },
      "title": "배송 문의",
      "content": "배송 기간이 얼마나 걸리나요?",
      "is_secret": false,
      "is_answered": true,
      "created_at": "2025-01-15T10:00:00Z",
      "answer": {
        "id": 1,
        "seller": {
          "id": 2,
          "username": "seller1"
        },
        "content": "배송은 주문 후 2-3일 소요됩니다.",
        "created_at": "2025-01-15T11:00:00Z"
      }
    }
  ]
}
```

**참고:**
- 비밀글(`is_secret: true`)은 작성자와 판매자만 조회 가능
- 비로그인 사용자는 공개 문의만 볼 수 있음

### 문의 상세 조회
```http
GET /api/products/{product_id}/questions/{id}/
```

**응답:**
```json
{
  "id": 1,
  "product": {
    "id": 1,
    "name": "삼성 노트북"
  },
  "user": {
    "id": 3,
    "username": "user123"
  },
  "title": "배송 문의",
  "content": "배송 기간이 얼마나 걸리나요?",
  "is_secret": false,
  "is_answered": true,
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z",
  "answer": {
    "id": 1,
    "seller": {
      "id": 2,
      "username": "seller1"
    },
    "content": "배송은 주문 후 2-3일 소요됩니다.",
    "created_at": "2025-01-15T11:00:00Z",
    "updated_at": "2025-01-15T11:00:00Z"
  }
}
```

### 문의 작성
```http
POST /api/products/{product_id}/questions/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "title": "배송 문의",
  "content": "배송 기간이 얼마나 걸리나요?",
  "is_secret": false
}
```

**응답:**
```json
{
  "id": 1,
  "title": "배송 문의",
  "content": "배송 기간이 얼마나 걸리나요?",
  "is_secret": false,
  "is_answered": false,
  "created_at": "2025-01-15T10:00:00Z"
}
```

### 문의 수정
```http
PATCH /api/products/{product_id}/questions/{id}/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "content": "배송 기간이 얼마나 걸리나요? (서울 기준)"
}
```

**참고:** 본인이 작성한 문의만 수정 가능

### 문의 삭제
```http
DELETE /api/products/{product_id}/questions/{id}/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "message": "문의가 삭제되었습니다."
}
```

**참고:** 
- 본인이 작성한 문의만 삭제 가능
- 답변이 달린 문의는 삭제 불가

### 답변 작성 (판매자/관리자)
```http
POST /api/products/{product_id}/questions/{id}/answer/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "content": "배송은 주문 후 2-3일 소요됩니다."
}
```

**응답:**
```json
{
  "id": 1,
  "content": "배송은 주문 후 2-3일 소요됩니다.",
  "created_at": "2025-01-15T11:00:00Z"
}
```

**참고:**
- 상품 판매자 또는 관리자만 답변 작성 가능
- 답변 작성 시 질문자에게 자동으로 알림 발송
- 문의당 1개의 답변만 가능

### 답변 수정 (판매자/관리자)
```http
PATCH /api/products/{product_id}/questions/{id}/answer/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "content": "배송은 주문 후 2-3일 소요됩니다. (제주/도서산간 제외)"
}
```

### 답변 삭제 (판매자/관리자)
```http
DELETE /api/products/{product_id}/questions/{id}/answer/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "message": "답변이 삭제되었습니다."
}
```

**참고:** 답변 삭제 시 문의의 `is_answered` 상태가 `false`로 변경됨

### 내가 작성한 문의 목록
```http
GET /api/my/questions/
Authorization: Bearer {access_token}
```

**쿼리 파라미터:**
- `page`: 페이지 번호
- `page_size`: 페이지당 개수 (기본 10)

**응답:**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "product": {
        "id": 1,
        "name": "삼성 노트북"
      },
      "title": "배송 문의",
      "is_answered": true,
      "created_at": "2025-01-15T10:00:00Z"
    }
  ]
}
```

### 내 문의 상세 조회
```http
GET /api/my/questions/{id}/
Authorization: Bearer {access_token}
```

**응답:** 문의 상세 조회와 동일

---

## 🔔 알림 (Notifications)

### 알림 목록 조회
```http
GET /api/notifications/
Authorization: Bearer {access_token}
```

**쿼리 파라미터:**
- `page`: 페이지 번호
- `page_size`: 페이지당 개수 (기본 20)

**응답:**
```json
{
  "count": 15,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "notification_type": "qa_answer",
      "notification_type_display": "상품 문의 답변",
      "title": "상품 문의에 답변이 달렸습니다",
      "message": "\"배송 문의\" 문의에 판매자가 답변했습니다.",
      "link": "/products/1/questions/1",
      "is_read": false,
      "created_at": "2025-01-15T11:00:00Z"
    },
    {
      "id": 2,
      "notification_type": "order_status",
      "notification_type_display": "주문 상태 변경",
      "title": "주문이 배송 중입니다",
      "message": "주문번호 20250115000001이 배송 중입니다.",
      "link": "/orders/1",
      "is_read": true,
      "created_at": "2025-01-14T15:30:00Z"
    }
  ]
}
```

**알림 타입:**
- `qa_answer`: 상품 문의 답변
- `order_status`: 주문 상태 변경
- `point_earned`: 포인트 적립
- `point_expiring`: 포인트 만료 예정
- `review_reply`: 리뷰 답글

### 알림 상세 조회
```http
GET /api/notifications/{id}/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "id": 1,
  "notification_type": "qa_answer",
  "notification_type_display": "상품 문의 답변",
  "title": "상품 문의에 답변이 달렸습니다",
  "message": "\"배송 문의\" 문의에 판매자가 답변했습니다.",
  "link": "/products/1/questions/1",
  "is_read": true,
  "created_at": "2025-01-15T11:00:00Z"
}
```

**참고:** 상세 조회 시 자동으로 읽음 처리됨

### 읽지 않은 알림 개수
```http
GET /api/notifications/unread/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "count": 5,
  "notifications": [
    {
      "id": 1,
      "notification_type": "qa_answer",
      "title": "상품 문의에 답변이 달렸습니다",
      "message": "\"배송 문의\" 문의에 판매자가 답변했습니다.",
      "created_at": "2025-01-15T11:00:00Z"
    }
  ]
}
```

**참고:** 최근 5개의 읽지 않은 알림만 반환

### 알림 읽음 처리
```http
POST /api/notifications/mark_read/
Authorization: Bearer {access_token}
```

**요청 바디:**
```json
{
  "notification_ids": [1, 2, 3]
}
```

**응답:**
```json
{
  "message": "3개의 알림을 읽음 처리했습니다.",
  "count": 3
}
```

**참고:**
- `notification_ids`가 빈 배열이면 모든 읽지 않은 알림을 읽음 처리
- 예: `{"notification_ids": []}`

### 읽은 알림 전체 삭제
```http
DELETE /api/notifications/clear/
Authorization: Bearer {access_token}
```

**응답:**
```json
{
  "message": "10개의 알림을 삭제했습니다.",
  "count": 10
}
```

**참고:** 읽은 알림만 삭제됨 (읽지 않은 알림은 유지)

---

## 🔍 검색 및 필터링

### 상품 검색 예시

**이름 검색:**
```http
GET /api/products/?search=노트북
```

**카테고리 + 가격 필터:**
```http
GET /api/products/?category=1&min_price=500000&max_price=1500000
```

**정렬:**
```http
# 최신순
GET /api/products/?ordering=-created_at

# 가격 낮은순
GET /api/products/?ordering=price

# 가격 높은순
GET /api/products/?ordering=-price

# 평점 높은순
GET /api/products/?ordering=-average_rating

# 이름순
GET /api/products/?ordering=name
```

**페이지네이션:**
```http
GET /api/products/?page=2&page_size=20
```

**복합 조건:**
```http
GET /api/products/?search=삼성&category=1&min_price=100000&max_price=2000000&ordering=-created_at&page=1&page_size=12
```

### 주문 검색 예시

**상태별 필터:**
```http
# 결제 완료된 주문
GET /api/orders/?status=paid

# 배송중인 주문
GET /api/orders/?status=shipped

# 취소된 주문
GET /api/orders/?status=cancelled
```

**정렬:**
```http
# 최신순 (기본)
GET /api/orders/?ordering=-created_at

# 오래된 순
GET /api/orders/?ordering=created_at
```

### 포인트 이력 검색

**타입별 필터:**
```http
# 적립 이력만
GET /api/points/history/?type=earned

# 사용 이력만
GET /api/points/history/?type=used
```

**기간별 필터:**
```http
GET /api/points/history/?start_date=2025-01-01&end_date=2025-01-31
```

### 찜 목록 필터

**구매 가능 상품만:**
```http
GET /api/wishlist/?is_available=true
```

**세일 중인 상품만:**
```http
GET /api/wishlist/?on_sale=true
```

**정렬:**
```http
# 최신 찜 순
GET /api/wishlist/?ordering=-created_at

# 가격 낮은 순
GET /api/wishlist/?ordering=price

# 가격 높은 순
GET /api/wishlist/?ordering=-price

# 이름순
GET /api/wishlist/?ordering=name
```

---

## 🔧 자동 생성 API 문서

Swagger UI를 통해 실시간으로 API를 테스트할 수 있습니다:

```
http://localhost:8000/swagger/
```

ReDoc 문서:
```
http://localhost:8000/redoc/
```

---

## 📌 인증 헤더

대부분의 API는 JWT 토큰을 요구합니다. 헤더에 다음과 같이 포함하세요:

```http
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**토큰 발급:**
1. 회원가입 또는 로그인 시 `access`, `refresh` 토큰 발급
2. `access` 토큰으로 API 요청
3. `access` 토큰 만료 시 `refresh` 토큰으로 갱신

**토큰 갱신 주기:**
- Access Token: 1시간
- Refresh Token: 7일

---

## ⚠️ 에러 응답

### 400 Bad Request
```json
{
  "error": "잘못된 요청입니다",
  "detail": "필수 필드가 누락되었습니다."
}
```

또는 필드별 에러:

```json
{
  "username": ["이 필드는 필수입니다."],
  "email": ["유효한 이메일 주소를 입력하세요."]
}
```

### 401 Unauthorized
```json
{
  "detail": "인증 정보가 제공되지 않았습니다."
}
```

또는:

```json
{
  "detail": "토큰이 유효하지 않습니다."
}
```

### 403 Forbidden
```json
{
  "error": "이메일 인증이 필요합니다.",
  "message": "주문을 생성하려면 먼저 이메일 인증을 완료해주세요.",
  "verification_required": true
}
```

또는:

```json
{
  "detail": "권한이 없습니다."
}
```

### 404 Not Found
```json
{
  "detail": "찾을 수 없습니다."
}
```

또는:

```json
{
  "error": "상품을 찾을 수 없습니다."
}
```

### 500 Internal Server Error
```json
{
  "detail": "서버 오류가 발생했습니다."
}
```

---

## 📊 상태 코드 정리

| 상태 코드 | 의미 | 사용 예시 |
|----------|------|----------|
| 200 OK | 성공 | GET 요청 성공 |
| 201 Created | 생성 성공 | POST 요청으로 리소스 생성 |
| 204 No Content | 성공 (응답 본문 없음) | DELETE 요청 성공 |
| 400 Bad Request | 잘못된 요청 | 유효성 검사 실패 |
| 401 Unauthorized | 인증 실패 | 토큰 없음/만료 |
| 403 Forbidden | 권한 없음 | 이메일 미인증, 본인 아님 |
| 404 Not Found | 찾을 수 없음 | 존재하지 않는 리소스 |
| 500 Internal Server Error | 서버 오류 | 서버 내부 에러 |

---

## 💡 주요 기능별 워크플로우

### 1. 회원가입 → 이메일 인증 → 주문 워크플로우

```mermaid
graph LR
    A[회원가입] --> B[이메일 발송]
    B --> C[이메일 인증]
    C --> D[장바구니 담기]
    D --> E[주문 생성]
    E --> F[결제]
    F --> G[포인트 적립]
```

**단계별 API:**
1. `POST /api/auth/register/` - 회원가입
2. `POST /api/auth/email/verify/` - 이메일 인증
3. `POST /api/cart/add_item/` - 장바구니 담기
4. `POST /api/orders/` - 주문 생성
5. `POST /api/payments/request/` - 결제 요청
6. `POST /api/payments/confirm/` - 결제 승인 (자동 포인트 적립)

### 2. 상품 문의 워크플로우

```mermaid
graph LR
    A[문의 작성] --> B[알림 발송]
    B --> C[판매자 답변]
    C --> D[알림 발송]
    D --> E[고객 확인]
```

**단계별 API:**
1. `POST /api/products/{id}/questions/` - 문의 작성
2. 판매자에게 자동 알림
3. `POST /api/products/{id}/questions/{q_id}/answer/` - 답변 작성
4. 고객에게 자동 알림
5. `GET /api/notifications/` - 알림 확인

### 3. 포인트 사용 워크플로우

```mermaid
graph LR
    A[포인트 확인] --> B[주문 생성]
    B --> C[포인트 차감]
    C --> D[결제]
    D --> E[포인트 적립]
```

**단계별 API:**
1. `GET /api/points/my/` - 보유 포인트 확인
2. `POST /api/points/check/` - 사용 가능 여부 확인
3. `POST /api/orders/` - 주문 생성 (포인트 사용)
4. `POST /api/payments/confirm/` - 결제 승인
5. 자동 포인트 적립

---

## 📚 추가 참고사항

### 이메일 인증 필수 기능
다음 기능들은 이메일 인증이 완료되어야 사용 가능합니다:
- 주문 생성
- 결제 요청

### 포인트 등급 시스템
- Bronze (브론즈): 기본 (1% 적립)
- Silver (실버): 10만원 이상 구매 (2% 적립)
- Gold (골드): 50만원 이상 구매 (3% 적립)

### 포인트 만료
- 적립일로부터 1년 후 자동 만료
- 만료 30일 전 알림 발송

### 비밀글 문의
- `is_secret: true`로 설정 시 본인과 판매자만 조회 가능
- 비밀글은 목록에서 제목이 "비밀글입니다"로 표시됨

---

## 🎯 마무리

이 문서는 Django Shopping Mall의 모든 API 엔드포인트를 포함하고 있습니다. 

추가 질문이나 불명확한 부분이 있다면 Swagger UI(`/swagger/`)에서 실시간으로 테스트해보세요!