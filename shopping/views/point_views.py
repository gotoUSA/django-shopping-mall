from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models.point import PointHistory
from ..serializers.point_serializers import PointCheckSerializer, PointHistorySerializer, UserPointSerializer


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

        # 최근 포인트 이력 5개 - N+1 쿼리 방지를 위해 select_related 사용
        recent_histories = PointHistory.objects.filter(user=user).select_related("order").order_by("-created_at")[:5]

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

        # 쿼리 파라미터
        type_filter = request.GET.get("type")  # earn, use, cancel_refund 등
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 20))

        # 기본 쿼리셋 - N+1 쿼리 방지를 위해 select_related 사용
        queryset = PointHistory.objects.filter(user=user).select_related("order")

        # 타입 필터
        if type_filter:
            if type_filter == "earned":
                queryset = queryset.filter(points__gt=0)
            elif type_filter == "used":
                queryset = queryset.filter(points__lt=0)
            else:
                queryset = queryset.filter(type=type_filter)

        # 날짜 필터
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        # 정렬
        queryset = queryset.order_by("-created_at")

        # 페이지네이션
        total_count = queryset.count()
        start = (page - 1) * page_size
        end = start + page_size
        histories = queryset[start:end]

        serializer = PointHistorySerializer(histories, many=True)

        # 요약 정보 - DB aggregate 사용
        summary = {
            "current_points": user.points,
            "total_earned": queryset.filter(points__gt=0).aggregate(total=Sum("points"))["total"] or 0,
            "total_used": abs(queryset.filter(points__lt=0).aggregate(total=Sum("points"))["total"] or 0),
        }

        return Response(
            {
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "summary": summary,
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

        expire_date = timezone.now() + timedelta(days=days)

        # 만료 예정 포인트 이력 - N+1 쿼리 방지를 위해 select_related 사용
        expiring_histories = (
            PointHistory.objects.filter(
                user=user,
                type="earn",
                points__gt=0,
                expires_at__lte=expire_date,
                expires_at__gt=timezone.now(),
            )
            .select_related("order")
            .order_by("expires_at")
        )

        # 월별 만료 예정
        monthly_expiring = {}
        for history in expiring_histories:
            month_key = history.expires_at.strftime("%Y-%m")
            if month_key not in monthly_expiring:
                monthly_expiring[month_key] = {
                    "month": month_key,
                    "points": 0,
                    "count": 0,
                }
            monthly_expiring[month_key]["points"] += history.points
            monthly_expiring[month_key]["count"] += 1

        serializer = PointHistorySerializer(expiring_histories, many=True)

        # DB aggregate를 사용하여 총 만료 예정 포인트 계산
        total_expiring = PointHistory.objects.get_expiring_soon(user, days=days)

        return Response(
            {
                "total_expiring": total_expiring,
                "days": days,
                "monthly_summary": list(monthly_expiring.values()),
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

    # 이번달 적립/사용 - manager 메서드 사용
    this_month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month_stats = PointHistory.objects.get_month_statistics(user, this_month_start)

    # 전체 통계 - manager 메서드 사용
    total_earned = PointHistory.objects.get_total_earned(user)
    total_used = PointHistory.objects.get_total_used(user)

    # 타입별 통계 - DB aggregate 사용
    type_stats = PointHistory.objects.filter(user=user).values("type").annotate(count=Count("id"), total=Sum("points"))

    return Response(
        {
            "current_points": user.points,
            "this_month": this_month_stats,
            "all_time": {"earned": total_earned, "used": total_used},
            "by_type": list(type_stats),
        }
    )
