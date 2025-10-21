from rest_framework import serializers

from ..models.point import PointHistory
from ..models.user import User


class PointHistorySerializer(serializers.ModelSerializer):
    """포인트 이력 조회용 시리얼라이저"""

    type_display = serializers.CharField(source="get_type_display", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True, allow_null=True)

    class Meta:
        model = PointHistory
        fields = [
            "id",
            "points",
            "balance",
            "type",
            "type_display",
            "order",
            "order_number",
            "description",
            "expires_at",
            "metadata",
            "created_at",
        ]
        read_only_fields = ["balance", "created_at"]


class UserPointSerializer(serializers.ModelSerializer):
    """사용자 포인트 정보 조회용 시리얼라이저"""

    total_earned = serializers.SerializerMethodField()
    total_used = serializers.SerializerMethodField()
    expiring_soon = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "points",
            "total_earned",
            "total_used",
            "expiring_soon",
        ]
        read_only_fields = ["points"]

    def get_total_earned(self, obj):
        """총 적립 포인트"""
        histories = obj.point_histories.filter(points__gt=0)
        return sum(h.points for h in histories)

    def get_total_used(self, obj):
        """총 사용 포인트"""
        histories = obj.point_histories.filter(points__lt=0)
        return abs(sum(h.points for h in histories))

    def get_expiring_soon(self, obj):
        """30일 내 만료 예정 포인트"""
        from datetime import timedelta

        from django.utils import timezone

        expire_date = timezone.now() + timedelta(days=30)
        histories = obj.point_histories.filter(
            type="earn",
            points__gt=0,
            expires_at__lte=expire_date,
            expires_at__gt=timezone.now(),
        )
        return sum(h.points for h in histories)


class PointUseSerializer(serializers.Serializer):
    """포인트 사용 요청 시리얼라이저"""

    points = serializers.IntegerField(min_value=100, help_text="사용할 포인트 (최소 100포인트)")
    order_id = serializers.IntegerField(required=False, help_text="관련 주문 ID")
    description = serializers.CharField(max_length=255, required=False, help_text="사용 사유")

    def validate_points(self, value):
        """포인트 검증"""
        user = self.context["request"].user

        if value > user.points:
            raise serializers.ValidationError(f"보유 포인트가 부족합니다. (보유: {user.points}P)")

        return value


class PointCheckSerializer(serializers.Serializer):
    """포인트 사용 가능 여부 확인 시리얼라이저"""

    order_amount = serializers.DecimalField(max_digits=10, decimal_places=0, help_text="주문 금액")
    use_points = serializers.IntegerField(min_value=0, help_text="사용하려는 포인트")

    def validate(self, attrs):
        """포인트 사용 가능 여부 검증"""
        user = self.context["request"].user
        order_amount = attrs["order_amount"]
        use_points = attrs["use_points"]

        result = {
            "available_points": user.points,
            "can_use": False,
            "max_usable": 0,
            "message": "",
        }

        # 최대 사용 가능 포인트 (주문 금액의 100%)
        max_usable = min(user.points, int(order_amount))
        result["max_usable"] = max_usable

        if use_points == 0:
            result["can_use"] = True
            result["message"] = "포인트를 사용하지 않습니다."
        elif use_points < 100:
            result["message"] = "최소 100포인트 이상 사용 가능합니다."
        elif use_points > user.points:
            result["message"] = f"보유 포인트가 부족합니다. (보유: {user.points}P)"
        elif use_points > order_amount:
            result["message"] = "주문 금액을 초과하여 사용할 수 없습니다."
        else:
            result["can_use"] = True
            result["message"] = f"{use_points}포인트 사용 가능합니다."

        attrs["result"] = result
        return attrs
