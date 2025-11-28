from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ..serializers.point_serializers import PointCheckSerializer, PointHistorySerializer, UserPointSerializer
from ..services.point_query_service import DateParseError, PointQueryService


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
        monthly_summary, expiring_histories, total_expiring = (
            PointQueryService.get_monthly_expiring_summary(user, days=days)
        )

        serializer = PointHistorySerializer(expiring_histories, many=True)

        return Response(
            {
                "total_expiring": total_expiring,
                "days": days,
                "monthly_summary": [
                    {"month": item.month, "points": item.points, "count": item.count}
                    for item in monthly_summary
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
