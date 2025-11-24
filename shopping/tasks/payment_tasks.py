"""결제 관련 Celery 태스크"""

from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import transaction
from django.db.models import F

from ..models.cart import Cart
from ..models.order import Order
from ..models.payment import Payment, PaymentLog
from ..models.product import Product
from ..utils.toss_payment import TossPaymentClient, TossPaymentError

logger = get_task_logger(__name__)


@shared_task(
    name="shopping.tasks.payment_tasks.call_toss_confirm_api",
    queue="external_api",
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

        # 에러 로그 기록 및 상태 업데이트 (Payment는 order_id로 찾아야 함)
        try:
            payment = Payment.objects.get(toss_order_id=order_id)
            payment.status = "aborted"
            payment.save(update_fields=["status"])

            # Order 상태도 failed로 변경
            order = payment.order
            order.status = "failed"
            order.failure_reason = f"결제 실패: {e.message}"
            order.save(update_fields=["status", "failure_reason", "updated_at"])

            PaymentLog.objects.create(
                payment=payment,
                log_type="error",
                message=f"Toss API 호출 실패: {e.message}",
                data={"error_code": e.code, "error_message": e.message},
            )
        except Exception as log_error:
            logger.error(f"에러 로그 기록 실패: {str(log_error)}")

        # 재시도 (네트워크 오류 등)
        if e.code in ["NETWORK_ERROR", "TIMEOUT"]:
            raise call_toss_confirm_api.retry(exc=e)

        # 재시도 불가능한 오류는 그대로 raise
        raise


@shared_task(
    name="shopping.tasks.payment_tasks.finalize_payment_confirm",
    queue="payment_critical",
    max_retries=5,
    default_retry_delay=10,
)
def finalize_payment_confirm(toss_response: dict, payment_id: int, user_id: int) -> dict:
    """
    Toss API 결과를 받아 결제 최종 처리
    - Payment 상태 업데이트
    - 재고 차감 (sold_count 증가)
    - Order 상태 변경
    - 장바구니 비활성화
    - 포인트 적립 태스크 트리거 (비동기)

    Args:
        toss_response: Toss API 응답 데이터
        payment_id: Payment ID
        user_id: 사용자 ID

    Returns:
        처리 결과
    """
    from ..models.user import User

    logger.info(f"결제 최종 처리 시작: payment_id={payment_id}")

    try:
        with transaction.atomic():
            # 1. Payment 업데이트 (짧은 트랜잭션)
            payment = Payment.objects.select_for_update().get(pk=payment_id)

            # 중복 처리 방지
            if payment.is_paid:
                logger.warning(f"이미 처리된 결제: payment_id={payment_id}")
                return {"status": "already_processed", "payment_id": payment_id}

            payment.mark_as_paid(toss_response)
            order = payment.order

            # 2. 재고 차감 (sold_count만 증가, stock은 주문 생성 시 이미 차감)
            for order_item in order.order_items.select_for_update():
                if order_item.product:
                    Product.objects.filter(pk=order_item.product.pk).update(
                        sold_count=F("sold_count") + order_item.quantity
                    )

            # 3. Order 상태 변경
            order.status = "paid"
            order.payment_method = payment.method
            order.save(update_fields=["status", "payment_method", "updated_at"])

            # 4. 장바구니 비활성화
            Cart.objects.filter(user_id=user_id, is_active=True).update(is_active=False)

            # 5. 로그 기록
            PaymentLog.objects.create(
                payment=payment,
                log_type="approve",
                message="결제 승인 완료",
                data=toss_response,
            )

        logger.info(f"결제 최종 처리 완료: payment_id={payment_id}, order_id={order.id}")

        # 6. 포인트 적립은 별도 태스크로 (비동기)
        from .point_tasks import add_points_after_payment

        if order.final_amount > 0:
            add_points_after_payment.delay(user_id, order.id)

        return {
            "status": "success",
            "payment_id": payment_id,
            "order_id": order.id,
        }

    except Exception as e:
        logger.error(f"결제 최종 처리 실패: payment_id={payment_id}, error={str(e)}")

        # 재시도
        raise finalize_payment_confirm.retry(exc=e)
