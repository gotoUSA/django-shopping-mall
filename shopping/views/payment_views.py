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
from ..services.payment_service import PaymentConfirmError, PaymentService
from ..throttles import PaymentCancelRateThrottle, PaymentConfirmRateThrottle, PaymentRequestRateThrottle
from ..utils.toss_payment import TossPaymentClient, TossPaymentError, get_error_message
from .mixins import EmailVerificationRequiredMixin

# 로거 설정
logger = logging.getLogger(__name__)


class PaymentRequestView(EmailVerificationRequiredMixin, APIView):
    """
    결제 요청 뷰

    프론트엔드에서 토스페이먼츠 결제창을 열기 전에 호출합니다.
    결제에 필요한 정보를 반환합니다.

    POST /api/payments/request/
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [PaymentRequestRateThrottle]

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
        verification_error = self.check_email_verification(request, "결제를")
        if verification_error:
            return verification_error

        serializer = PaymentRequestSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            # Payment 생성
            payment = serializer.save()

            # N+1 방지: order와 order_items를 함께 조회
            payment = Payment.objects.select_related("order").prefetch_related("order__order_items").get(
                pk=payment.id
            )
            order = payment.order

            # 주문명 생성 (첫 상품명 + 나머지 개수)
            order_items = list(order.order_items.all())  # prefetch된 데이터 사용

            if not order_items:
                return Response(
                    {"error": "주문 항목이 아직 생성되지 않았습니다. 잠시 후 다시 시도해주세요."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            first_item = order_items[0]

            if len(order_items) > 1:
                order_name = f"{first_item.product_name} 외 {len(order_items) - 1}건"
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


class PaymentConfirmView(EmailVerificationRequiredMixin, APIView):
    """
    결제 승인 뷰

    사용자가 토스페이먼츠 결제창에서 결제를 완료하면
    프론트엔드에서 이 API를 호출하여 결제를 승인합니다.

    POST /api/payments/confirm/
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [PaymentConfirmRateThrottle]

    def post(self, request):
        """
        결제 승인 처리 (비동기 처리)

        요청 본문:
        {
            "order_id": "20250111000001",
            "payment_key": "test_payment_key_...",
            "amount": 1500000
        }

        응답:
        HTTP 202 Accepted
        {
            "status": "processing",
            "payment_id": 1,
            "task_id": "abc-123-...",
            "message": "결제 처리 중입니다. 잠시만 기다려주세요.",
            "status_url": "/api/payments/1/status/"
        }
        """
        # 이메일 인증 체크 (보안)
        verification_error = self.check_email_verification(request, "결제를")
        if verification_error:
            return verification_error

        # Serializer를 통한 검증
        serializer = PaymentConfirmSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payment = serializer.payment

        try:
            # PaymentService를 통한 비동기 결제 승인 처리
            result = PaymentService.confirm_payment_async(
                payment=payment,
                payment_key=serializer.validated_data["payment_key"],
                order_id=serializer.validated_data["order_id"],
                amount=serializer.validated_data["amount"],
                user=request.user,
            )

            # 즉시 응답 (202 Accepted)
            return Response(
                {
                    "status": "processing",
                    "payment_id": result["payment_id"],
                    "task_id": result["task_id"],
                    "message": "결제 처리 중입니다. 완료 시 알림을 드립니다.",
                    # 프론트엔드가 결과를 확인할 수 있는 엔드포인트
                    "status_url": f"/api/payments/{result['payment_id']}/status/",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except PaymentConfirmError as e:
            # 결제 승인 에러 (중복 결제, 잘못된 상태 등)
            logger.warning(f"Payment confirm error: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except TossPaymentError as e:
            # Toss API 에러 (Celery eager mode에서 태스크 즉시 실행 시 발생)
            # 프로덕션에서는 태스크가 백그라운드에서 실행되므로 여기 도달하지 않음
            logger.error(f"Toss API error in task: {str(e)}")

            # 결제 실패 처리
            payment.refresh_from_db()
            if payment.status != "aborted":
                payment.mark_as_failed(str(e))

            # 비동기 처리 중 에러 발생으로 202 반환 (이미 태스크 dispatch 됨)
            return Response(
                {
                    "status": "processing",
                    "payment_id": payment.id,
                    "task_id": "error",
                    "message": "결제 처리 중입니다.",
                    "status_url": f"/api/payments/{payment.id}/status/",
                },
                status=status.HTTP_202_ACCEPTED,
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
    throttle_classes = [PaymentCancelRateThrottle]

    def post(self, request):
        """
        결제 취소 처리

        요청 본문:
        {
            "payment_id": 1,
            "cancel_reason": "고객 변심"
        }
        """
        # 입력 검증만 수행 (비즈니스 로직 검증은 서비스에서)
        serializer = PaymentCancelSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payment_id = serializer.validated_data["payment_id"]
        cancel_reason = serializer.validated_data["cancel_reason"]

        try:
            # 서비스 레이어 호출 (동시성 제어 및 비즈니스 로직 처리)
            from ..services.payment_service import PaymentService

            result = PaymentService.cancel_payment(
                payment_id=payment_id, user=request.user, cancel_reason=cancel_reason
            )

            # N+1 방지: 응답용 Payment 객체를 order와 함께 조회
            payment = Payment.objects.select_related("order").get(pk=payment_id)

            return Response(
                {
                    "message": "결제가 취소되었습니다.",
                    "payment": PaymentSerializer(payment).data,
                    "refund_amount": int(result["canceled_amount"]),
                    "refunded_points": result["points_refunded"],
                    "deducted_points": result["points_deducted"],
                },
                status=status.HTTP_200_OK,
            )

        except Payment.DoesNotExist:
            return Response(
                {"error": "결제 정보를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as e:
            # PaymentCancelError 및 기타 에러
            from ..services.payment_service import PaymentCancelError

            if isinstance(e, PaymentCancelError):
                logger.error(f"Payment cancel error: {str(e)}")
                return Response(
                    {"error": str(e)}, status=status.HTTP_400_BAD_REQUEST
                )

            # 기타 예외
            logger.error(f"Unexpected error in payment cancel: {str(e)}")
            return Response(
                {"error": "결제 취소 중 오류가 발생했습니다.", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PaymentStatusView(APIView):
    """
    결제 처리 상태 확인 API

    비동기 결제 처리 시 프론트엔드가 이 API를 polling하여
    결제 처리 완료 여부를 확인할 수 있습니다.

    GET /api/payments/{payment_id}/status/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, payment_id):
        """
        결제 상태 조회

        응답:
        {
            "payment_id": 1,
            "status": "done",
            "is_paid": true,
            "order_status": "paid",
            "order_id": 123
        }
        """
        try:
            payment = Payment.objects.select_related("order").get(
                id=payment_id,
                order__user=request.user
            )

            return Response({
                "payment_id": payment.id,
                "status": payment.status,
                "is_paid": payment.is_paid,
                "order_status": payment.order.status if payment.order else None,
                "order_id": payment.order.id if payment.order else None,
            })

        except Payment.DoesNotExist:
            return Response(
                {"error": "결제 정보를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )


class PaymentFailView(APIView):
    """
    결제 실패 처리 뷰

    토스페이먼츠 결제창에서 실패/취소 시 호출됩니다.
    Payment 상태를 aborted로 변경하고 실패 로그를 기록합니다.

    POST /api/payments/fail/

    보안: 사용자 인증 필수 - 본인의 결제만 실패 처리 가능
    """

    permission_classes = [permissions.IsAuthenticated]

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
        serializer = PaymentFailSerializer(data=request.data, context={"request": request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payment = serializer.payment
        fail_code = serializer.validated_data["code"]
        fail_message = serializer.validated_data["message"]

        # 보안: 본인의 결제만 실패 처리 가능
        if payment.order.user != request.user:
            logger.warning(
                f"타인의 결제 실패 처리 시도: user_id={request.user.id}, "
                f"payment_id={payment.id}, payment_user_id={payment.order.user.id}"
            )
            return Response(
                {"error": "결제 정보를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            # 1. Payment 상태를 aborted로 변경
            payment.mark_as_failed(f"[{fail_code}] {fail_message}")

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
            # N+1 방지: order와 함께 조회
            payment = Payment.objects.select_related("order").get(id=payment_id, order__user=request.user)
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
    """
    결제 테스트 페이지 - 포인트 정보 표시

    Note: order_number는 Order 생성 시 post_save signal에서 자동으로 생성됩니다.
          (signals.py의 generate_order_number 참조)
    """
    # 관리자는 모든 주문 접근 가능
    if request.user.is_staff or request.user.is_superuser:
        order = get_object_or_404(Order, id=order_id)
    else:
        order = get_object_or_404(Order, id=order_id, user=request.user)

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
    """
    결제 성공 콜백 처리 (템플릿 렌더링용)

    Note: 비즈니스 로직은 PaymentService를 통해 처리합니다.
          새로운 구현에서는 PaymentConfirmView API를 사용하는 것을 권장합니다.
    """
    # URL 파라미터에서 값 가져오기
    payment_key = request.GET.get("paymentKey")
    order_id = request.GET.get("orderId")
    amount = request.GET.get("amount")

    if not all([payment_key, order_id, amount]):
        logger.warning(
            f"결제 성공 콜백 파라미터 누락: payment_key={payment_key}, "
            f"order_id={order_id}, amount={amount}"
        )
        return render(
            request,
            "shopping/payment_fail.html",
            {"message": "필수 파라미터가 누락되었습니다."},
        )

    try:
        # Payment 찾기
        payment = Payment.objects.get(toss_order_id=order_id)

        # PaymentService를 통한 결제 승인 처리
        result = PaymentService.confirm_payment(
            payment=payment,
            payment_key=payment_key,
            order_id=order_id,
            amount=int(amount),
            user=request.user,
        )

        logger.info(
            f"템플릿 결제 성공 처리 완료: payment_id={payment.id}, "
            f"order_id={result['payment'].order.id}, user_id={request.user.id}"
        )

        return render(
            request,
            "shopping/payment_success.html",
            {
                "payment": result["payment"],
                "order": result["payment"].order,
                "points_earned": result["points_earned"],
            },
        )

    except Payment.DoesNotExist:
        logger.error(f"결제 정보를 찾을 수 없음: order_id={order_id}")
        return render(
            request,
            "shopping/payment_fail.html",
            {"message": "결제 정보를 찾을 수 없습니다."},
        )

    except (PaymentConfirmError, TossPaymentError) as e:
        logger.error(f"결제 승인 실패: order_id={order_id}, error={str(e)}")
        return render(
            request,
            "shopping/payment_fail.html",
            {"message": f"결제 처리 중 오류가 발생했습니다: {str(e)}"},
        )

    except Exception as e:
        logger.error(f"결제 성공 처리 중 예상치 못한 오류: order_id={order_id}, error={str(e)}")
        return render(
            request,
            "shopping/payment_fail.html",
            {"message": "결제 처리 중 오류가 발생했습니다."},
        )


@login_required
def payment_fail(request):
    """
    결제 실패 콜백 처리 (템플릿 렌더링용)

    Note: 간단한 상태 업데이트만 수행합니다.
          새로운 구현에서는 PaymentFailView API를 사용하는 것을 권장합니다.
    """
    code = request.GET.get("code")
    message = request.GET.get("message")
    order_id = request.GET.get("orderId")

    logger.warning(
        f"결제 실패 콜백 수신: code={code}, message={message}, order_id={order_id}"
    )

    # Payment 상태 업데이트
    if order_id:
        try:
            payment = Payment.objects.get(toss_order_id=order_id)
            payment.mark_as_failed(message)
            logger.info(f"결제 실패 상태 업데이트: payment_id={payment.id}, order_id={order_id}")
        except Payment.DoesNotExist:
            logger.error(f"결제 정보를 찾을 수 없음: order_id={order_id}")

    return render(
        request,
        "shopping/payment_fail.html",
        {"code": code, "message": message, "order_id": order_id},
    )
