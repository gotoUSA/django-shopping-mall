from __future__ import annotations

from typing import Any

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from ..models.notification import Notification
from ..serializers.notification_serializers import NotificationMarkReadSerializer, NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    알림 ViewSet

    알림 조회 및 읽음 처리 기능을 제공합니다.

    엔드포인트:
    - GET    /api/notifications/              - 내 알림 목록
    - GET    /api/notifications/{id}/         - 알림 상세
    - GET    /api/notifications/unread/       - 읽지 않은 알림 개수
    - POST   /api/notifications/mark_read/    - 알림 읽음 처리
    - DELETE /api/notifications/clear/        - 읽은 알림 삭제
    """

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> Any:
        """현재 사용자의 알림만 조회"""
        return Notification.objects.filter(user=self.request.user)

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

    @action(detail=False, methods=["get"])
    def unread(self, request: Request) -> Response:
        """
        읽지 않은 알림 개수 조회
        GET /api/notifications/unread/

        프론트엔드에서 🔔 아이콘에 빨간 점 표시하기 위해 사용

        응답:
        {
            "count": 5,
            "notifications": [최근 5개 알림]
        }
        """
        unread_notifications = self.get_queryset().filter(is_read=False)
        count = unread_notifications.count()

        # 최근 5개만 미리보기
        recent = unread_notifications[:5]
        serializer = self.get_serializer(recent, many=True)

        return Response({"count": count, "notifications": serializer.data})

    @action(detail=False, methods=["post"])
    def mark_read(self, request: Request) -> Response:
        """
        알림 읽음 처리
        POST /api/notifications/mark_read/

        요청 본문:
        {
            "notification_ids": [1, 2, 3]  // 빈 배열이면 전체 읽음
        }

        응답:
        {
            "message": "3개의 알림을 읽음 처리했습니다.",
            "count": 3
        }
        """
        serializer = NotificationMarkReadSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            count = serializer.mark_as_read()

            if count == 0:
                message = "읽지 않은 알림이 없습니다."
            else:
                message = f"{count}개의 알림을 읽음 처리했습니다."

            return Response({"message": message, "count": count})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["delete"])
    def clear(self, request: Request) -> Response:
        """
        읽은 알림 전체 삭제
        DELETE /api/notifications/clear/

        응답:
        {
            "message": "10개의 알림을 삭제했습니다.",
            "count": 10
        }
        """
        read_notifiactions = self.get_queryset().filter(is_read=True)
        count = read_notifiactions.count()
        read_notifiactions.delete()

        return Response({"message": f"{count}개의 알림을 삭제했습니다.", "count": count})
