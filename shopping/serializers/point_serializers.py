from __future__ import annotations

from typing import Any

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

    def validate_points(self, value: int) -> int:
        """포인트 변동량 검증"""
        if value == 0:
            raise serializers.ValidationError("포인트 변동량은 0이 될 수 없습니다.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """포인트 이력 데이터 검증 - Model의 clean() 로직 반영"""
        points = attrs.get("points")
        point_type = attrs.get("type")
        balance = attrs.get("balance")

        # type별 points 부호 검증
        positive_types = {"earn", "cancel_refund", "admin_add", "event"}
        negative_types = {"use", "cancel_deduct", "admin_deduct", "expire"}

        if point_type in positive_types and points is not None and points <= 0:
            type_display = dict(PointHistory.TYPE_CHOICES).get(point_type, point_type)
            raise serializers.ValidationError({"points": f"{type_display}는 양수 포인트여야 합니다."})

        if point_type in negative_types and points is not None and points >= 0:
            type_display = dict(PointHistory.TYPE_CHOICES).get(point_type, point_type)
            raise serializers.ValidationError({"points": f"{type_display}는 음수 포인트여야 합니다."})

        # 잔액 검증 (balance가 제공된 경우)
        if balance is not None and balance < 0:
            raise serializers.ValidationError({"balance": "잔액은 음수가 될 수 없습니다."})

        return attrs


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

    def get_total_earned(self, obj: User) -> int:
        """총 적립 포인트 - DB aggregate 사용"""
        from ..models.point import PointHistory

        return PointHistory.objects.get_total_earned(obj)

    def get_total_used(self, obj: User) -> int:
        """총 사용 포인트 - DB aggregate 사용"""
        from ..models.point import PointHistory

        return PointHistory.objects.get_total_used(obj)

    def get_expiring_soon(self, obj: User) -> int:
        """30일 내 만료 예정 포인트 - DB aggregate 사용"""
        from ..models.point import PointHistory

        return PointHistory.objects.get_expiring_soon(obj, days=30)


class PointUseSerializer(serializers.Serializer):
    """
    포인트 사용 요청 시리얼라이저

    검증 정책:
    - amount: 양수 정수, 최소 100포인트
    - 보유 포인트 초과 불가
    - order_id: 선택적 (주문 연동 시)
    - description: 선택적 (사용 사유)
    """

    amount = serializers.IntegerField(
        min_value=1,
        error_messages={
            "required": "사용할 포인트를 입력해주세요.",
            "invalid": "포인트는 숫자로 입력해주세요.",
            "min_value": "포인트는 1 이상이어야 합니다.",
        },
        help_text="사용할 포인트",
    )
    order_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="관련 주문 ID",
    )
    description = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
        help_text="사용 사유",
    )

    # 최소 사용 금액 상수 (PointService와 동일)
    MINIMUM_USE_AMOUNT = 100

    def validate_amount(self, value: int) -> int:
        """포인트 금액 검증"""
        # 최소 사용 금액 검증
        if value < self.MINIMUM_USE_AMOUNT:
            raise serializers.ValidationError(f"포인트는 최소 {self.MINIMUM_USE_AMOUNT}포인트 이상 사용 가능합니다.")

        # 보유 포인트 검증
        user = self.context["request"].user
        if value > user.points:
            raise serializers.ValidationError(f"보유 포인트가 부족합니다. (보유: {user.points:,}P, 요청: {value:,}P)")

        return value

    def validate_order_id(self, value: int | None) -> int | None:
        """주문 ID 검증"""
        if value is None:
            return None

        from ..models.order import Order

        user = self.context["request"].user

        # 주문 존재 여부 및 소유권 검증
        if not Order.objects.filter(id=value, user=user).exists():
            raise serializers.ValidationError("유효하지 않은 주문입니다.")

        return value


class PointCancelSerializer(serializers.Serializer):
    """
    취소/환불 포인트 회수 시리얼라이저

    검증 정책:
    - amount: 양수 정수
    - order_id: 필수 (취소된 주문 연동)
    - type: cancel_deduct(회수) 또는 cancel_refund(환불)
    """

    amount = serializers.IntegerField(
        min_value=1,
        error_messages={
            "required": "포인트 금액을 입력해주세요.",
            "invalid": "포인트는 숫자로 입력해주세요.",
            "min_value": "포인트는 1 이상이어야 합니다.",
        },
        help_text="처리할 포인트",
    )
    order_id = serializers.IntegerField(
        required=True,
        error_messages={
            "required": "주문 ID는 필수입니다.",
            "invalid": "주문 ID는 숫자로 입력해주세요.",
        },
        help_text="취소된 주문 ID",
    )
    type = serializers.ChoiceField(
        choices=[("cancel_deduct", "취소차감"), ("cancel_refund", "취소환불")],
        error_messages={
            "required": "포인트 처리 유형을 선택해주세요.",
            "invalid_choice": "유효하지 않은 처리 유형입니다. (cancel_deduct 또는 cancel_refund)",
        },
        help_text="처리 유형: cancel_deduct(적립 포인트 회수), cancel_refund(사용 포인트 환불)",
    )
    description = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
        help_text="처리 사유",
    )

    def validate_order_id(self, value: int) -> int:
        """주문 ID 검증"""
        from ..models.order import Order

        user = self.context["request"].user

        # 주문 존재 여부 및 소유권 검증
        try:
            order = Order.objects.get(id=value, user=user)
        except Order.DoesNotExist:
            raise serializers.ValidationError("유효하지 않은 주문입니다.")

        # 취소된 주문인지 검증
        if order.status != "canceled":
            raise serializers.ValidationError("취소된 주문에 대해서만 포인트 처리가 가능합니다.")

        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """전체 검증"""
        cancel_type = attrs.get("type")
        amount = attrs.get("amount")
        user = self.context["request"].user

        # cancel_deduct(회수)인 경우: 유효한 포인트가 충분한지 검증
        # (만료되지 않은 포인트만 회수 가능)
        if cancel_type == "cancel_deduct":
            # 기본 잔액 검증
            if amount > user.points:
                raise serializers.ValidationError({"amount": f"회수할 포인트가 부족합니다. (보유: {user.points:,}P)"})

        return attrs


class PointCheckSerializer(serializers.Serializer):
    """포인트 사용 가능 여부 확인 시리얼라이저"""

    order_amount = serializers.DecimalField(max_digits=10, decimal_places=0, help_text="주문 금액")
    use_points = serializers.IntegerField(min_value=0, help_text="사용하려는 포인트")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
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
