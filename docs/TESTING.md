# 테스트 가이드

Django Shopping Mall API의 테스트 작성 및 실행 가이드입니다.

## 📋 목차

- [테스트 실행](#-테스트-실행)
- [Docker 환경 테스트](#-docker-환경-테스트)
- [테스트 구조](#-테스트-구조)
- [테스트 작성 가이드](#-테스트-작성-가이드)
- [커버리지 측정](#-커버리지-측정)
- [CI/CD 통합](#-cicd-통합)

---

## 🚀 테스트 실행

### Docker 환경에서 테스트 (권장)

```bash
# pytest로 전체 테스트 실행
docker-compose exec web pytest

# verbose 모드
docker-compose exec web pytest -v

# 특정 파일 테스트
docker-compose exec web pytest shopping/tests/test_auth.py

# 특정 테스트 메서드
docker-compose exec web pytest shopping/tests/test_auth.py::TestAuth::test_login

# 병렬 실행 (속도 향상)
docker-compose exec web pytest -n auto

# 커버리지 측정
docker-compose exec web pytest --cov=shopping --cov-report=html

# 커버리지 보고서 확인
# htmlcov/index.html 브라우저에서 열기
```

### Django TestCase 사용

```bash
# Django 기본 테스트 러너
docker-compose exec web python manage.py test

# 특정 앱 테스트
docker-compose exec web python manage.py test shopping

# verbose 모드
docker-compose exec web python manage.py test --verbosity=2

# 병렬 실행
docker-compose exec web python manage.py test --parallel
```

---

## 🐳 Docker 환경 테스트

### 테스트 전용 컨테이너 실행

```bash
# 테스트 DB 자동 생성하여 실행
docker-compose run --rm web pytest

# 환경변수 오버라이드
docker-compose run --rm -e DEBUG=False web pytest
```

### CI/CD에서 사용하는 방법

```bash
# GitHub Actions에서 실행되는 명령어
docker-compose up -d
docker-compose exec -T web pytest --cov=shopping --cov-report=xml
docker-compose down
```

---

## 📁 테스트 구조

```
shopping/tests/
├── __init__.py
├── conftest.py              # pytest fixtures (공통 설정)
├── test_auth.py             # 인증 테스트
├── test_products.py         # 상품 테스트
├── test_cart.py             # 장바구니 테스트
├── test_orders.py           # 주문 테스트
├── test_payments.py         # 결제 테스트
├── test_points.py           # 포인트 테스트
└── test_models.py           # 모델 테스트
```

---

## 📝 테스트 작성 가이드

### 기본 테스트 클래스

```python
from django.test import TestCase
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from shopping.models import User, Product

class ProductTests(APITestCase):
    """상품 관련 테스트"""
    
    def setUp(self):
        """각 테스트 실행 전 호출"""
        self.client = APIClient()
        
        # 테스트 사용자 생성
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123!'
        )
        
        # 테스트 상품 생성
        self.product = Product.objects.create(
            name='테스트 상품',
            price=10000,
            stock=100
        )
    
    def test_get_product_list(self):
        """상품 목록 조회 테스트"""
        url = '/api/products/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data['results']), 0)
    
    def test_create_product_without_auth(self):
        """인증 없이 상품 생성 시도 (실패 예상)"""
        url = '/api/products/'
        data = {
            'name': '새 상품',
            'price': 20000,
            'stock': 50
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
```

### 인증이 필요한 테스트

```python
def test_create_order(self):
    """주문 생성 테스트"""
    # 인증 토큰 획득
    self.client.force_authenticate(user=self.user)
    
    url = '/api/orders/'
    data = {
        'cart_item_ids': [1, 2],
        'shipping_address': '서울시 강남구'
    }
    
    response = self.client.post(url, data, format='json')
    
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self.assertIn('order_number', response.data)
```

### 모델 테스트

```python
from django.test import TestCase
from shopping.models import Product, Category

class ProductModelTest(TestCase):
    """Product 모델 테스트"""
    
    def setUp(self):
        self.category = Category.objects.create(name='전자제품')
        self.product = Product.objects.create(
            name='노트북',
            price=1500000,
            stock=10,
            category=self.category
        )
    
    def test_product_str(self):
        """__str__ 메서드 테스트"""
        self.assertEqual(str(self.product), '노트북')
    
    def test_decrease_stock(self):
        """재고 차감 테스트"""
        original_stock = self.product.stock
        self.product.decrease_stock(3)
        
        self.assertEqual(self.product.stock, original_stock - 3)
    
    def test_cannot_decrease_stock_more_than_available(self):
        """재고보다 많이 차감 시도 (예외 발생 예상)"""
        with self.assertRaises(ValueError):
            self.product.decrease_stock(100)
```

### 결제 테스트 (Mocking)

```python
from unittest.mock import patch, MagicMock

class PaymentTests(APITestCase):
    """결제 테스트"""
    
    @patch('shopping.utils.toss_payment.TossPaymentClient.confirm_payment')
    def test_payment_confirmation(self, mock_confirm):
        """결제 승인 테스트"""
        # Mock 설정
        mock_confirm.return_value = {
            'status': 'DONE',
            'approvedAt': '2025-01-15T10:30:00+09:00'
        }
        
        self.client.force_authenticate(user=self.user)
        
        url = '/api/payments/confirm/'
        data = {
            'payment_key': 'test_key_123',
            'order_key': 'ord_123',
            'amount': 50000
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_confirm.assert_called_once()
```

---

## 📊 커버리지 측정

### Coverage 설치

```bash
pip install coverage
```

### 커버리지 실행

```bash
# 테스트 실행 및 커버리지 측정
coverage run --source='.' manage.py test

# 콘솔에 결과 출력
coverage report

# HTML 보고서 생성
coverage html

# HTML 보고서 열기
# htmlcov/index.html 브라우저에서 열기
```

### 특정 디렉토리만 측정

```bash
coverage run --source='shopping' manage.py test
```

### .coveragerc 설정

프로젝트 루트에 `.coveragerc` 파일 생성:

```ini
[run]
source = shopping
omit = 
    */migrations/*
    */tests/*
    */admin.py
    */apps.py
    manage.py
    myproject/wsgi.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
```

---

## 🧪 Pytest 사용 (선택사항)

### Pytest 설치

```bash
pip install pytest pytest-django pytest-cov
```

### pytest.ini 설정

프로젝트 루트에 `pytest.ini` 생성:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = myproject.settings
python_files = tests.py test_*.py *_tests.py
addopts = 
    --verbose
    --cov=shopping
    --cov-report=html
    --cov-report=term
```

### Pytest 실행

```bash
# 전체 테스트
pytest

# 특정 파일
pytest shopping/tests/test_auth.py

# 특정 테스트
pytest shopping/tests/test_auth.py::test_login

# 커버리지 포함
pytest --cov=shopping --cov-report=html
```

### Fixtures 사용 (conftest.py)

```python
# shopping/tests/conftest.py
import pytest
from rest_framework.test import APIClient
from shopping.models import User, Product

@pytest.fixture
def api_client():
    """API 클라이언트 fixture"""
    return APIClient()

@pytest.fixture
def test_user(db):
    """테스트 사용자 fixture"""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123!'
    )

@pytest.fixture
def authenticated_client(api_client, test_user):
    """인증된 클라이언트 fixture"""
    api_client.force_authenticate(user=test_user)
    return api_client

@pytest.fixture
def test_product(db):
    """테스트 상품 fixture"""
    return Product.objects.create(
        name='테스트 상품',
        price=10000,
        stock=100
    )
```

### Pytest 테스트 예시

```python
# shopping/tests/test_products.py
import pytest
from rest_framework import status

@pytest.mark.django_db
def test_get_products(api_client, test_product):
    """상품 목록 조회 테스트"""
    url = '/api/products/'
    response = api_client.get(url)
    
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data['results']) > 0

@pytest.mark.django_db
def test_create_product_with_auth(authenticated_client):
    """인증된 사용자의 상품 생성 테스트"""
    url = '/api/products/'
    data = {
        'name': '새 상품',
        'price': 20000,
        'stock': 50
    }
    
    response = authenticated_client.post(url, data)
    assert response.status_code == status.HTTP_201_CREATED
```

---

## 🔧 테스트 데이터베이스

### 기본 설정

Django는 테스트 시 자동으로 `test_` 접두사가 붙은 데이터베이스를 생성합니다.

### 메모리 DB 사용 (SQLite)

`settings.py` 수정:

```python
if 'test' in sys.argv:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
```

---

## 🚦 CI/CD 통합

### GitHub Actions 예시

`.github/workflows/test.yml`:

```yaml
name: Django Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install coverage
    
    - name: Run tests with coverage
      env:
        SECRET_KEY: test-secret-key-for-ci
        CELERY_BROKER_URL: redis://localhost:6379/0
      run: |
        coverage run --source='shopping' manage.py test
        coverage report
        coverage xml
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        files: ./coverage.xml
```

---

## 📈 테스트 모범 사례

### 1. AAA 패턴 사용

```python
def test_example(self):
    # Arrange (준비)
    user = User.objects.create_user(username='test')
    
    # Act (실행)
    response = self.client.get('/api/profile/')
    
    # Assert (검증)
    self.assertEqual(response.status_code, 200)
```

### 2. 명확한 테스트 이름

```python
# 좋음
def test_user_cannot_checkout_empty_cart(self):
    pass

# 나쁨
def test_cart(self):
    pass
```

### 3. 독립적인 테스트

각 테스트는 다른 테스트에 의존하지 않아야 합니다.

```python
# 나쁨 - 순서에 의존
def test_1_create_user(self):
    self.user = User.objects.create(...)

def test_2_update_user(self):
    self.user.username = 'new'  # test_1에 의존
```

### 4. setUp과 tearDown 활용

```python
def setUp(self):
    """각 테스트 전 실행"""
    self.user = User.objects.create_user(...)

def tearDown(self):
    """각 테스트 후 실행"""
    # 필요시 정리 작업
    pass
```

### 5. 예외 테스트

```python
def test_invalid_payment_raises_error(self):
    with self.assertRaises(ValueError):
        process_payment(amount=-100)
```

---

## 🐛 디버깅 팁

### 1. pdb 사용

```python
def test_something(self):
    import pdb; pdb.set_trace()
    # 브레이크포인트
    response = self.client.get('/api/products/')
```

### 2. 테스트 출력 보기

```bash
python manage.py test --verbosity=2
```

### 3. 실패한 테스트만 재실행

```bash
python manage.py test --failfast
```

---

## ✅ 테스트 체크리스트

프로젝트에 다음 테스트가 포함되어 있는지 확인하세요:

- [ ] **모델 테스트**: 모든 모델 메서드 검증
- [ ] **API 엔드포인트 테스트**: CRUD 작업 모두 테스트
- [ ] **인증/권한 테스트**: 인증 필요 API 검증
- [ ] **비즈니스 로직 테스트**: 주문, 결제 등 핵심 로직
- [ ] **에러 케이스**: 예외 상황 처리 검증
- [ ] **커버리지 80% 이상**: 주요 코드 경로 테스트

---

## 📚 추가 자료

- [Django Testing 공식 문서](https://docs.djangoproject.com/en/5.0/topics/testing/)
- [DRF Testing 가이드](https://www.django-rest-framework.org/api-guide/testing/)
- [Pytest-Django 문서](https://pytest-django.readthedocs.io/)

---

테스트 작성으로 더 안정적인 애플리케이션을 만들어보세요! 🚀