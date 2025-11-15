"""결제 서비스 레이어"""

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F

from ..models.order import Order
from ..models.payment import Payment, PaymentLog
from ..models.point_history import PointHistory
from ..models.product import Product
from ..utils.toss_payment import TossPaymentClient, TossPaymentError


class PaymentCancelError(Exception):
    """결제 취소 관련 에러"""

    pass


class PaymentService:
    """결제 관련 비즈니스 로직을 처리하는 서비스"""

    @staticmethod
    @transaction.atomic
    def cancel_payment(payment_id: int, user, cancel_reason: str) -> dict[str, Any]:
        """
        결제 취소 처리

        동시성 제어를 위해 락을 먼저 획득한 후 모든 검증을 수행합니다.

        Args:
            payment_id: 취소할 결제 ID
            user: 요청한 사용자
            cancel_reason: 취소 사유

        Returns:
            취소된 결제 정보

        Raises:
            Payment.DoesNotExist: 결제 정보를 찾을 수 없음
            PaymentCancelError: 취소 불가능한 상태
        """
        # 1. 동시성 제어: Payment를 락으로 보호하며 조회
        try:
            payment = Payment.objects.select_for_update().get(
                id=payment_id, order__user=user
            )
        except Payment.DoesNotExist:
            raise PaymentCancelError("결제 정보를 찾을 수 없습니다.")

        # 2. 중복 취소 방지: 이미 취소된 결제인지 확인
        if payment.is_canceled:
            raise PaymentCancelError("이미 취소된 결제입니다.")

        # 3. 취소 가능한 상태인지 확인
        if payment.status != "done":
            raise PaymentCancelError(
                f"취소할 수 없는 결제 상태입니다: {payment.get_status_display()}"
            )

        # 4. Order를 락으로 보호
        order = Order.objects.select_for_update().get(pk=payment.order_id)

        # 5. 토스페이먼츠 API 클라이언트
        toss_client = TossPaymentClient()

        # 포인트 변수 초기화
        points_refunded = 0
        points_deducted = 0

        try:
            # 6. 토스페이먼츠에 취소 요청
            cancel_data = toss_client.cancel_payment(
                payment_key=payment.payment_key, cancel_reason=cancel_reason
            )

            # 7. Payment 정보 업데이트
            payment.mark_as_canceled(cancel_data)

            # 8. 재고 복구
            for order_item in order.order_items.all():
                if order_item.product:  # 상품이 삭제되지 않았다면
                    Product.objects.filter(pk=order_item.product.pk).update(
                        stock=F("stock") + order_item.quantity,
                        sold_count=F("sold_count") - order_item.quantity,
                    )

            # 9. 주문 상태 변경
            order.status = "canceled"
            order.save(update_fields=["status", "updated_at"])

            # 10. 포인트 처리
            # 10-1. 사용한 포인트 환불
            if order.used_points > 0:
                points_refunded = order.used_points
                user.add_points(points_refunded)

                # 포인트 환불 이력 기록
                PointHistory.create_history(
                    user=user,
                    points=order.used_points,
                    type="cancel_refund",
                    order=order,
                    description=f"주문 #{order.order_number} 취소로 인한 포인트 환불",
                    metadata={
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "cancel_reason": cancel_reason,
                    },
                )

                # 환불 로그
                PaymentLog.objects.create(
                    payment=payment,
                    log_type="cancel",
                    message=f"사용 포인트 {order.used_points}점 환불",
                    data={"points": order.used_points},
                )

            # 10-2. 적립된 포인트 차감
            if order.earned_points > 0:
                points_deducted = order.earned_points
                user.deduct_points(points_deducted)

                # 포인트 차감 이력 기록
                PointHistory.create_history(
                    user=user,
                    points=-order.earned_points,
                    type="cancel_deduct",
                    order=order,
                    description=f"주문 #{order.order_number} 취소로 인한 적립 포인트 차감",
                    metadata={
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "cancel_reason": cancel_reason,
                    },
                )

                # 차감 로그
                PaymentLog.objects.create(
                    payment=payment,
                    log_type="cancel",
                    message=f"적립 포인트 {order.earned_points}점 차감",
                    data={"points": -order.earned_points},
                )

            # 취소 성공 로그
            PaymentLog.objects.create(
                payment=payment,
                log_type="cancel",
                message="결제가 성공적으로 취소되었습니다.",
                data={
                    "cancel_reason": cancel_reason,
                    "canceled_amount": str(payment.canceled_amount),
                    "points_refunded": points_refunded,
                    "points_deducted": points_deducted,
                },
            )

            # payment 저장 (mark_as_canceled에서 save 호출)
            # 응답 데이터 반환
            return {
                "payment_id": payment.id,
                "status": payment.status,
                "canceled_amount": payment.canceled_amount,
                "cancel_reason": payment.cancel_reason,
                "canceled_at": payment.canceled_at,
                "points_refunded": points_refunded,
                "points_deducted": points_deducted,
            }

        except TossPaymentError as e:
            # 토스 API 에러
            PaymentLog.objects.create(
                payment=payment,
                log_type="error",
                message=f"결제 취소 실패: {e.message}",
                data={"error_code": e.code, "error_message": e.message},
            )
            raise PaymentCancelError(f"결제 취소 실패: {e.message}")

        except Exception as e:
            # 기타 에러
            PaymentLog.objects.create(
                payment=payment,
                log_type="error",
                message=f"결제 취소 중 오류 발생: {str(e)}",
                data={"error": str(e)},
            )
            raise
