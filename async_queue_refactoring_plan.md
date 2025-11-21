# 비동기 큐 처리 아키텍처 개선 계획

## 📋 목차

1. [개요](#개요)
2. [Phase 0: 사전 준비](#phase-0-사전-준비)
3. [Phase 1: 결제 승인 비동기화](#phase-1-결제-승인-비동기화)
4. [Phase 2: 주문 생성 하이브리드 처리](#phase-2-주문-생성-하이브리드-처리)
5. [Phase 3: 포인트 시스템 최적화](#phase-3-포인트-시스템-최적화)
6. [Phase 4: 성능 테스트 및 검증](#phase-4-성능-테스트-및-검증)
7. [Phase 5: 모니터링 및 배포](#phase-5-모니터링-및-배포)

---

## 개요

### 🎯 목표

현재 동기 처리 방식의 결제/주문 시스템을 **Celery 기반 비동기 큐 아키텍처**로 전환하여:
- 대규모 트래픽(1000명 동시 주문) 처리 능력 확보
- DB 락 경쟁 최소화
- 외부 API 호출 병목 제거
- UX 개선 (즉시 응답)

### 📊 현재 문제점

| 문제 영역 | 현재 상태 | 목표 상태 |
|----------|----------|----------|
| **결제 승인** | 동기 처리, 트랜잭션 내 외부 API 호출 | Toss API 비동기화, 트랜잭션 분리 |
| **주문 생성** | 전체 동기 처리, 응답 지연 | Order 생성은 동기, 재고/포인트는 비동기 |
| **포인트 적립** | 결제 트랜잭션 내 동기 처리 | 별도 큐로 비동기 처리 |
| **재고 차감** | 트랜잭션 락 경쟁 | 비동기 처리로 락 경쟁 완화 |

### ⚠️ 핵심 원칙

1. **UX 최우선**: 사용자에게 즉시 응답이 필요한 작업은 동기 유지
2. **트랜잭션 최소화**: 외부 API는 트랜잭션 밖에서 호출
3. **단계적 전환**: 한 번에 모든 것을 바꾸지 않고, 작은 단위로 검증하며 진행
4. **롤백 가능성**: 각 Phase마다 독립적으로 롤백 가능하도록 설계

---

## Phase 0: 사전 준비

### Task 0-1: Celery 설정 검증 및 개선

**목적**: 현재 Celery 설정이 대규모 트래픽을 처리할 수 있는지 확인

**작업 내용**:

1. **Celery 설정 파일 확인**
   - 파일: `myproject/celery.py`
   - 확인 항목:
     - Broker URL (Redis/RabbitMQ)
     - Result Backend
     - Task Serializer
     - Timezone 설정

2. **Queue 구조 설계**
   ```python
   # myproject/celery.py에 추가
   CELERY_TASK_ROUTES = {
       # 결제 관련 (최우선)
       'shopping.tasks.payment_tasks.*': {
           'queue': 'payment_critical',
           'routing_key': 'payment.critical',
       },

       # 주문 처리
       'shopping.tasks.order_tasks.*': {
           'queue': 'order_processing',
           'routing_key': 'order.process',
       },

       # 포인트 (낮은 우선순위)
       'shopping.tasks.point_tasks.*': {
           'queue': 'points',
           'routing_key': 'points.earn',
       },

       # 외부 API 호출
       'shopping.tasks.external_api_tasks.*': {
           'queue': 'external_api',
           'routing_key': 'external.api',
       },
   }
   ```

3. **Worker 실행 스크립트 작성**
   ```bash
   # start_workers.sh
   celery -A myproject worker -Q payment_critical -c 10 -n payment@%h &
   celery -A myproject worker -Q order_processing -c 5 -n order@%h &
   celery -A myproject worker -Q external_api -c 3 -n api@%h &
   celery -A myproject worker -Q points -c 2 -n points@%h &
   ```

**검증 방법**:
```bash
# Celery 상태 확인
celery -A myproject inspect active_queues
celery -A myproject inspect stats
```

**예상 소요 시간**: 1시간

---

### Task 0-2: 테스트 환경 설정

**목적**: Celery 태스크를 테스트할 수 있는 환경 구성

**작업 내용**:

1. **pytest-celery 설치**
   ```bash
   pip install pytest-celery
   ```

2. **테스트 설정 추가**
   ```python
   # conftest.py
   import pytest
   from celery import Celery

   @pytest.fixture(scope='session')
   def celery_config():
       return {
           'broker_url': 'memory://',
           'result_backend': 'cache+memory://',
           'task_always_eager': True,  # 동기 실행 (테스트용)
           'task_eager_propagates': True,
       }

   @pytest.fixture
   def celery_worker_parameters():
       return {
           'perform_ping_check': False,
       }
   ```

3. **기본 태스크 테스트 작성**
   ```python
   # shopping/tests/tasks/test_celery_setup.py
   import pytest
   from shopping.tasks.point_tasks import expire_points_task

   @pytest.mark.django_db(transaction=True)
   class TestCelerySetup:
       def test_celery_task_can_run(self):
           """Celery 태스크가 정상 실행되는지 확인"""
           result = expire_points_task.delay()
           assert result.successful()
   ```

**예상 소요 시간**: 30분

---

## Phase 1: 결제 승인 비동기화

> ⚠️ **가장 우선순위 높음**: 외부 API 호출로 인한 DB 락 장시간 보유 문제 해결

### Task 1-1: Toss API 호출 태스크 분리

**목적**: 외부 API 호출을 트랜잭션 밖으로 분리

**작업 내용**:

1. **새 태스크 파일 생성**: `shopping/tasks/payment_tasks.py`

```python
from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import transaction

from shopping.models.payment import Payment, PaymentLog
from shopping.utils.toss_payment import TossPaymentClient, TossPaymentError

logger = get_task_logger(__name__)


@shared_task(
    name='shopping.tasks.payment_tasks.call_toss_confirm_api',
    queue='external_api',
    max_retries=3,
    default_retry_delay=5,
    time_limit=10,  # 10초 타임아웃
)
def call_toss_confirm_api(payment_key: str, order_id: str, amount: int) -> dict:
    """
    Toss 결제 승인 API 호출 (외부 API만 호출, DB 작업 없음)

    Args:
        payment_key: 토스 결제 키
        order_id: 주문 번호
        amount: 결제 금액

    Returns:
        Toss API 응답 데이터

    Raises:
        TossPaymentError: API 호출 실패
    """
    logger.info(f"Toss API 호출 시작: order_id={order_id}, amount={amount}")

    try:
        toss_client = TossPaymentClient()
        payment_data = toss_client.confirm_payment(
            payment_key=payment_key,
            order_id=order_id,
            amount=amount,
        )

        logger.info(f"Toss API 호출 성공: order_id={order_id}")
        return payment_data

    except TossPaymentError as e:
        logger.error(f"Toss API 호출 실패: order_id={order_id}, error={e.message}")

        # 재시도 (네트워크 오류 등)
        if e.code in ['NETWORK_ERROR', 'TIMEOUT']:
            raise call_toss_confirm_api.retry(exc=e)

        # 재시도 불가능한 오류는 그대로 raise
        raise
```

**예상 소요 시간**: 1시간

---

### Task 1-2: 결제 승인 최종 처리 태스크 작성

**목적**: Toss API 결과를 받아 DB 업데이트 (짧은 트랜잭션)

**작업 내용**:

1. **`shopping/tasks/payment_tasks.py`에 추가**:

```python
@shared_task(
    name='shopping.tasks.payment_tasks.finalize_payment_confirm',
    queue='payment_critical',
    max_retries=5,
    default_retry_delay=10,
)
def finalize_payment_confirm(
    payment_id: int,
    toss_response: dict,
    user_id: int
) -> dict:
    """
    Toss API 결과를 받아 결제 최종 처리
    - Payment 상태 업데이트
    - 재고 차감 (sold_count 증가)
    - Order 상태 변경
    - 장바구니 비활성화

    Args:
        payment_id: Payment ID
        toss_response: Toss API 응답 데이터
        user_id: 사용자 ID

    Returns:
        처리 결과
    """
    from shopping.models.payment import Payment
    from shopping.models.order import Order
    from shopping.models.product import Product
    from shopping.models.cart import Cart
    from shopping.models.user import User
    from django.db.models import F

    logger.info(f"결제 최종 처리 시작: payment_id={payment_id}")

    try:
        with transaction.atomic():
            # 1. Payment 업데이트 (짧은 트랜잭션)
            payment = Payment.objects.select_for_update().get(pk=payment_id)

            # 중복 처리 방지
            if payment.is_paid:
                logger.warning(f"이미 처리된 결제: payment_id={payment_id}")
                return {'status': 'already_processed', 'payment_id': payment_id}

            payment.mark_as_paid(toss_response)
            order = payment.order

            # 2. 재고 차감 (sold_count만 증가, stock은 주문 생성 시 이미 차감)
            for order_item in order.order_items.select_for_update():
                if order_item.product:
                    Product.objects.filter(pk=order_item.product.pk).update(
                        sold_count=F('sold_count') + order_item.quantity
                    )

            # 3. Order 상태 변경
            order.status = 'paid'
            order.payment_method = payment.method
            order.save(update_fields=['status', 'payment_method', 'updated_at'])

            # 4. 장바구니 비활성화
            Cart.objects.filter(user_id=user_id, is_active=True).update(is_active=False)

            # 5. 로그 기록
            PaymentLog.objects.create(
                payment=payment,
                log_type='approve',
                message='결제 승인 완료',
                data=toss_response,
            )

        logger.info(f"결제 최종 처리 완료: payment_id={payment_id}, order_id={order.id}")

        # 6. 포인트 적립은 별도 태스크로 (비동기)
        from shopping.tasks.point_tasks import add_points_after_payment
        if order.final_amount > 0:
            add_points_after_payment.delay(user_id, order.id)

        return {
            'status': 'success',
            'payment_id': payment_id,
            'order_id': order.id,
        }

    except Exception as e:
        logger.error(f"결제 최종 처리 실패: payment_id={payment_id}, error={str(e)}")

        # 재시도
        raise finalize_payment_confirm.retry(exc=e)
```

**예상 소요 시간**: 2시간

---

### Task 1-3: PaymentService 리팩토링

**목적**: 기존 `confirm_payment` 메서드를 비동기 태스크 기반으로 변경

**작업 내용**:

1. **`shopping/services/payment_service.py` 수정**:

```python
# 기존 confirm_payment 메서드를 주석 처리하고 새 버전 작성

@staticmethod
def confirm_payment_async(
    payment: Payment,
    payment_key: str,
    order_id: str,
    amount: int,
    user
) -> dict:
    """
    결제 승인 처리 (비동기 버전)

    1. Toss API 호출 태스크 실행
    2. 즉시 응답 반환 (processing 상태)
    3. 백그라운드에서 결제 최종 처리

    Returns:
        {'status': 'processing', 'payment_id': ..., 'task_id': ...}
    """
    from shopping.tasks.payment_tasks import (
        call_toss_confirm_api,
        finalize_payment_confirm
    )

    logger.info(f"비동기 결제 승인 시작: payment_id={payment.id}")

    # 1. Payment 상태 확인 (간단한 트랜잭션)
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)

        if payment.is_paid:
            raise PaymentConfirmError("이미 완료된 결제입니다.")

        if payment.status in ['expired', 'canceled', 'aborted']:
            raise PaymentConfirmError(f"유효하지 않은 결제 상태입니다: {payment.get_status_display()}")

        # 처리 중 상태로 변경
        payment.status = 'in_progress'
        payment.save(update_fields=['status'])

    # 2. Celery Chain: Toss API 호출 → 최종 처리
    from celery import chain

    task_chain = chain(
        call_toss_confirm_api.s(payment_key, order_id, amount),
        finalize_payment_confirm.s(payment.id, user.id)
    )

    result = task_chain.apply_async()

    logger.info(f"결제 승인 태스크 실행: payment_id={payment.id}, task_id={result.id}")

    # 3. 즉시 응답 (사용자는 결과를 WebSocket/Polling으로 확인)
    return {
        'status': 'processing',
        'payment_id': payment.id,
        'task_id': result.id,
        'message': '결제 처리 중입니다. 잠시만 기다려주세요.',
    }
```

**마이그레이션 전략**:
- 기존 `confirm_payment`는 `confirm_payment_sync`로 이름 변경 (롤백용)
- 새 메서드를 먼저 테스트
- 검증 후 기존 메서드 제거

**예상 소요 시간**: 2시간

---

### Task 1-4: View 레이어 수정

**목적**: API 엔드포인트에서 비동기 메서드 호출

**작업 내용**:

1. **`shopping/views/payment_views.py` 수정**:

```python
# PaymentConfirmView 수정

class PaymentConfirmView(APIView):
    """결제 승인 API (비동기 처리)"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # ... 기존 검증 로직 ...

        try:
            # 기존: result = PaymentService.confirm_payment(...)
            # 변경: 비동기 메서드 호출
            result = PaymentService.confirm_payment_async(
                payment=payment,
                payment_key=payment_key,
                order_id=order_id,
                amount=amount,
                user=request.user,
            )

            # 즉시 응답 (202 Accepted)
            return Response({
                'status': 'processing',
                'payment_id': result['payment_id'],
                'task_id': result['task_id'],
                'message': '결제 처리 중입니다. 완료 시 알림을 드립니다.',
                # 프론트엔드가 결과를 확인할 수 있는 엔드포인트
                'status_url': f'/api/payments/{result["payment_id"]}/status/',
            }, status=status.HTTP_202_ACCEPTED)

        except PaymentConfirmError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
```

2. **결제 상태 확인 API 추가**:

```python
class PaymentStatusView(APIView):
    """결제 처리 상태 확인 API"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, payment_id):
        try:
            payment = Payment.objects.get(
                id=payment_id,
                order__user=request.user
            )

            return Response({
                'payment_id': payment.id,
                'status': payment.status,
                'is_paid': payment.is_paid,
                'order_status': payment.order.status if payment.order else None,
            })

        except Payment.DoesNotExist:
            return Response(
                {'error': '결제 정보를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )
```

**예상 소요 시간**: 1.5시간

---

### Task 1-5: 결제 비동기 처리 테스트 작성

**목적**: 비동기 결제 처리가 정상 작동하는지 검증

**작업 내용**:

1. **`shopping/tests/tasks/test_payment_tasks.py` 생성**:

```python
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from shopping.models.payment import Payment
from shopping.tasks.payment_tasks import (
    call_toss_confirm_api,
    finalize_payment_confirm,
)
from shopping.tests.factories import (
    PaymentFactory,
    OrderFactory,
    ProductFactory,
    UserFactory,
)


@pytest.mark.django_db(transaction=True)
class TestPaymentTasksHappyPath:
    """결제 태스크 정상 케이스"""

    def test_call_toss_api_task_success(self, mocker):
        """Toss API 호출 태스크가 성공적으로 실행됨"""
        # Arrange
        mock_response = {
            'paymentKey': 'test_key_123',
            'orderId': 'ORDER_123',
            'status': 'DONE',
        }
        mocker.patch(
            'shopping.utils.toss_payment.TossPaymentClient.confirm_payment',
            return_value=mock_response
        )

        # Act
        result = call_toss_confirm_api(
            payment_key='test_key_123',
            order_id='ORDER_123',
            amount=10000
        )

        # Assert
        assert result == mock_response
        assert result['status'] == 'DONE'

    def test_finalize_payment_task_success(self, user_factory, product):
        """결제 최종 처리 태스크가 성공적으로 실행됨"""
        # Arrange
        user = user_factory()
        order = OrderFactory(user=user, status='pending')
        payment = PaymentFactory(order=order, status='ready')

        toss_response = {
            'paymentKey': 'test_key',
            'status': 'DONE',
            'approvedAt': '2025-11-21T14:00:00',
        }

        # Act
        result = finalize_payment_task(
            payment_id=payment.id,
            toss_response=toss_response,
            user_id=user.id
        )

        # Assert
        payment.refresh_from_db()
        assert payment.is_paid
        assert payment.order.status == 'paid'
        assert result['status'] == 'success'

    def test_payment_chain_integration(self, user_factory, mocker):
        """Toss API → 최종 처리 체인이 정상 작동"""
        # Arrange
        user = user_factory()
        order = OrderFactory(user=user)
        payment = PaymentFactory(order=order)

        mock_toss_response = {'status': 'DONE', 'paymentKey': 'key123'}
        mocker.patch(
            'shopping.utils.toss_payment.TossPaymentClient.confirm_payment',
            return_value=mock_toss_response
        )

        # Act
        from celery import chain
        from shopping.tasks.payment_tasks import call_toss_confirm_api, finalize_payment_confirm

        task_chain = chain(
            call_toss_confirm_api.s('key123', 'ORDER_123', 10000),
            finalize_payment_confirm.s(payment.id, user.id)
        )

        result = task_chain.apply()

        # Assert
        payment.refresh_from_db()
        assert payment.is_paid
        assert result.successful()


@pytest.mark.django_db(transaction=True)
class TestPaymentTasksBoundary:
    """결제 태스크 경계 케이스"""

    def test_duplicate_payment_confirm_ignored(self, user_factory):
        """이미 처리된 결제는 무시됨"""
        # Arrange
        user = user_factory()
        order = OrderFactory(user=user, status='paid')
        payment = PaymentFactory(order=order, status='done', is_paid=True)

        # Act
        result = finalize_payment_confirm(
            payment_id=payment.id,
            toss_response={'status': 'DONE'},
            user_id=user.id
        )

        # Assert
        assert result['status'] == 'already_processed'


@pytest.mark.django_db(transaction=True)
class TestPaymentTasksException:
    """결제 태스크 예외 케이스"""

    def test_toss_api_network_error_retries(self, mocker):
        """네트워크 오류 시 재시도"""
        # Arrange
        from shopping.utils.toss_payment import TossPaymentError

        mock_client = mocker.patch(
            'shopping.utils.toss_payment.TossPaymentClient.confirm_payment',
            side_effect=TossPaymentError('NETWORK_ERROR', 'Network failed')
        )

        # Act & Assert
        with pytest.raises(Exception):  # Celery retry exception
            call_toss_confirm_api.apply(
                args=('key', 'order', 10000),
                throw=True
            )
```

**예상 소요 시간**: 3시간

---

## Phase 2: 주문 생성 하이브리드 처리

> 📌 **하이브리드 전략**: Order 생성은 동기(즉시 응답), 재고/포인트는 비동기

### Task 2-1: 주문 처리 태스크 작성

**목적**: 무거운 작업(재고 차감, 포인트 사용)을 비동기로 분리

**작업 내용**:

1. **`shopping/tasks/order_tasks.py` 생성**:

```python
from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import transaction
from django.db.models import F

logger = get_task_logger(__name__)


@shared_task(
    name='shopping.tasks.order_tasks.process_order_heavy_tasks',
    queue='order_processing',
    max_retries=3,
    default_retry_delay=10,
)
def process_order_heavy_tasks(
    order_id: int,
    cart_id: int,
    use_points: int = 0
) -> dict:
    """
    주문 생성 후 무거운 작업 처리
    - 재고 차감
    - 포인트 사용
    - 장바구니 비우기

    Args:
        order_id: Order ID
        cart_id: Cart ID
        use_points: 사용할 포인트

    Returns:
        처리 결과
    """
    from shopping.models.order import Order
    from shopping.models.cart import Cart
    from shopping.models.product import Product
    from shopping.services.point_service import PointService

    logger.info(f"주문 무거운 작업 시작: order_id={order_id}")

    try:
        with transaction.atomic():
            # 1. Order 조회 및 락
            order = Order.objects.select_for_update().get(pk=order_id)

            # 이미 처리된 주문인지 확인
            if order.status != 'pending':
                logger.warning(f"이미 처리된 주문: order_id={order_id}, status={order.status}")
                return {'status': 'already_processed', 'order_id': order_id}

            # 2. Cart 조회 및 락
            cart = Cart.objects.select_for_update().get(pk=cart_id)

            # 3. 재고 차감 (실패 가능)
            for cart_item in cart.items.all():
                product = Product.objects.select_for_update().get(pk=cart_item.product.pk)

                # 재고 부족 체크
                if product.stock < cart_item.quantity:
                    logger.error(
                        f"재고 부족: product_id={product.pk}, "
                        f"requested={cart_item.quantity}, available={product.stock}"
                    )

                    # 주문 실패 처리
                    order.status = 'failed'
                    order.failure_reason = f'{product.name} 재고 부족'
                    order.save(update_fields=['status', 'failure_reason', 'updated_at'])

                    return {
                        'status': 'failed',
                        'reason': 'insufficient_stock',
                        'product': product.name,
                        'order_id': order_id,
                    }

                # 재고 차감
                Product.objects.filter(pk=product.pk).update(
                    stock=F('stock') - cart_item.quantity
                )

                logger.info(f"재고 차감: product_id={product.pk}, quantity={cart_item.quantity}")

                # OrderItem 생성
                from shopping.models.order import OrderItem
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    product_name=cart_item.product.name,
                    quantity=cart_item.quantity,
                    price=cart_item.product.price,
                )

            # 4. 포인트 사용 (선택적)
            if use_points > 0:
                point_service = PointService()
                result = point_service.use_points_fifo(
                    user=order.user,
                    amount=use_points,
                    type='use',
                    order=order,
                    description=f'주문 #{order.order_number} 결제시 사용',
                    metadata={
                        'order_id': order.id,
                        'order_number': order.order_number,
                    }
                )

                if not result['success']:
                    logger.error(f"포인트 사용 실패: order_id={order_id}, reason={result['message']}")

                    # 주문 실패 처리 (재고는 이미 차감됨 → 복구 필요)
                    for item in order.order_items.all():
                        Product.objects.filter(pk=item.product.pk).update(
                            stock=F('stock') + item.quantity
                        )

                    order.status = 'failed'
                    order.failure_reason = f'포인트 사용 실패: {result["message"]}'
                    order.save(update_fields=['status', 'failure_reason', 'updated_at'])

                    return {
                        'status': 'failed',
                        'reason': 'point_deduction_failed',
                        'message': result['message'],
                        'order_id': order_id,
                    }

            # 5. 주문 확정
            order.status = 'confirmed'
            order.save(update_fields=['status', 'updated_at'])

            # 6. 장바구니 비우기
            cart.items.all().delete()

            logger.info(f"주문 무거운 작업 완료: order_id={order_id}")

            return {
                'status': 'success',
                'order_id': order_id,
                'order_number': order.order_number,
            }

    except Exception as e:
        logger.error(f"주문 처리 실패: order_id={order_id}, error={str(e)}")

        # 재시도
        raise process_order_heavy_tasks.retry(exc=e)
```

**예상 소요 시간**: 3시간

---

### Task 2-2: OrderService 리팩토링

**목적**: Order 생성은 동기, 무거운 작업은 비동기로 분리

**작업 내용**:

1. **`shopping/services/order_service.py`에 새 메서드 추가**:

```python
@staticmethod
def create_order_hybrid(
    user,
    cart: Cart,
    shipping_name: str,
    shipping_phone: str,
    shipping_postal_code: str,
    shipping_address: str,
    shipping_address_detail: str,
    order_memo: str = "",
    use_points: int = 0,
) -> tuple[Order, str]:
    """
    주문 생성 (하이브리드 방식)

    1. Order 레코드만 빠르게 생성 (동기, 즉시 응답)
    2. 재고/포인트 처리는 비동기 태스크로 위임

    Returns:
        (Order, task_id) 튜플
    """
    logger.info(f"하이브리드 주문 생성 시작: user_id={user.id}, cart_id={cart.id}")

    # 1. 사전 검증 (동기)
    if not cart.items.exists():
        raise OrderServiceError("장바구니가 비어있습니다.")

    total_amount = cart.get_total_amount()

    # 2. 배송비 계산
    shipping_result = ShippingService.calculate_fee(
        total_amount=total_amount,
        postal_code=shipping_postal_code
    )

    # 3. 포인트 사용 검증 (실제 차감은 나중에)
    total_payment_amount = (
        total_amount +
        shipping_result['shipping_fee'] +
        shipping_result['additional_fee']
    )
    OrderService._validate_point_usage(user, use_points, total_payment_amount)

    # 4. 최종 결제 금액
    final_amount = max(Decimal('0'), total_payment_amount - Decimal(str(use_points)))

    # 5. Order 레코드 생성 (트랜잭션 짧게)
    with transaction.atomic():
        order = Order.objects.create(
            user=user,
            status='pending',  # 아직 미확정
            total_amount=total_amount,
            shipping_fee=shipping_result['shipping_fee'],
            additional_shipping_fee=shipping_result['additional_fee'],
            is_free_shipping=shipping_result['is_free_shipping'],
            used_points=use_points,
            final_amount=final_amount,
            shipping_name=shipping_name,
            shipping_phone=shipping_phone,
            shipping_postal_code=shipping_postal_code,
            shipping_address=shipping_address,
            shipping_address_detail=shipping_address_detail,
            order_memo=order_memo,
        )

    logger.info(f"Order 레코드 생성 완료: order_id={order.id}, order_number={order.order_number}")

    # 6. 무거운 작업은 비동기로 (재고, 포인트)
    from shopping.tasks.order_tasks import process_order_heavy_tasks

    task_result = process_order_heavy_tasks.delay(
        order_id=order.id,
        cart_id=cart.id,
        use_points=use_points
    )

    logger.info(f"주문 비동기 처리 시작: order_id={order.id}, task_id={task_result.id}")

    return order, task_result.id
```

**예상 소요 시간**: 2시간

---

### Task 2-3: 주문 View 수정

**작업 내용**:

1. **`shopping/views/order_views.py` 수정**:

```python
class OrderCreateView(APIView):
    """주문 생성 API (하이브리드 처리)"""

    def post(self, request):
        # ... 기존 검증 로직 ...

        try:
            # 기존: order = OrderService.create_order_from_cart(...)
            # 변경: 하이브리드 메서드 호출
            order, task_id = OrderService.create_order_hybrid(
                user=request.user,
                cart=cart,
                # ... 기타 파라미터
            )

            # 즉시 응답 (202 Accepted)
            return Response({
                'order_id': order.id,
                'order_number': order.order_number,
                'status': 'pending',
                'task_id': task_id,
                'message': '주문 처리 중입니다.',
                'status_url': f'/api/orders/{order.id}/status/',
                # 결제 페이지로 리다이렉트
                'next_step': 'payment',
            }, status=status.HTTP_202_ACCEPTED)

        except OrderServiceError as e:
            return Response({'error': str(e)}, status=400)
```

**예상 소요 시간**: 1시간

---

## Phase 3: 포인트 시스템 최적화

### Task 3-1: 포인트 적립 태스크 작성

**작업 내용**:

1. **`shopping/tasks/point_tasks.py`에 추가**:

```python
@shared_task(
    name='shopping.tasks.point_tasks.add_points_after_payment',
    queue='points',
    priority=5,  # 낮은 우선순위
    max_retries=5,
    default_retry_delay=60,
)
def add_points_after_payment(user_id: int, order_id: int) -> dict:
    """
    결제 완료 후 포인트 적립 (비동기)

    Args:
        user_id: User ID
        order_id: Order ID

    Returns:
        적립 결과
    """
    from shopping.models.user import User
    from shopping.models.order import Order
    from shopping.services.point_service import PointService
    from decimal import Decimal

    logger.info(f"포인트 적립 시작: user_id={user_id}, order_id={order_id}")

    try:
        user = User.objects.get(pk=user_id)
        order = Order.objects.get(pk=order_id)

        # 포인트로만 결제한 경우는 적립 안 함
        if order.final_amount <= 0:
            logger.info(f"포인트 전액 결제로 적립 제외: order_id={order_id}")
            return {'status': 'skipped', 'reason': 'full_point_payment'}

        # 등급별 적립률
        earn_rate = user.get_earn_rate()
        points_to_add = int(order.final_amount * Decimal(earn_rate) / Decimal('100'))

        if points_to_add <= 0:
            return {'status': 'skipped', 'reason': 'zero_points'}

        # 포인트 적립
        PointService.add_points(
            user=user,
            amount=points_to_add,
            type='earn',
            order=order,
            description=f'주문 #{order.order_number} 구매 적립',
            metadata={
                'order_id': order.id,
                'order_number': order.order_number,
                'payment_amount': str(order.final_amount),
                'earn_rate': f'{earn_rate}%',
            }
        )

        # Order에 적립 포인트 기록
        order.earned_points = points_to_add
        order.save(update_fields=['earned_points'])

        logger.info(f"포인트 적립 완료: user_id={user_id}, points={points_to_add}")

        return {
            'status': 'success',
            'user_id': user_id,
            'order_id': order_id,
            'points_earned': points_to_add,
        }

    except Exception as e:
        logger.error(f"포인트 적립 실패: user_id={user_id}, error={str(e)}")

        # 재시도
        raise add_points_after_payment.retry(exc=e)
```

**예상 소요 시간**: 1.5시간

---

## Phase 4: 성능 테스트 및 검증

### Task 4-1: 부하 테스트 작성

**목적**: 1000명 동시 주문 시나리오 검증

**작업 내용**:

1. **`shopping/tests/performance/test_concurrent_load.py` 생성**:

```python
import pytest
from concurrent.futures import ThreadPoolExecutor
from rest_framework.test import APIClient

from shopping.models.product import Product
from shopping.tests.factories import UserFactory, ProductFactory


@pytest.mark.django_db(transaction=True)
@pytest.mark.performance
class TestConcurrentLoad:
    """대규모 동시 접속 테스트"""

    def test_1000_concurrent_payments(self, user_factory, product):
        """1000명 동시 결제 처리"""
        # Arrange
        product.stock = 1000
        product.save()

        users = [user_factory(username=f'user{i}') for i in range(1000)]

        def make_payment(user):
            client = APIClient()
            client.force_authenticate(user=user)
            # ... 주문 생성 → 결제 승인
            return client.post('/api/payments/confirm/', ...)

        # Act
        with ThreadPoolExecutor(max_workers=100) as executor:
            results = list(executor.map(make_payment, users))

        # Assert
        success_count = sum(1 for r in results if r.status_code in [200, 202])
        assert success_count >= 950, f"95% 이상 성공해야 함: {success_count}/1000"

        # 재고 검증
        product.refresh_from_db()
        assert product.stock >= 0, "재고는 음수가 될 수 없음"
```

**예상 소요 시간**: 2시간

---

### Task 4-2: Celery 모니터링 설정

**작업 내용**:

1. **Flower 설치 및 설정**:

```bash
pip install flower
```

2. **`docker-compose.yml`에 추가**:

```yaml
services:
  flower:
    image: mher/flower
    command: celery -A myproject flower
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - redis
```

3. **모니터링 대시보드 접속**: `http://localhost:5555`

**예상 소요 시간**: 30분

---

## Phase 5: 모니터링 및 배포

### Task 5-1: 로깅 및 알림 설정

**작업 내용**:

1. **Sentry 연동** (선택사항):

```python
# settings.py
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[CeleryIntegration()],
)
```

2. **Celery 에러 알림**:

```python
# celery.py
from celery.signals import task_failure

@task_failure.connect
def task_failure_handler(sender, task_id, exception, **kwargs):
    logger.error(f"Task failed: {sender.name}, task_id={task_id}, error={exception}")
    # Slack/Email 알림
```

**예상 소요 시간**: 1시간

---

## 📝 각 Phase별 Command 요약

### Phase 0: 사전 준비
```bash
# Task 0-1
"Celery 설정 검증 및 Queue 구조 설계를 진행해줘"

# Task 0-2
"Celery 테스트 환경을 설정해줘"
```

### Phase 1: 결제 비동기화
```bash
# Task 1-1
"Toss API 호출 태스크를 작성해줘"

# Task 1-2
"결제 승인 최종 처리 태스크를 작성해줘"

# Task 1-3
"PaymentService를 비동기 방식으로 리팩토링해줘"

# Task 1-4
"결제 View를 비동기 처리 방식으로 수정해줘"

# Task 1-5
"결제 비동기 처리 테스트를 작성해줘"
```

### Phase 2: 주문 하이브리드
```bash
# Task 2-1
"주문 무거운 작업 처리 태스크를 작성해줘"

# Task 2-2
"OrderService를 하이브리드 방식으로 리팩토링해줘"

# Task 2-3
"주문 View를 하이브리드 처리 방식으로 수정해줘"
```

### Phase 3: 포인트 최적화
```bash
# Task 3-1
"포인트 적립 비동기 태스크를 작성해줘"
```

### Phase 4: 성능 테스트
```bash
# Task 4-1
"1000명 동시 접속 부하 테스트를 작성해줘"

# Task 4-2
"Celery Flower 모니터링을 설정해줘"
```

---

## ⏱️ 전체 예상 소요 시간

| Phase | 예상 시간 | 누적 시간 |
|-------|----------|----------|
| Phase 0 | 1.5시간 | 1.5시간 |
| Phase 1 | 9.5시간 | 11시간 |
| Phase 2 | 6시간 | 17시간 |
| Phase 3 | 1.5시간 | 18.5시간 |
| Phase 4 | 2.5시간 | 21시간 |
| Phase 5 | 1시간 | 22시간 |

**총 예상 시간**: 약 22시간 (3-4일 작업량)

---

## 🎯 우선순위

1. **최우선**: Phase 1 (결제 비동기화) - 가장 큰 병목 해결
2. **높음**: Phase 2 (주문 하이브리드) - UX 개선
3. **중간**: Phase 3 (포인트 최적화) - 성능 개선
4. **낮음**: Phase 4-5 (테스트/모니터링) - 안정성 확보

---

## 📌 주의사항

1. **롤백 전략**: 각 Phase마다 기존 코드를 주석 처리하고 새 코드 추가
2. **점진적 배포**: 한 번에 모든 Phase를 배포하지 말고, Phase별로 배포 후 검증
3. **테스트 우선**: 각 Task마다 테스트 작성 후 구현
4. **문서화**: 변경사항을 CHANGELOG.md에 기록

---

## 🚀 시작 준비

이제 다음과 같이 지시해주세요:

```
"Phase 0의 Task 0-1부터 시작해줘"
```

각 Task가 완료되면 다음 Task로 진행하겠습니다!
