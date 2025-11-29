from __future__ import annotations

import logging

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models.order import Order
from ..serializers.point_serializers import (
    PointCancelSerializer,
    PointCheckSerializer,
    PointHistorySerializer,
    PointUseSerializer,
    UserPointSerializer,
)
from ..services.point_query_service import DateParseError, PointQueryService
from ..services.point_service import PointService

logger = logging.getLogger(__name__)


class MyPointView(APIView):
    """
    내 포인트 정보 조회

    GET /api/points/my/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        """내 포인트 현황 조회"""
        user = request.user
        serializer = UserPointSerializer(user)

        # 최근 포인트 이력 5개 - Service 레이어 활용
        recent_histories = PointQueryService.get_recent_histories(user, limit=5)
        recent_serializer = PointHistorySerializer(recent_histories, many=True)

        return Response({"point_info": serializer.data, "recent_histories": recent_serializer.data})


class PointHistoryListView(APIView):
    """
    포인트 이력 목록 조회

    GET /api/points/history/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        """포인트 이력 목록 조회"""
        user = request.user

        # Request에서 필터 조건 추출 (날짜 검증 포함)
        try:
            filter_params = PointQueryService.build_filter_from_request(request)
        except DateParseError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 필터링된 이력 조회
        paginated_result = PointQueryService.get_filtered_history(user, filter_params)

        # 요약 정보 계산 (필터링된 쿼리셋 기반)
        # 참고: 전체 이력 기준 요약이 필요하면 queryset=None 전달
        summary = PointQueryService.get_history_summary(user)

        serializer = PointHistorySerializer(paginated_result.items, many=True)

        return Response(
            {
                "count": paginated_result.total_count,
                "page": paginated_result.page,
                "page_size": paginated_result.page_size,
                "summary": {
                    "current_points": summary.current_points,
                    "total_earned": summary.total_earned,
                    "total_used": summary.total_used,
                },
                "results": serializer.data,
            }
        )


class PointCheckView(APIView):
    """
    포인트 사용 가능 여부 확인

    POST /api/points/check
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        """
        포인트 사용 가능 여부 확인

        요청:
        {
            "order_amount": 10000,
            "use_points": 500
        }

        응답:
        {
            "available_points": 1500,
            "can_use": true,
            "max_usable": 1500,
            "message": "500포인트 사용 가능합니다."
        }
        """
        serializer = PointCheckSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            return Response(serializer.validated_data["result"])

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ExpiringPointsView(APIView):
    """
    만료 예정 포인트 조회

    GET /api/points/expiring/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        """만료 예정 포인트 조회"""
        user = request.user
        days = int(request.GET.get("days", 30))  # 기본 30일

        # Service 레이어에서 월별 만료 예정 요약 조회
        monthly_summary, expiring_histories, total_expiring = PointQueryService.get_monthly_expiring_summary(user, days=days)

        serializer = PointHistorySerializer(expiring_histories, many=True)

        return Response(
            {
                "total_expiring": total_expiring,
                "days": days,
                "monthly_summary": [
                    {"month": item.month, "points": item.points, "count": item.count} for item in monthly_summary
                ],
                "histories": serializer.data,
            }
        )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def point_statistics(request: Request) -> Response:
    """
    포인트 통계 정보

    GET /api/points/statistics/
    """
    user = request.user

    # Service 레이어에서 종합 통계 조회
    stats = PointQueryService.get_point_statistics(user)

    return Response(
        {
            "current_points": stats.current_points,
            "this_month": stats.this_month,
            "all_time": stats.all_time,
            "by_type": stats.by_type,
        }
    )


class PointUseView(APIView):
    """
    포인트 사용 API

    POST /api/points/use/

    FIFO 방식으로 만료 임박 포인트부터 차감합니다.
    최소 100포인트 이상 사용 가능합니다.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        """
        포인트 사용

        요청:
        {
            "amount": 1000,
            "order_id": 123,       // 선택
            "description": "주문 결제"  // 선택
        }

        성공 응답 (200):
        {
            "success": true,
            "message": "1,000 포인트를 사용했습니다.",
            "data": {
                "used_amount": 1000,
                "remaining_points": 4000,
                "used_details": [
                    {"history_id": 1, "amount": 700, "expires_at": "..."},
                    {"history_id": 2, "amount": 300, "expires_at": "..."}
                ]
            }
        }

        실패 응답 (400):
        {
            "success": false,
            "error_code": "INSUFFICIENT_POINTS",
            "message": "포인트가 부족합니다."
        }
        """
        serializer = PointUseSerializer(data=request.data, context={"request": request})

        if not serializer.is_valid():
            # Serializer 검증 실패 - 에러 코드 매핑
            return self._build_validation_error_response(serializer.errors)

        # 검증 통과 - 포인트 사용 실행
        user = request.user
        amount = serializer.validated_data["amount"]
        order_id = serializer.validated_data.get("order_id")
        description = serializer.validated_data.get("description", "")

        # Order 객체 조회 (있는 경우)
        order = None
        if order_id:
            order = Order.objects.filter(id=order_id, user=user).first()

        # PointService.use_points_fifo 호출
        point_service = PointService()
        result = point_service.use_points_fifo(
            user=user,
            amount=amount,
            type="use",
            order=order,
            description=description or "포인트 사용",
        )

        if result["success"]:
            # 사용자 포인트 새로고침
            user.refresh_from_db()

            logger.info(f"포인트 사용 성공: user_id={user.id}, amount={amount}, " f"remaining={user.points}")

            return Response(
                {
                    "success": True,
                    "message": f"{amount:,} 포인트를 사용했습니다.",
                    "data": {
                        "used_amount": amount,
                        "remaining_points": user.points,
                        "used_details": result["used_details"],
                    },
                }
            )
        else:
            # Service 레이어 실패 - 에러 코드 매핑
            error_code = self._map_service_error_code(result["message"])

            logger.warning(f"포인트 사용 실패: user_id={user.id}, amount={amount}, " f"error={result['message']}")

            return Response(
                {
                    "success": False,
                    "error_code": error_code,
                    "message": result["message"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    def _build_validation_error_response(self, errors: dict) -> Response:
        """Serializer 검증 에러를 통일된 응답 형식으로 변환"""
        # 첫 번째 에러 메시지 추출
        first_field = next(iter(errors))
        first_error = errors[first_field]
        if isinstance(first_error, list):
            message = str(first_error[0])
        else:
            message = str(first_error)

        # 에러 코드 매핑
        error_code = "INVALID_REQUEST"
        if "최소" in message or "100" in message:
            error_code = "MINIMUM_AMOUNT_NOT_MET"
        elif "부족" in message:
            error_code = "INSUFFICIENT_POINTS"
        elif "숫자" in message or "invalid" in message.lower():
            error_code = "INVALID_AMOUNT"

        return Response(
            {
                "success": False,
                "error_code": error_code,
                "message": message,
                "errors": errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _map_service_error_code(self, message: str) -> str:
        """Service 에러 메시지를 에러 코드로 매핑"""
        if "부족" in message:
            if "유효한" in message:
                return "INSUFFICIENT_VALID_POINTS"
            return "INSUFFICIENT_POINTS"
        elif "최소" in message:
            return "MINIMUM_AMOUNT_NOT_MET"
        elif "0보다" in message:
            return "INVALID_AMOUNT"
        return "POINT_USE_FAILED"


class PointCancelView(APIView):
    """
    취소/환불 포인트 처리 API

    POST /api/points/cancel/

    주문 취소 시 포인트 처리:
    - cancel_deduct: 주문으로 적립받은 포인트 회수
    - cancel_refund: 주문에 사용한 포인트 환불
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        """
        취소/환불 포인트 처리

        요청:
        {
            "amount": 500,
            "order_id": 123,
            "type": "cancel_deduct",  // 또는 "cancel_refund"
            "description": "주문 취소로 인한 포인트 회수"  // 선택
        }

        성공 응답 (200):
        {
            "success": true,
            "message": "500 포인트가 회수되었습니다.",
            "data": {
                "processed_amount": 500,
                "remaining_points": 4500,
                "type": "cancel_deduct",
                "order_id": 123
            }
        }
        """
        serializer = PointCancelSerializer(data=request.data, context={"request": request})

        if not serializer.is_valid():
            return self._build_validation_error_response(serializer.errors)

        user = request.user
        amount = serializer.validated_data["amount"]
        order_id = serializer.validated_data["order_id"]
        cancel_type = serializer.validated_data["type"]
        description = serializer.validated_data.get("description", "")

        # Order 객체 조회
        order = Order.objects.get(id=order_id, user=user)

        # 타입에 따른 처리
        if cancel_type == "cancel_deduct":
            # 적립 포인트 회수 (FIFO 방식)
            result = self._process_cancel_deduct(user, amount, order, description)
        else:
            # 사용 포인트 환불
            result = self._process_cancel_refund(user, amount, order, description)

        if result["success"]:
            user.refresh_from_db()

            logger.info(
                f"포인트 취소 처리 성공: user_id={user.id}, type={cancel_type}, " f"amount={amount}, order_id={order_id}"
            )

            type_message = "회수" if cancel_type == "cancel_deduct" else "환불"
            return Response(
                {
                    "success": True,
                    "message": f"{amount:,} 포인트가 {type_message}되었습니다.",
                    "data": {
                        "processed_amount": amount,
                        "remaining_points": user.points,
                        "type": cancel_type,
                        "order_id": order_id,
                    },
                }
            )
        else:
            error_code = self._map_service_error_code(result["message"], cancel_type)

            logger.warning(
                f"포인트 취소 처리 실패: user_id={user.id}, type={cancel_type}, " f"amount={amount}, error={result['message']}"
            )

            return Response(
                {
                    "success": False,
                    "error_code": error_code,
                    "message": result["message"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    def _process_cancel_deduct(self, user, amount: int, order: Order, description: str) -> dict:
        """적립 포인트 회수 처리 (FIFO)"""
        point_service = PointService()
        return point_service.use_points_fifo(
            user=user,
            amount=amount,
            type="cancel_deduct",
            order=order,
            description=description or f"주문 #{order.order_number} 취소로 인한 포인트 회수",
        )

    def _process_cancel_refund(self, user, amount: int, order: Order, description: str) -> dict:
        """사용 포인트 환불 처리"""
        success = PointService.add_points(
            user=user,
            amount=amount,
            type="cancel_refund",
            order=order,
            description=description or f"주문 #{order.order_number} 취소로 인한 포인트 환불",
        )

        if success:
            return {"success": True, "message": "포인트 환불 완료"}
        else:
            return {"success": False, "message": "포인트 환불에 실패했습니다."}

    def _build_validation_error_response(self, errors: dict) -> Response:
        """Serializer 검증 에러를 통일된 응답 형식으로 변환"""
        first_field = next(iter(errors))
        first_error = errors[first_field]
        if isinstance(first_error, list):
            message = str(first_error[0])
        else:
            message = str(first_error)

        error_code = "INVALID_REQUEST"
        # 순서 중요: "취소된 주문에 대해서만"에 "주문"이 포함되므로 "취소"를 먼저 체크
        if "취소된 주문" in message:
            error_code = "ORDER_NOT_CANCELED"
        elif "유효하지 않은 주문" in message:
            error_code = "INVALID_ORDER"
        elif "유형" in message or "type" in message.lower():
            error_code = "INVALID_TYPE"
        elif "부족" in message:
            error_code = "INSUFFICIENT_POINTS"

        return Response(
            {
                "success": False,
                "error_code": error_code,
                "message": message,
                "errors": errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _map_service_error_code(self, message: str, cancel_type: str) -> str:
        """Service 에러 메시지를 에러 코드로 매핑"""
        if "부족" in message:
            if "유효한" in message:
                return "INSUFFICIENT_VALID_POINTS"
            return "INSUFFICIENT_POINTS"
        elif cancel_type == "cancel_deduct":
            return "CANCEL_DEDUCT_FAILED"
        else:
            return "CANCEL_REFUND_FAILED"
