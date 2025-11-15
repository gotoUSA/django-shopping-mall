import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models.cart import Cart
from ..models.order import Order
from ..models.payment import Payment, PaymentLog
from ..models.point import PointHistory
from ..models.product import Product
from ..serializers.payment_serializers import (
    PaymentCancelSerializer,
    PaymentConfirmSerializer,
    PaymentFailSerializer,
    PaymentRequestSerializer,
    PaymentSerializer,
)
from ..utils.toss_payment import TossPaymentClient, TossPaymentError, get_error_message

# 로거 설정
logger = logging.getLogger(__name__)


class PaymentRequestView(APIView):
    """
    결제 요청 뷰

    프론트엔드에서 토스페이먼츠 결제창을 열기 전에 호출합니다.
    결제에 필요한 정보를 반환합니다.

    POST /api/payments/request/
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        결제 요청 생성

        요청 본문:
        {
            "order_id": 1
        }

        응답:
        {
            "payment_id": 1,
            "order_id": "20250111000001",
            "order_name": "노트북 외 2건",
            "customer_name": "홍길동",
            "customer_email": "user@example.com",
            "amount": 1500000,
            "client_key": "test_ck_...",  // 토스 클라이언트 키
            "success_url": "http://localhost:8000/api/payments/success",
            "fail_url": "http://localhost:8000/api/payments/fail"
        }
        """
        # 이메일 인증 체크
        if not request.user.is_email_verified:
            return Response(
                {"error": "이메일 인증이 필요합니다. 먼저 이메일을 인증해주세요."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PaymentRequestSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            # Payment 생성
            payment = serializer.save()
            order = payment.order

            # 주문명 생성 (첫 상품명 + 나머지 개수)
            order_items = order.order_items.all()
            first_item = order_items.first()

            if order_items.count() > 1:
                order_name = f"{first_item.product_name} 외 {order_items.count() - 1}건"
            else:
                order_name = first_item.product_name

            # 결제 정보 반환
            response_data = {
                "payment_id": payment.id,
                "order_id": payment.order_id,
                "order_name": order_name,
                "customer_name": request.user.get_full_name() or request.user.username,
                "customer_email": request.user.email,
                "amount": int(payment.amount),
                "client_key": settings.TOSS_CLIENT_KEY,
                "success_url": f"{settings.FRONTEND_URL}/payment/success",
                "fail_url": f"{settings.FRONTEND_URL}/payment/fail",
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PaymentConfirmView(APIView):
    """
    결제 승인 뷰

    사용자가 토스페이먼츠 결제창에서 결제를 완료하면
    프론트엔드에서 이 API를 호출하여 결제를 승인합니다.

    POST /api/payments/confirm/
    """

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        """
        결제 승인 처리

        요청 본문:
        {
            "order_id": "20250111000001",
            "payment_key": "test_payment_key_...",
            "amount": 1500000
        }
        """
        # 이메일 인증 체크 (보안)
        if not request.user.is_email_verified:
            logger.warning(f"미인증 사용자 결제 승인 시도: user_id={request.user.id}, " f"email={request.user.email}")
            return Response(
                {
                    "error": "이메일 인증이 필요합니다.",
                    "message": "결제를 완료하려면 먼저 이메일을 인증해주세요.",
                    "verification_required": True,
                    "verification_url": "/api/email-verification/send/",  # 인증 메일 발송 URL
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = PaymentConfirmSerializer(data=request.data, context={"request": request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 동시성 제어: Payment를 락으로 보호
        payment = Payment.objects.select_for_update().get(pk=serializer.payment.pk)

        # 중복 처리 방지: 이미 완료된 결제인지 확인
        if payment.is_paid:
            return Response(
                {"error": "이미 완료된 결제입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order = payment.order

        # 토스페이먼츠 API 클라이언트
        toss_client = TossPaymentClient()

        try:
            # 1. 토스페이먼츠에 결제 승인 요청
            payment_data = toss_client.confirm_payment(
                payment_key=serializer.validated_data["payment_key"],
                order_id=serializer.validated_data["order_id"],
                amount=serializer.validated_data["amount"],
            )

            # 2. Payment 정보 업데이트
            payment.mark_as_paid(payment_data)

            # 3. 재고 차감 (select_for_update로 동시성 제어)
            for order_item in order.order_items.select_for_update():
                if order_item.product:
                    # sold_count만 증가 (F 객체로 안전하게)
                    Product.objects.filter(pk=order_item.product.pk).update(sold_count=F("sold_count") + order_item.quantity)

            # 4. 주문 상태 변경
            order.status = "paid"
            order.payment_method = payment.method
            order.save(update_fields=["status", "payment_method", "updated_at"])

            # 5. 장바구니 비활성화
            Cart.objects.filter(user=request.user, is_active=True).update(is_active=False)

            # 6. 포인트 차감 (Order 생성 시 차감되지 않은 경우 처리)
            # 일반적으로 OrderSerializer에서 차감되지만 (order_serializers.py:313),
            # 테스트 등에서 Order를 직접 생성한 경우 차감되지 않을 수 있음
            if order.used_points > 0:
                # 이미 차감되었는지 확인 (PointHistory에 사용 이력이 있는지)
                already_deducted = PointHistory.objects.filter(
                    user=request.user,
                    order=order,
                    type="use",
                ).exists()

                if not already_deducted:
                    # 동시성 제어: User를 락으로 보호
                    from ..models.user import User
                    user = User.objects.select_for_update().get(pk=request.user.pk)

                    # 포인트 차감
                    user.use_points(order.used_points)

                    # 포인트 사용 이력 기록
                    PointHistory.create_history(
                        user=user,
                        points=-order.used_points,
                        type="use",
                        order=order,
                        description=f"주문 #{order.order_number} 결제 시 포인트 사용",
                        metadata={
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "total_amount": str(order.total_amount),
                            "used_points": order.used_points,
                            "final_amount": str(order.final_amount),
                        },
                    )

                    # request.user도 업데이트 (이후 적립 시 사용)
                    request.user.refresh_from_db()

            # 7. 포인트 적립
            # 포인트로만 결제한 경우는 적립하지 않음
            if order.final_amount > 0:
                # 등급별 적립률 적용
                earn_rate = request.user.get_earn_rate()  # 1, 2, 3, 5 (%)
                points_to_add = int(order.final_amount * Decimal(earn_rate) / Decimal("100"))

                if points_to_add > 0:
                    # 포인트 적립
                    request.user.add_points(points_to_add)

                    # 주문에 적립 포인트 기록
                    order.earned_points = points_to_add
                    order.save(update_fields=["earned_points"])

                    # 포인트 적립 이력 기록
                    PointHistory.create_history(
                        user=request.user,
                        points=points_to_add,
                        type="earn",
                        order=order,
                        description=f"주문 #{order.order_number} 구매 적립",
                        metadata={
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "payment_amount": str(order.final_amount),
                            "earn_rate": f"{earn_rate}%",
                            "membership_level": request.user.membership_level,
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
                points_to_add = 0
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

            # 응답
            return Response(
                {
                    "message": "결제가 완료되었습니다.",
                    "payment": PaymentSerializer(payment).data,
                    "points_earned": points_to_add,
                    "receipt_url": payment.receipt_url,
                },
                status=status.HTTP_200_OK,
            )

        except TossPaymentError as e:
            # 토스페이먼츠 API 에러
            logger.error(f"Toss payment error: {e.to_dict()}")

            # 결제 실패 처리
            payment.mark_as_failed(e.message)

            # 에러 로그
            PaymentLog.objects.create(
                payment=payment,
                log_type="error",
                message=f"결제 승인 실패: {e.message}",
                data=e.to_dict(),
            )

            return Response(
                {
                    "error": get_error_message(e.code),
                    "code": e.code,
                    "message": e.message,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            # 기타 에러
            logger.error(f"Payment confirm error: {str(e)}")

            # 결제 실패 처리
            payment.mark_as_failed(str(e))

            # 에러 로그
            PaymentLog.objects.create(
                payment=payment,
                log_type="error",
                message=f"서버 오류: {str(e)}",
                data={"error": str(e)},
            )

            return Response(
                {"error": "결제 처리 중 오류가 발생했습니다.", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PaymentCancelView(APIView):
    """
    결제 취소 뷰

    완료된 결제를 취소합니다. (전체 취소만 지원)

    POST /api/payments/cancel/
    """

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        """
        결제 취소 처리

        요청 본문:
        {
            "payment_id": 1,
            "cancel_reason": "고객 변심"
        }
        """
        serializer = PaymentCancelSerializer(data=request.data, context={"request": request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 동시성 제어: Payment를 먼저 락으로 보호
        payment = Payment.objects.select_for_update().get(pk=serializer.payment.pk)

        # 중복 취소 방지: 이미 취소된 결제인지 확인
        if payment.is_canceled:
            return Response(
                {"error": "이미 취소된 결제입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 취소 가능한 상태인지 확인
        if not payment.can_cancel:
            return Response(
                {"error": f"취소할 수 없는 결제 상태입니다: {payment.get_status_display()}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Order를 락으로 보호
        order = Order.objects.select_for_update().get(pk=payment.order.pk)

        # 이미 취소된 주문인지 확인 (중복 취소 방지)
        if order.status == "canceled":
            return Response(
                {"error": "이미 취소된 주문입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cancel_reason = serializer.validated_data["cancel_reason"]

        # 토스페이먼츠 API 클라이언트
        toss_client = TossPaymentClient()

        # 포인트 변수 초기화 (함수 시작 시)
        points_refunded = 0
        points_deducted = 0

        try:
            # 1. 토스페이먼츠에 취소 요청
            cancel_data = toss_client.cancel_payment(payment_key=payment.payment_key, cancel_reason=cancel_reason)

            # 2. Payment 정보 업데이트
            payment.mark_as_canceled(cancel_data)

            # 3. 재고 복구
            for order_item in order.order_items.all():
                if order_item.product:  # 상품이 삭제되지 않았다면
                    Product.objects.filter(pk=order_item.product.pk).update(
                        stock=F("stock") + order_item.quantity,
                        sold_count=F("sold_count") - order_item.quantity,
                    )

            # 4. 주문 상태 변경
            order.status = "canceled"
            order.save(update_fields=["status", "updated_at"])

            # 5. 포인트 처리
            # 5-1. 사용한 포인트 환불
            if order.used_points > 0:
                points_refunded = order.used_points  # 변수에 저장
                request.user.add_points(points_refunded)

                # 포인트 환불 이력 기록
                PointHistory.create_history(
                    user=request.user,
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
                    data={"refunded_points": order.used_points},
                )

            # 5-2. 적립했던 포인트 회수
            if order.earned_points > 0:
                # 포인트 차감 (보유 포인트가 부족한 경우 처리)
                points_deducted = min(order.earned_points, request.user.points)
                if points_deducted > 0:
                    request.user.use_points(points_deducted)

                    # 포인트 차감 이력 기록
                    PointHistory.create_history(
                        user=request.user,
                        points=-points_deducted,
                        type="cancel_deduct",
                        order=order,
                        description=f"주문 #{order.order_number} 취소로 인한 적립 포인트 회수",
                        metadata={
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "original_earned": order.earned_points,
                            "actual_deducted": points_deducted,
                        },
                    )
                    # 포인트 회수 로그
                    PaymentLog.objects.create(
                        payment=payment,
                        log_type="cancel",
                        message=f"적립 포인트 {points_deducted}점 회수",
                        data={"deducted_points": points_deducted},
                    )

            # 6. 취소 로그
            PaymentLog.objects.create(
                payment=payment,
                log_type="cancel",
                message=f"결제 취소 완료: {cancel_reason}",
                data=cancel_data,
            )

            return Response(
                {
                    "message": "결제가 취소되었습니다.",
                    "payment": PaymentSerializer(payment).data,
                    "refund_amount": int(payment.canceled_amount),
                    "refunded_points": points_refunded,
                    "deducted_points": points_deducted,
                },
                status=status.HTTP_200_OK,
            )

        except TossPaymentError as e:
            # 토스페이먼츠 API 에러
            logger.error(f"Toss cancel error: {e.to_dict()}")

            # 에러 로그
            PaymentLog.objects.create(
                payment=payment,
                log_type="error",
                message=f"결제 취소 실패: {e.message}",
                data=e.to_dict(),
            )

            return Response(
                {
                    "error": get_error_message(e.code),
                    "code": e.code,
                    "message": e.message,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            # 기타 에러
            logger.error(f"Payment cancel error: {str(e)}")

            # 에러 로그
            PaymentLog.objects.create(
                payment=payment,
                log_type="error",
                message=f"취소 중 오류: {str(e)}",
                data={"error": str(e)},
            )

            return Response(
                {
                    "message": "결제가 취소되었습니다.",
                    "payment": PaymentSerializer(payment).data,
                    "refund_amount": int(payment.canceled_amount),
                    "refunded_points": (order.used_points if order.used_points > 0 else 0),
                    "deducted_points": (points_deducted if order.earned_points > 0 else 0),
                },
                status=status.HTTP_200_OK,
            )


class PaymentFailView(APIView):
    """
    결제 실패 처리 뷰

    토스페이먼츠 결제창에서 실패/취소 시 호출됩니다.
    Payment 상태를 aborted로 변경하고 실패 로그를 기록합니다.

    POST /api/payments/fail/
    """

    permission_classes = [permissions.AllowAny]  # 토스 콜백은 인증 불필요

    def post(self, request):
        """
        결제 실패 처리

        요청 본문:
        {
            "code": "USER_CANCEL",
            "message": "사용자가 결제를 취소했습니다",
            "order_id": "20250115000001"
        }
        """
        serializer = PaymentFailSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payment = serializer.payment
        fail_code = serializer.validated_data["code"]
        fail_message = serializer.validated_data["message"]

        try:
            # 1. Payment 상태를 aborted로 변경
            payment.status = "aborted"
            payment.fail_reason = f"[{fail_code}] {fail_message}"
            payment.save(update_fields=["status", "fail_reason", "updated_at"])

            # 2. 실패 로그 기록
            PaymentLog.objects.create(
                payment=payment,
                log_type="error",
                message=f"결제 실패: {fail_code}",
                data={
                    "code": fail_code,
                    "message": fail_message,
                    "order_id": serializer.validated_data["order_id"],
                },
            )

            logger.info(
                f"결제 실패 처리 완료 - Payment ID: {payment.id}, "
                f"Code: {fail_code}, Message: {fail_message}"
            )

            return Response(
                {
                    "message": "결제 실패가 처리되었습니다.",
                    "payment_id": payment.id,
                    "order_id": payment.order.id,
                    "order_number": payment.order.order_number,
                    "status": payment.status,
                    "fail_code": fail_code,
                    "fail_message": fail_message,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            # 예외 발생 시 로그 기록
            logger.error(f"결제 실패 처리 중 오류 발생: {str(e)}")

            return Response(
                {
                    "error": "결제 실패 처리 중 오류가 발생했습니다.",
                    "message": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PaymentDetailView(APIView):
    """
    결제 상세 조회 뷰

    GET /api/payments/{payment_id}/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, payment_id):
        """결제 정보 조회"""
        try:
            payment = Payment.objects.get(id=payment_id, order__user=request.user)
        except Payment.DoesNotExist:
            return Response(
                {"error": "결제 정보를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PaymentSerializer(payment)
        return Response(serializer.data)


class PaymentListView(APIView):
    """
    결제 목록 조회 뷰

    GET /api/payments/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        내 결제 목록 조회

        Query Parameters:
        - page: 페이지 번호 (기본값: 1)
        - page_size: 페이지 크기 (기본값: 10, 최대: 100)
        - status: 결제 상태 필터링 (ready, done, canceled, aborted 등)
        """
        payments = Payment.objects.filter(order__user=request.user).select_related("order").order_by("-created_at")

        # 상태별 필터링
        payment_status = request.GET.get("status")
        if payment_status:
            # 유효한 상태값인지 검증
            valid_statuses = [choice[0] for choice in Payment.STATUS_CHOICES]
            if payment_status not in valid_statuses:
                return Response(
                    {"error": f"유효하지 않은 상태값입니다. 사용 가능한 값: {', '.join(valid_statuses)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            payments = payments.filter(status=payment_status)

        # 페이지네이션 파라미터 검증
        try:
            page = int(request.GET.get("page", 1))
            page_size = int(request.GET.get("page_size", 10))
        except (ValueError, TypeError):
            return Response(
                {"error": "page와 page_size는 정수여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 페이지네이션 값 검증
        if page < 1:
            return Response(
                {"error": "page는 1 이상이어야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page_size < 1:
            return Response(
                {"error": "page_size는 1 이상이어야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # page_size 최대값 제한 (DoS 방지)
        MAX_PAGE_SIZE = 100
        if page_size > MAX_PAGE_SIZE:
            return Response(
                {"error": f"page_size는 최대 {MAX_PAGE_SIZE}까지 가능합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start = (page - 1) * page_size
        end = start + page_size

        payments_page = payments[start:end]

        serializer = PaymentSerializer(payments_page, many=True)

        return Response(
            {
                "count": payments.count(),
                "page": page,
                "page_size": page_size,
                "results": serializer.data,
            }
        )


@login_required
def payment_test_page(request, order_id):
    """결제 테스트 페이지 - 포인트 정보 표시"""
    # 관리자는 모든 주문 접근 가능
    if request.user.is_staff or request.user.is_superuser:
        order = get_object_or_404(Order, id=order_id)
    else:
        order = get_object_or_404(Order, id=order_id, user=request.user)

    # order_number가 없으면 생성
    if not order.order_number:
        from django.utils import timezone

        date_str = timezone.now().strftime("%Y%m%d")
        order.order_number = f"{date_str}{order.id:06d}"
        order.save(update_fields=["order_number"])
        print(f"Order number 생성됨: {order.order_number}")

    # 이미 결제된 주문인지 확인
    if hasattr(order, "payment") and order.payment.is_paid:
        return redirect("shopping:order_detail", order_id=order.id)

    context = {
        "order": order,
        "client_key": settings.TOSS_CLIENT_KEY,
        "user": request.user,  # 템플릿에서 user 접근 가능하도록
        "user_points": request.user.points,  # 사용자 보유 포인트 추가
        "used_points": order.used_points,  # 사용한 포인트
        "final_amount": order.final_amount,  # 최종 결제 금액
    }
    return render(request, "shopping/payment_test.html", context)


@login_required
def payment_success(request):
    """결제 성공 처리"""
    # URL 파라미터에서 값 가져오기
    payment_key = request.GET.get("paymentKey")
    order_id = request.GET.get("orderId")
    amount = request.GET.get("amount")

    if not all([payment_key, order_id, amount]):
        return render(
            request,
            "shopping/payment_fail.html",
            {"message": "필수 파라미터가 누락되었습니다."},
        )

    try:
        # Payment 찾기
        payment = Payment.objects.get(toss_order_id=order_id)

        # 토스페이먼츠 API 클라이언트 사용
        from ..utils.toss_payment import TossPaymentClient

        toss_client = TossPaymentClient()
        result = toss_client.confirm_payment(payment_key=payment_key, order_id=order_id, amount=int(amount))

        # 결제 성공 처리
        payment.mark_as_paid(result)

        # 주문 상태 업데이트
        order = payment.order
        order.status = "paid"
        order.save()

        return render(
            request,
            "shopping/payment_success.html",
            {"payment": payment, "order": order},
        )
    except Payment.DoesNotExist:
        return render(
            request,
            "shopping/payment_fail.html",
            {"message": "결제 정보를 찾을 수 없습니다."},
        )
    except Exception as e:
        return render(request, "shopping/payment_fail.html", {"message": str(e)})


@login_required
def payment_fail(request):
    """결제 실패 처리"""
    code = request.GET.get("code")
    message = request.GET.get("message")
    order_id = request.GET.get("orderId")

    # Payment 상태 업데이트
    if order_id:
        try:
            payment = Payment.objects.get(toss_order_id=order_id)
            payment.mark_as_failed(message)
        except Payment.DoesNotExist:
            pass

    return render(
        request,
        "shopping/payment_fail.html",
        {"code": code, "message": message, "order_id": order_id},
    )
