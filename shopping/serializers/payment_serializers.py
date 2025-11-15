from rest_framework import serializers

from ..models.order import Order
from ..models.payment import Payment, PaymentLog


class PaymentSerializer(serializers.ModelSerializer):
    """
    결제 정보 조회용 시리얼라이저
    """

    order_number = serializers.CharField(
        source="order.order_number",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    used_points = serializers.IntegerField(
        source="order.used_points",
        read_only=True,
    )

    earned_points = serializers.IntegerField(
        source="order.earned_points",
        read_only=True,
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
            "order_number",
            "payment_key",
            "order_id",
            "amount",
            "used_points",
            "earned_points",
            "method",
            "card_company",
            "card_number",
            "installment_plan_months",
            "status",
            "status_display",
            "approved_at",
            "receipt_url",
            "is_canceled",
            "canceled_amount",
            "cancel_reason",
            "canceled_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "payment_key",
            "approved_at",
            "receipt_url",
            "canceled_at",
        ]


class PaymentRequestSerializer(serializers.Serializer):
    """
    결제 요청용 시리얼라이저
    프론트엔드에서 결제창 열기 전 필요한 정보
    """

    order_id = serializers.IntegerField(help_text="주문 ID")
    payment_method = serializers.CharField(
        max_length=50,
        default="card",
        help_text="결제 수단 (card, bank_transfer 등)",
    )

    def validate_order_id(self, value):
        """주문 검증"""
        user = self.context["request"].user

        try:
            # 관리자 권한 체크
            if user.is_staff or user.is_superuser:
                # 관리자는 모든 주문 접근 가능
                order = Order.objects.get(id=value)
            else:
                # 일반 사용자는 본인 주문만 접근 가능
                order = Order.objects.get(id=value, user=user)
        except Order.DoesNotExist:
            raise serializers.ValidationError("주문을 찾을 수 없습니다.")

        # 이미 결제된 주문인지 확인
        if hasattr(order, "payment") and order.payment.is_paid:
            raise serializers.ValidationError("이미 결제된 주문입니다.")

        # 주문 상태 확인
        if order.status != "pending":
            raise serializers.ValidationError(f"결제할 수 없는 주문 상태입니다: {order.get_status_display()}")

        # 주문 금액이 0원인지 확인 (포인트 전액 결제 허용)
        # final_amount가 0원이어도 허용 (포인트 전액 결제)
        if order.total_amount <= 0:
            raise serializers.ValidationError("결제 금액이 올바르지 않습니다.")

        self.order = order
        return value

    def create(self, validated_data):
        """결제 정보 생성"""
        order = self.order
        payment_method = validated_data.get("payment_method", "card")

        # 기존 Payment가 있으면 삭제 (재시도의 경우)
        Payment.objects.filter(order=order).delete()

        # 새 Payment 생성 (포인트 차감 후 금액으로)
        payment = Payment.objects.create(
            order=order,
            toss_order_id=order.order_number,  # 명시적으로 설정
            amount=order.final_amount,
            method=payment_method,  # 결제 수단 저장
            status="ready",
        )

        # 로그 기록
        PaymentLog.objects.create(
            payment=payment,
            log_type="request",
            message="결제 요청 생성",
            data={
                "order_id": order.id,
                "total_amount": str(order.total_amount),
                "used_points": order.used_points,
                "amount": str(order.final_amount),  # 실제 결제 금액
                "payment_method": payment_method,
            },
        )

        return payment


class PaymentConfirmSerializer(serializers.Serializer):
    """
    결제 승인용 시리얼라이저
    토스페이먼츠 결제창에서 결제 완료 후 승인 요청
    """

    order_id = serializers.CharField(help_text="우리 시스템의 주문번호")

    payment_key = serializers.CharField(help_text="토스페이먼츠 결제키")

    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=0,
        help_text="결제 금액",
    )

    def validate(self, attrs):
        """데이터 검증"""
        order_id = attrs["order_id"]
        amount = attrs["amount"]

        # Payment 찾기 (사용자 검증 포함)
        # select_for_update()로 동시성 제어 - 동일 결제를 동시에 승인하는 것을 방지
        try:
            payment = Payment.objects.select_for_update().get(
                toss_order_id=order_id,
                order__user=self.context["request"].user,  # 보안: 본인 주문만 접근 가능
            )
        except Payment.DoesNotExist:
            raise serializers.ValidationError("결제 정보를 찾을 수 없습니다.")

        # 이미 완료된 결제인지 확인
        if payment.is_paid:
            raise serializers.ValidationError("이미 완료된 결제입니다.")

        # 유효하지 않은 상태 확인 (보안: Toss API 호출 전 사전 검증)
        if payment.status in ["expired", "canceled", "aborted"]:
            raise serializers.ValidationError(f"유효하지 않은 결제 상태입니다: {payment.get_status_display()}")

        # 금액 검증 (포인트 차감 후 금액과 비교)
        if payment.amount != amount:
            raise serializers.ValidationError(f"결제 금액이 일치하지 않습니다. " f"(예상: {payment.amount}, 실제: {amount})")

        self.payment = payment
        return attrs


class PaymentCancelSerializer(serializers.Serializer):
    """
    결제 취소용 시리얼라이저
    """

    payment_id = serializers.IntegerField(help_text="결제 ID")

    cancel_reason = serializers.CharField(max_length=200, help_text="취소 사유")

    def validate_payment_id(self, value):
        """결제 정보 검증"""
        user = self.context["request"].user

        try:
            payment = Payment.objects.get(id=value, order__user=user)
        except Payment.DoesNotExist:
            raise serializers.ValidationError("결제 정보를 찾을 수 없습니다.")

        # 취소 가능한지 확인
        if not payment.can_cancel:
            if payment.is_canceled:
                raise serializers.ValidationError("이미 취소된 결제입니다.")
            else:
                raise serializers.ValidationError("취소할 수 없는 결제입니다.")

        self.payment = payment
        return value


class PaymentLogSerializer(serializers.ModelSerializer):
    """
    결제 로그 조회용 시리얼라이저
    """

    log_type_display = serializers.CharField(source="get_log_type_display", read_only=True)

    class Meta:
        model = PaymentLog
        fields = [
            "id",
            "payment",
            "log_type",
            "log_type_display",
            "message",
            "data",
            "created_at",
        ]


class PaymentWebhookSerializer(serializers.Serializer):
    """
    토스페이먼츠 웹훅 처리용 시리얼라이저
    """

    eventType = serializers.CharField(help_text="이벤트 타입")

    data = serializers.JSONField(help_text="이벤트 데이터")

    def validate_eventType(self, value):
        """지원하는 이벤트 타입인지 확인"""
        supported_events = [
            "PAYMENT.DONE",  # 결제 완료
            "PAYMENT.CANCELED",  # 결제 취소
            "PAYMENT.FAILED",  # 결제 실패
            "PAYMENT.PARTIAL_CANCELED",  # 부분 취소 (향후 지원)
        ]

        if value not in supported_events:
            # 지원하지 않는 이벤트는 무시 (에러 발생시키지 않음)
            self.is_supported = False
        else:
            self.is_supported = True

        return value


class PaymentFailSerializer(serializers.Serializer):
    """
    결제 실패 처리용 시리얼라이저
    토스페이먼츠 결제창에서 실패/취소 시 호출
    """

    code = serializers.CharField(
        max_length=100,
        help_text="실패 코드 (USER_CANCEL, TIMEOUT 등)",
    )

    message = serializers.CharField(
        max_length=500,
        help_text="실패 사유",
    )

    order_id = serializers.CharField(
        max_length=100,
        help_text="토스 주문번호 (toss_order_id)",
    )

    def validate_order_id(self, value: str) -> str:
        """주문 및 결제 정보 검증"""
        try:
            payment = Payment.objects.get(toss_order_id=value)
        except Payment.DoesNotExist:
            raise serializers.ValidationError("결제 정보를 찾을 수 없습니다.")

        # 이미 완료된 결제는 실패 처리 불가
        if payment.status == "done":
            raise serializers.ValidationError("이미 완료된 결제입니다.")

        # 이미 취소된 결제는 실패 처리 불가
        if payment.status == "canceled":
            raise serializers.ValidationError("이미 취소된 결제입니다.")

        self.payment = payment
        return value
