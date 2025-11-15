"""결제 서비스 레이어"""

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest

from ..models.cart import Cart
from ..models.order import Order
from ..models.payment import Payment, PaymentLog
from ..models.point_history import PointHistory
from ..models.product import Product
from ..utils.toss_payment import TossPaymentClient, TossPaymentError


class PaymentCancelError(Exception):
    """결제 취소 관련 에러"""

    pass


class PaymentConfirmError(Exception):
    """결제 승인 관련 에러"""

    pass


class PaymentService:
    """결제 관련 비즈니스 로직을 처리하는 서비스"""

    @staticmethod
    @transaction.atomic
    def confirm_payment(payment: Payment, payment_key: str, order_id: str, amount: int, user) -> dict[str, Any]:
        """
        결제 승인 처리

        Args:
            payment: 결제 객체
            payment_key: 토스페이먼츠 결제 키
            order_id: 주문 번호
            amount: 결제 금액
            user: 요청한 사용자

        Returns:
            결제 승인 결과

        Raises:
            PaymentConfirmError: 결제 승인 실패
            TossPaymentError: 토스페이먼츠 API 에러
        """
        order = payment.order

        # 토스페이먼츠 API 클라이언트
        toss_client = TossPaymentClient()

        # 1. 토스페이먼츠에 결제 승인 요청
        payment_data = toss_client.confirm_payment(
            payment_key=payment_key,
            order_id=order_id,
            amount=amount,
        )

        # 2. Payment 정보 업데이트
        payment.mark_as_paid(payment_data)

        # 3. 재고 차감 (sold_count 증가, Product 락으로 동시성 제어)
        for order_item in order.order_items.all():
            if order_item.product:
                # Product를 락으로 보호
                product = Product.objects.select_for_update().get(pk=order_item.product.pk)
                # sold_count만 증가 (F 객체로 안전하게)
                Product.objects.filter(pk=product.pk).update(sold_count=F("sold_count") + order_item.quantity)

        # 4. 주문 상태 변경
        order.status = "paid"
        order.payment_method = payment.method
        order.save(update_fields=["status", "payment_method", "updated_at"])

        # 5. 장바구니 비활성화
        Cart.objects.filter(user=user, is_active=True).update(is_active=False)

        # 6. 포인트 적립 (구매 금액의 1%)
        points_to_add = 0
        # 포인트로만 결제한 경우는 적립하지 않음
        if order.final_amount > 0:
            # 등급별 적립률 적용
            earn_rate = user.get_earn_rate()  # 1, 2, 3, 5 (%)
            points_to_add = int(order.final_amount * Decimal(earn_rate) / Decimal("100"))

            if points_to_add > 0:
                # 포인트 적립
                user.add_points(points_to_add)

                # 주문에 적립 포인트 기록
                order.earned_points = points_to_add
                order.save(update_fields=["earned_points"])

                # 포인트 적립 이력 기록
                PointHistory.create_history(
                    user=user,
                    points=points_to_add,
                    type="earn",
                    order=order,
                    description=f"주문 #{order.order_number} 구매 적립",
                    metadata={
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "payment_amount": str(order.final_amount),
                        "earn_rate": f"{earn_rate}%",
                        "membership_level": user.membership_level,
                    },
                )

                # 포인트 적립 로그
                PaymentLog.objects.create(
                    payment=payment,
                    log_type="approve",
                    message=f"포인트 {points_to_add}점 적립",
                    data={"points": points_to_add},
                )
        else:
            # 포인트 전액 결제 로그
            if order.used_points > 0:
                PaymentLog.objects.create(
                    payment=payment,
                    log_type="approve",
                    message=f"포인트 {order.used_points}점으로 전액 결제",
                    data={"used_points": order.used_points},
                )

        # 7. 결제 승인 로그
        PaymentLog.objects.create(
            payment=payment,
            log_type="approve",
            message="결제 승인 완료",
            data=payment_data,
        )

        return {
            "payment": payment,
            "points_earned": points_to_add,
            "receipt_url": payment.receipt_url,
        }

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

            # 8. 재고 복구 (Product 락으로 동시성 제어)
            for order_item in order.order_items.all():
                if order_item.product:  # 상품이 삭제되지 않았다면
                    # Product를 락으로 보호
                    product = Product.objects.select_for_update().get(pk=order_item.product.pk)
                    # sold_count가 음수가 되지 않도록 Greatest 사용
                    Product.objects.filter(pk=product.pk).update(
                        stock=F("stock") + order_item.quantity,
                        sold_count=Greatest(F("sold_count") - order_item.quantity, 0),
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
                user.use_points(points_deducted)

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
            # 토스 API 에러 (트랜잭션이 깨지기 때문에 로그는 나중에)
            error_message = f"결제 취소 실패: {e.message}"
            error_data = {"error_code": e.code, "error_message": e.message}

            # 트랜잭션 밖에서 로그 기록
            try:
                from django.db import transaction
                with transaction.atomic():
                    PaymentLog.objects.create(
                        payment=payment,
                        log_type="error",
                        message=error_message,
                        data=error_data,
                    )
            except Exception:
                pass  # 로그 실패는 무시

            raise PaymentCancelError(error_message)

        except Exception as e:
            # 기타 에러 (트랜잭션이 깨지기 때문에 로그는 나중에)
            error_message = f"결제 취소 중 오류 발생: {str(e)}"
            error_data = {"error": str(e)}

            # 트랜잭션 밖에서 로그 기록
            try:
                from django.db import transaction
                with transaction.atomic():
                    PaymentLog.objects.create(
                        payment=payment,
                        log_type="error",
                        message=error_message,
                        data=error_data,
                    )
            except Exception:
                pass  # 로그 실패는 무시

            raise
