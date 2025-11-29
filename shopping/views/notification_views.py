from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, serializers as drf_serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from ..models.notification import Notification
from ..serializers.notification_serializers import (
    NotificationListSerializer,
    NotificationMarkReadSerializer,
    NotificationSerializer,
)


# ===== Swagger 문서화용 응답 Serializers =====


class UnreadNotificationResponseSerializer(drf_serializers.Serializer):
    """읽지 않은 알림 응답"""
    count = drf_serializers.IntegerField()
    notifications = NotificationListSerializer(many=True)


class MarkReadResponseSerializer(drf_serializers.Serializer):
    """알림 읽음 처리 응답"""
    message = drf_serializers.CharField()
    count = drf_serializers.IntegerField()


class ClearResponseSerializer(drf_serializers.Serializer):
    """알림 삭제 응답"""
    message = drf_serializers.CharField()
    count = drf_serializers.IntegerField()


@extend_schema_view(
    list=extend_schema(
        summary="내 알림 목록 조회",
        description="현재 사용자의 알림 목록을 조회합니다.",
        tags=["Notifications"],
    ),
    retrieve=extend_schema(
        summary="알림 상세 조회",
        description="""
알림의 상세 정보를 조회합니다.

**자동 처리:** 조회 시 자동으로 읽음 처리됩니다.
        """,
        tags=["Notifications"],
    ),
)
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """알림 ViewSet"""

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> Any:
        """현재 사용자의 알림만 조회"""
        return Notification.objects.filter(user=self.request.user)

    def get_serializer_class(self) -> type[NotificationListSerializer] | type[NotificationSerializer]:
        """
        액션에 따라 적절한 Serializer 선택

        - list, unread: 경량 ListSerializer (message 제외)
        - retrieve: 전체 정보 포함 Serializer
        """
        if self.action in ["list", "unread"]:
            return NotificationListSerializer
        return NotificationSerializer

    def retrieve(self, request: Request, pk: int | None = None) -> Response:
        """
        알림 상세 조회

        조회 시 자동으로 읽음 처리됩니다.
        """
        notification = self.get_object()

        # 읽지 않은 알림이면 읽음 처리
        if not notification.is_read:
            notification.mark_as_read()

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @extend_schema(
        responses={200: UnreadNotificationResponseSerializer},
        summary="읽지 않은 알림 조회",
        description="""
읽지 않은 알림 개수와 최근 5개를 조회합니다.

**활용:** 프론트엔드에서 🔔 아이콘에 빨간 점 표시
        """,
        tags=["Notifications"],
    )
    @action(detail=False, methods=["get"])
    def unread(self, request: Request) -> Response:
        unread_notifications = self.get_queryset().filter(is_read=False)
        count = unread_notifications.count()

        # 최근 5개만 미리보기
        recent = unread_notifications[:5]
        serializer = self.get_serializer(recent, many=True)

        return Response({"count": count, "notifications": serializer.data})

    @extend_schema(
        request=NotificationMarkReadSerializer,
        responses={200: MarkReadResponseSerializer},
        summary="알림 읽음 처리",
        description="""
알림을 읽음 처리합니다.

**요청 본문:**
- notification_ids: 알림 ID 배열 (빈 배열이면 전체 읽음)
        """,
        tags=["Notifications"],
    )
    @action(detail=False, methods=["post"])
    def mark_read(self, request: Request) -> Response:
        serializer = NotificationMarkReadSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            count = serializer.mark_as_read()

            if count == 0:
                message = "읽지 않은 알림이 없습니다."
            else:
                message = f"{count}개의 알림을 읽음 처리했습니다."

            return Response({"message": message, "count": count})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={200: ClearResponseSerializer},
        summary="읽은 알림 전체 삭제",
        description="읽음 처리된 알림을 전체 삭제합니다.",
        tags=["Notifications"],
    )
    @action(detail=False, methods=["delete"])
    def clear(self, request: Request) -> Response:
        read_notifications = self.get_queryset().filter(is_read=True)
        count = read_notifications.count()
        read_notifications.delete()

        return Response({"message": f"{count}개의 알림을 삭제했습니다.", "count": count})
