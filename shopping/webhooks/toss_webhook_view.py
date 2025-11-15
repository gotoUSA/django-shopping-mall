from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from ..models.cart import Cart
from ..models.payment import Payment, PaymentLog
from ..models.product import Product
from ..serializers.payment_serializers import PaymentWebhookSerializer
from ..utils.toss_payment import TossPaymentClient

# 로거 설정
logger = logging.getLogger(__name__)


@csrf_exempt  # 외부 서비스 호출이므로 CSRF 검증 제외
@api_view(["POST"])
@permission_classes([AllowAny])  # 토스페이먼츠 서버에서 호출하므로 인증 불필요
def toss_webhook(request: Request) -> Response:
    """
    토스페이먼츠 웹훅 처리

    토스페이먼츠에서 결제 상태가 변경되면 이 엔드포인트로 알림을 보냅니다.

    POST /api/webhooks/toss/

    웹훅 이벤트 타입:
    - PAYMENT.DONE: 결제 완료
    - PAYMENT.CANCELED: 결제 취소
    - PAYMENT.FAILED: 결제 실패
    - PAYMENT.PARTIAL_CANCELED: 부분 취소 (미지원)

    보안:
    - 웹훅 서명 검증으로 토스페이먼츠에서 보낸 요청인지 확인
    - 중복 처리 방지
    """

    # 1. 웹훅 서명 검증
    signature = request.headers.get("X-Toss-Webhook-Signature")

    if not signature:
        logger.warning("Webhook signature missing")
        return Response({"error": "Signature missing"}, status=status.HTTP_401_UNAUTHORIZED)

    # 토스페이먼츠 클라이언트로 서명 검증
    toss_client = TossPaymentClient()

    try:
        webhook_data = request.data

        # 서명 검증
        if not toss_client.verify_webhook(webhook_data, signature):
            logger.warning("Invalid webhook signature")
            return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

    except Exception as e:
        logger.error(f"Webhook signature verification error: {str(e)}")
        return Response(
            {"error": "Signature verification failed"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 2. 웹훅 데이터 파싱
    serializer = PaymentWebhookSerializer(data=webhook_data)

    if not serializer.is_valid():
        logger.error(f"Invalid webhook data: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # 지원하지 않는 이벤트는 무시
    if not serializer.is_supported:
        return Response({"message": "Event ignored"}, status=status.HTTP_200_OK)

    event_type = serializer.validated_data["eventType"]
    event_data = serializer.validated_data["data"]

    # 3. 이벤트 처리
    try:
        if event_type == "PAYMENT.DONE":
            handle_payment_done(event_data)

        elif event_type == "PAYMENT.CANCELED":
            handle_payment_canceled(event_data)

        elif event_type == "PAYMENT.FAILED":
            handle_payment_failed(event_data)

        elif event_type == "PAYMENT.PARTIAL_CANCELED":
            # 부분 취소는 향후 지원
            logger.info(f"Partial cancel event received: {event_data}")

        return Response({"message": "Webhook processed"}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return Response({"error": "Processing failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@transaction.atomic
def handle_payment_done(event_data: dict[str, Any]) -> None:
    """
    결제 완료 이벤트 처리

    결제창에서 결제 완류 후 confirm API 호출 전에
    웹훅이 먼저 도착할 수 있으므로 중복 처리 방지 필요
    """
    event_data.get("paymentKey")
    order_id = event_data.get("orderId")

    try:
        payment = Payment.objects.select_for_update().get(toss_order_id=order_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment not found for order_id: {order_id}")
        return

    # 이미 처리된 결제인지 확인 (중복 방지)
    if payment.is_paid:
        logger.info(f"Payment already processed: {order_id}")
        return

    # Payment 정보 업데이트
    payment.mark_as_paid(event_data)

    # Order 상태 변경
    order = payment.order

    # 이미 paid 상태면 스킵 (confirm API에서 이미 처리)
    if order.status == "paid":
        logger.info(f"Order already paid: {order_id}")
        return

    # 재고 차감 및 sold_count 증가 (결제 완료 시점)
    if order.status != "paid":
        for order_item in order.order_items.select_for_update():
            if order_item.product:
                # 재고 차감 및 sold_count 증가 (F 객체로 안전하게)
                Product.objects.filter(pk=order_item.product.pk).update(
                    stock=F("stock") - order_item.quantity,
                    sold_count=F("sold_count") + order_item.quantity,
                )

    # 주문 상태 변경
    order.status = "paid"
    order.payment_method = payment.method or "card"
    order.save(update_fields=["status", "payment_method", "updated_at"])

    # 장바구니 비활성화
    Cart.objects.filter(user=order.user, is_active=True).update(is_active=False)

    # 포인트 적립
    if order.user:
        points_to_add = int(payment.amount * Decimal(0.01))
        if points_to_add > 0:
            order.user.add_points(points_to_add)

    # 웹훅 로그
    PaymentLog.objects.create(
        payment=payment,
        log_type="webhook",
        message="결제 완료 웹훅 처리",
        data=event_data,
    )

    logger.info(f"Payment done webhook processed: {order_id}")


@transaction.atomic
def handle_payment_canceled(event_data: dict[str, Any]) -> None:
    """
    결제 취소 이벤트 처리
    """
    event_data.get("paymentKey")
    order_id = event_data.get("orderId")

    try:
        payment = Payment.objects.select_for_update().get(toss_order_id=order_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment not found for order_id: {order_id}")
        return

    # 이미 취소된 결제인지 확인
    if payment.is_canceled:
        logger.info(f"Payment already canceled: {order_id}")
        return

    # Payment 정보 업데이트
    payment.mark_as_canceled(event_data)

    # Order 상태 변경
    order = payment.order

    # 이미 cancelled 상태면 스킵
    if order.status == "canceled":
        logger.info(f"Order already cancelled: {order_id}")
        return

    # 재고 복구 (paid 상태였던 경우만)
    if order.status in ["paid", "preparing"]:
        for order_item in order.order_items.all():
            if order_item.product:
                Product.objects.filter(pk=order_item.product.pk).update(
                    stock=F("stock") + order_item.quantity,
                    sold_count=F("sold_count") - order_item.quantity,
                )

    # 포인트 회수 (상태 변경 전)
    if order.user and order.status in ["paid", "preparing"]:
        points_to_deduct = int(payment.amount * Decimal(0.01))
        if points_to_deduct > 0:
            order.user.use_points(points_to_deduct)

    # 주문 상태 변경
    order.status = "canceled"
    order.save(update_fields=["status", "updated_at"])

    # 웹훅 로그
    PaymentLog.objects.create(
        payment=payment,
        log_type="webhook",
        message="결제 취소 웹훅 처리",
        data=event_data,
    )

    logger.info(f"Payment canceled webhook processed: {order_id}")


def handle_payment_failed(event_data: dict[str, Any]) -> None:
    """
    결제 실패 이벤트 처리
    """
    order_id = event_data.get("orderId")
    fail_reason = event_data.get("failReason", "")

    try:
        payment = Payment.objects.get(toss_order_id=order_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment not found for order_id: {order_id}")
        return

    # 이미 실패 처리된 경우 스킵
    if payment.status in ["aborted", "failed"]:
        logger.info(f"Payment already failed: {order_id}")
        return

    # Payment 실패 처리
    payment.mark_as_failed(fail_reason)

    # 웹훅 로그
    PaymentLog.objects.create(
        payment=payment,
        log_type="webhook",
        message=f"결제 실패 웹훅 처리: {fail_reason}",
        data=event_data,
    )

    logger.info(f"Payment failed webhook processed: {order_id}")
