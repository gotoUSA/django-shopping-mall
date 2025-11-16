# 데이터 모델 구조

Django Shopping Mall API의 데이터베이스 모델 구조와 관계를 설명합니다.

## 📋 목차

- [모델 개요](#-모델-개요)
- [User (사용자)](#-user-사용자)
- [Category (카테고리)](#-category-카테고리)
- [Product (상품)](#-product-상품)
- [Cart (장바구니)](#-cart-장바구니)
- [Order (주문)](#-order-주문)
- [Payment (결제)](#-payment-결제)
- [Point (포인트)](#-point-포인트)
- [ERD 다이어그램](#-erd-다이어그램)

---

## 📊 모델 개요

| 모델 | 설명 | 주요 관계 |
|------|------|----------|
| **User** | 사용자 정보 | - |
| **Category** | 상품 카테고리 (계층 구조) | self (parent) |
| **Product** | 상품 정보 | Category, User(seller) |
| **ProductImage** | 상품 이미지 | Product |
| **Review** | 상품 리뷰 | Product, User |
| **Cart** | 장바구니 | User |
| **CartItem** | 장바구니 항목 | Cart, Product |
| **Order** | 주문 | User, Payment |
| **OrderItem** | 주문 항목 | Order, Product |
| **Payment** | 결제 정보 | Order |
| **PointHistory** | 포인트 이력 | User |

---

## 👤 User (사용자)

**위치**: `shopping/models/user.py`

### 필드

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `username` | CharField(150) | 사용자명 (고유) |
| `email` | EmailField | 이메일 (고유) |
| `password` | CharField(128) | 암호화된 비밀번호 |
| `phone` | CharField(20) | 전화번호 (선택) |
| `address` | TextField | 주소 (선택) |
| `points` | IntegerField | 보유 포인트 (기본 0) |
| `grade` | CharField(20) | 회원 등급 |
| `is_active` | BooleanField | 활성 상태 |
| `is_staff` | BooleanField | 스태프 여부 |
| `date_joined` | DateTimeField | 가입일 |
| `last_login` | DateTimeField | 마지막 로그인 |
| `last_login_ip` | GenericIPAddressField | 마지막 로그인 IP |

### 회원 등급

```python
GRADE_CHOICES = [
    ('bronze', '브론즈'),   # 적립률 1%
    ('silver', '실버'),     # 적립률 2%
    ('gold', '골드'),       # 적립률 3%
    ('platinum', '플래티넘'), # 적립률 4%
    ('diamond', '다이아몬드'), # 적립률 5%
]
```

### 관계

- `cart` ← Cart (1:1)
- `orders` ← Order (1:N)
- `reviews` ← Review (1:N)
- `point_histories` ← PointHistory (1:N)

---

## 🏷 Category (카테고리)

**위치**: `shopping/models/product.py`

MPTT(Modified Preorder Tree Traversal)를 사용한 계층형 카테고리

### 필드

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `name` | CharField(100) | 카테고리명 |
| `slug` | SlugField(100) | URL 슬러그 (자동 생성) |
| `description` | TextField | 설명 (선택) |
| `parent` | ForeignKey(self) | 부모 카테고리 (선택) |
| `is_active` | BooleanField | 활성 상태 |
| `created_at` | DateTimeField | 생성일 |
| `updated_at` | DateTimeField | 수정일 |

### MPTT 필드 (자동 생성)

- `lft`, `rght`, `tree_id`, `level`: 트리 구조 관리용

### 관계

- `parent` → Category (self, nullable)
- `children` ← Category (1:N)
- `products` ← Product (1:N)

### 예시 구조

```
전자제품 (level 0)
├── 컴퓨터 (level 1)
│   ├── 노트북 (level 2)
│   └── 데스크탑 (level 2)
└── 모바일 (level 1)
    ├── 스마트폰 (level 2)
    └── 태블릿 (level 2)
```

---

## 📦 Product (상품)

**위치**: `shopping/models/product.py`

### 필드

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `name` | CharField(200) | 상품명 |
| `description` | TextField | 상품 설명 |
| `price` | DecimalField(10,2) | 판매가 |
| `stock` | IntegerField | 재고 수량 |
| `category` | ForeignKey(Category) | 카테고리 |
| `seller` | ForeignKey(User) | 판매자 (선택) |
| `is_active` | BooleanField | 판매 여부 |
| `average_rating` | DecimalField(3,2) | 평균 평점 (0-5) |
| `review_count` | IntegerField | 리뷰 수 |
| `view_count` | IntegerField | 조회수 |
| `created_at` | DateTimeField | 등록일 |
| `updated_at` | DateTimeField | 수정일 |

### 관계

- `category` → Category (N:1)
- `seller` → User (N:1, nullable)
- `images` ← ProductImage (1:N)
- `reviews` ← Review (1:N)
- `cart_items` ← CartItem (1:N)
- `order_items` ← OrderItem (1:N)

### ProductImage (상품 이미지)

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `product` | ForeignKey(Product) | 상품 |
| `image` | ImageField | 이미지 파일 |
| `is_primary` | BooleanField | 대표 이미지 여부 |
| `ordering` | IntegerField | 정렬 순서 |

---

## 🛒 Cart (장바구니)

**위치**: `shopping/models/cart.py`

### Cart

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `user` | OneToOneField(User) | 사용자 |
| `created_at` | DateTimeField | 생성일 |
| `updated_at` | DateTimeField | 수정일 |

### CartItem (장바구니 항목)

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `cart` | ForeignKey(Cart) | 장바구니 |
| `product` | ForeignKey(Product) | 상품 |
| `quantity` | IntegerField | 수량 |
| `created_at` | DateTimeField | 추가일 |
| `updated_at` | DateTimeField | 수정일 |

### 제약 조건

- `(cart, product)` 유니크: 같은 상품 중복 방지
- `quantity > 0`: 양수만 허용

---

## 📋 Order (주문)

**위치**: `shopping/models/order.py`

### Order

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `user` | ForeignKey(User) | 주문자 |
| `order_number` | CharField(50) | 주문번호 (고유) |
| `status` | CharField(20) | 주문 상태 |
| `total_amount` | DecimalField(10,2) | 총 금액 |
| `discount_amount` | DecimalField(10,2) | 할인 금액 |
| `point_used` | IntegerField | 사용 포인트 |
| `final_amount` | DecimalField(10,2) | 최종 결제 금액 |
| `shipping_address` | TextField | 배송지 주소 |
| `shipping_memo` | TextField | 배송 메모 (선택) |
| `created_at` | DateTimeField | 주문일 |
| `updated_at` | DateTimeField | 수정일 |

### 주문 상태

```python
STATUS_CHOICES = [
    ('pending', '결제 대기'),
    ('paid', '결제 완료'),
    ('preparing', '상품 준비중'),
    ('shipped', '배송중'),
    ('delivered', '배송 완료'),
    ('cancelled', '주문 취소'),
    ('refunded', '환불 완료'),
]
```

### OrderItem (주문 항목)

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `order` | ForeignKey(Order) | 주문 |
| `product` | ForeignKey(Product) | 상품 |
| `product_name` | CharField(200) | 상품명 (스냅샷) |
| `product_price` | DecimalField(10,2) | 상품 가격 (스냅샷) |
| `quantity` | IntegerField | 수량 |
| `subtotal` | DecimalField(10,2) | 소계 |

**스냅샷 필드**: 주문 시점의 상품 정보를 저장하여 나중에 상품이 변경되어도 주문 내역 유지

---

## 💳 Payment (결제)

**위치**: `shopping/models/payment.py`

### 필드

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `order` | OneToOneField(Order) | 주문 |
| `amount` | DecimalField(10,2) | 결제 금액 |
| `method` | CharField(20) | 결제 수단 |
| `status` | CharField(20) | 결제 상태 |
| `toss_payment_key` | CharField(200) | 토스 결제 키 |
| `toss_order_id` | CharField(100) | 토스 주문 ID |
| `paid_at` | DateTimeField | 결제 완료 시각 |
| `cancelled_at` | DateTimeField | 취소 시각 (선택) |
| `cancel_reason` | TextField | 취소 사유 (선택) |
| `failure_code` | CharField(100) | 실패 코드 (선택) |
| `failure_message` | TextField | 실패 메시지 (선택) |
| `created_at` | DateTimeField | 생성일 |
| `updated_at` | DateTimeField | 수정일 |

### 결제 수단

```python
METHOD_CHOICES = [
    ('card', '카드'),
    ('transfer', '계좌이체'),
    ('virtual_account', '가상계좌'),
    ('mobile', '휴대폰'),
]
```

### 결제 상태

```python
STATUS_CHOICES = [
    ('ready', '결제 준비'),
    ('in_progress', '결제 진행중'),
    ('done', '결제 완료'),
    ('cancelled', '결제 취소'),
    ('failed', '결제 실패'),
]
```

---

## 💰 Point (포인트)

**위치**: `shopping/models/point.py`

### PointHistory

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | AutoField | 기본키 |
| `user` | ForeignKey(User) | 사용자 |
| `points` | IntegerField | 포인트 (양수: 적립, 음수: 사용) |
| `type` | CharField(20) | 포인트 유형 |
| `description` | CharField(200) | 설명 |
| `expires_at` | DateTimeField | 만료일 (적립 시) |
| `metadata` | JSONField | 추가 정보 |
| `created_at` | DateTimeField | 생성일 |

### 포인트 유형

```python
TYPE_CHOICES = [
    ('earn', '적립'),
    ('use', '사용'),
    ('cancel_refund', '취소 환급'),
    ('expire', '만료'),
    ('admin_adjust', '관리자 조정'),
]
```

### 메타데이터 예시

```json
{
  "order_id": 123,
  "earn_rate": 2,
  "used_details": [
    {
      "history_id": 45,
      "amount": 100,
      "expires_at": "2025-12-31"
    }
  ]
}
```

---

## 📐 ERD 다이어그램

```
User (사용자)
  │
  ├─ 1:1 ─→ Cart (장바구니)
  │           │
  │           └─ 1:N ─→ CartItem
  │                      │
  │                      └─ N:1 ─→ Product
  │
  ├─ 1:N ─→ Order (주문)
  │           │
  │           ├─ 1:N ─→ OrderItem
  │           │           │
  │           │           └─ N:1 ─→ Product
  │           │
  │           └─ 1:1 ─→ Payment (결제)
  │
  ├─ 1:N ─→ Review (리뷰)
  │           │
  │           └─ N:1 ─→ Product
  │
  └─ 1:N ─→ PointHistory (포인트 이력)

Category (카테고리)
  │
  ├─ self ─→ parent (부모 카테고리)
  │
  └─ 1:N ─→ Product (상품)
              │
              └─ 1:N ─→ ProductImage
```

---

## 🔄 주요 비즈니스 로직

### 주문 생성 프로세스

1. **장바구니 → 주문 변환**
   ```
   CartItem들을 OrderItem으로 복사
   재고 차감
   장바구니 비우기
   ```

2. **결제 대기 상태 생성**
   ```
   Order (status='pending')
   Payment (status='ready')
   ```

3. **토스페이먼츠 결제 요청**
   ```
   결제 정보 생성
   프론트엔드로 결제 정보 전달
   ```

4. **결제 승인**
   ```
   토스 API 호출
   Payment (status='done')
   Order (status='paid')
   포인트 적립
   ```

### 재고 관리

**주문 생성 시:**
```python
product.stock -= order_item.quantity
product.save()
```

**주문 취소 시:**
```python
product.stock += order_item.quantity
product.save()
```

### 포인트 적립/사용

**적립:**
```python
earn_amount = order.final_amount * (user.earn_rate / 100)
# F() 객체로 안전하게 포인트 증가
User.objects.filter(pk=user.pk).update(points=F('points') + earn_amount)
user.refresh_from_db()
# 이력 기록 (balance 명시적 전달 필수)
PointHistory.create_history(
    user=user,
    points=earn_amount,
    balance=user.points,
    type='earn',
    expires_at=now + 1년
)
```

**사용 (FIFO):**
```python
# 만료일 순으로 포인트 차감
available_points = PointHistory.filter(
    user=user,
    type='earn',
    expires_at__gt=now
).order_by('expires_at')
```

---

## 📝 데이터베이스 마이그레이션

### 마이그레이션 파일 생성

```bash
python manage.py makemigrations
```

### 마이그레이션 적용

```bash
python manage.py migrate
```

### 마이그레이션 확인

```bash
# 적용된 마이그레이션 목록
python manage.py showmigrations

# 마이그레이션 SQL 확인
python manage.py sqlmigrate shopping 0001
```

---

## 🔍 인덱스 최적화

### 자동 생성 인덱스

- Primary Key (id)
- Foreign Key (user_id, product_id, 등)
- Unique 필드 (username, email, order_number, 등)

### 추가 권장 인덱스

```python
class Meta:
    indexes = [
        models.Index(fields=['created_at']),
        models.Index(fields=['status', 'created_at']),
        models.Index(fields=['category', 'is_active']),
    ]
```

---

## 💡 참고 사항

- **Soft Delete**: 실제 데이터 삭제 대신 `is_active=False` 사용
- **타임스탬프**: 모든 모델에 `created_at`, `updated_at` 포함
- **스냅샷**: 주문 항목은 주문 시점의 정보를 저장
- **트랜잭션**: 주문/결제는 atomic 트랜잭션으로 보호

---

더 자세한 내용은 코드를 직접 참조하세요:
- `shopping/models/user.py`
- `shopping/models/product.py`
- `shopping/models/cart.py`
- `shopping/models/order.py`
- `shopping/models/payment.py`
- `shopping/models/point.py`