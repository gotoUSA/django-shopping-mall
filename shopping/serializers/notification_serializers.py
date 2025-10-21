from django.utils import timezone

from rest_framework import serializers

from ..models.notification import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """
    알림 기본 Serializer

    알림 목록 조회 및 상세 정보 표시에 사용됩니다.
    """

    # 알림 타입을 한글로 표시
    notification_type_display = serializers.CharField(source="get_notification_type_display", read_only=True)

    # 생성된 시간을 상대적으로 표시 (예: "5분 전", "2시간 전")
    created_at_display = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "notification_type_display",
            "title",
            "message",
            "link",
            "is_read",
            "read_at",
            "created_at",
            "created_at_display",
        ]
        read_only_fields = ["created_at", "read_at"]

    def get_created_at_display(self, obj):
        """
        생성 시간을 상대적으로 표시

        예: "방금 전", "5분 전", "1시간 전", "3일 전"
        """
        now = timezone.now()
        diff = now - obj.created_at

        seconds = diff.total_seconds()

        if seconds < 60:
            return "방금 전"
        elif seconds < 3600:  # 1시간
            minutes = int(seconds / 60)
            return f"{minutes}분 전"
        elif seconds < 86400:  # 1일
            hours = int(seconds / 3600)
            return f"{hours}시간 전"
        elif seconds < 604800:  # 7일
            days = int(seconds / 86400)
            return f"{days}일 전"
        else:
            # 7일 이상이면 날짜로 표시
            return obj.created_at.strftime("%Y-%m-%d")


class NotificationMarkReadSerializer(serializers.Serializer):
    """
    알림 읽음 처리 Serializer

    여러 알림을 한번에 읽음 처리할 수 있습니다.
    """

    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="읽음 처리할 알림 ID 목록 (빈 리스트면 전체 읽음)",
    )

    def validate_notification_ids(self, value):
        """알림 ID가 실제로 존재하고, 현재 사용자의 것인지 확인"""
        user = self.context["request"].user
        if not value:
            return value

        requested_ids = set(value)  # 중복 제거
        qs = Notification.objects.filter(id__in=requested_ids, user=user)
        found_count = qs.count()
        if found_count != len(requested_ids):
            found_ids = set(qs.values_list("id", flat=True))
            missing = sorted(requested_ids - found_ids)
            raise serializers.ValidationError(f"다음 알림을 찾을 수 없거나 권한이 없습니다: {missing}")
        return value

    def mark_as_read(self):
        """알림을 읽음 처리"""
        user = self.context["request"].user
        notification_ids = self.validated_data.get("notification_ids", [])

        if notification_ids:
            # 특정 알림들만 읽음 처리
            notifications = Notification.objects.filter(id__in=notification_ids, user=user, is_read=False)
        else:
            # 전체 읽음 처리
            notifications = Notification.objects.filter(user=user, is_read=False)

        # 읽음 처리
        count = notifications.update(is_read=True, read_at=timezone.now())

        return count
