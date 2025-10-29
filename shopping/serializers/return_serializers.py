from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from shopping.models import Order, OrderItem, Product, Return, ReturnItem


class ReturnItemSerializer(serializers.ModelSerializer):
    """반품 상품 항목 Serializer"""

    order_item_id = serializers.IntegerField(write_only=True)
    subtotal = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ReturnItem
        fields = [
            "id",
            "order_item_id",
            "quantity",
            "product_name",
            "product_price",
            "subtotal",
        ]
        read_only_fields = ["id", "product_name", "product_price", "subtotal"]

    def get_subtotal(self, obj):
        """반품 금액 계산"""
        return obj.get_subtotal()


class ReturnCreateSerializer(serializers.ModelSerializer):
    """교환/환불 신청 Serializer"""

    items = ReturnItemSerializer(many=True, write_only=True, source="return_items")

    class Meta:
        model = Return
        fields = [
            "type",
            "reason",
            "reason_detail",
            "items",
            # 환불 정보 (type='refund'일 때만)
            "refund_account_bank",
            "refund_account_number",
            "refund_account_holder",
            # 교환 정보 (type='exchange'일 때만)
            "exchange_product",
        ]

    def validate(self, attrs):
        """데이터 유효성 검증"""
        request = self.context.get("request")
        order_id = self.context.get("order_id")

        # 주문 존재 여부 확인
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            raise serializers.ValidationError("주문을 찾을 수 없습니다.")

        # 주문 상태 확인
        if order.status != "delivered":
            raise serializers.ValidationError("배송 완료된 주문만 신청 가능합니다.")

        # 배송 완료 후 7일 이내 확인
        days_passed = (timezone.now() - order.created_at).days
        if days_passed > 7:
            raise serializers.ValidationError("배송 완료 후 7일이 지나 신청할 수 없습니다.")

        # 이미 신청한 교환/환불이 있는지 확인
        existing_returns = Return.objects.filter(
            order=order, status__in=["requested", "approved", "shipping", "received"]
        ).exists()

        if existing_returns:
            raise serializers.ValidationError("이미 처리 중인 교환/환불이 있습니다.")

        # 환불인 경우 계좌 정보 필수
        if attrs["type"] == "refund":
            if not attrs.get("refund_account_bank") or not attrs.get("refund_account_number"):
                raise serializers.ValidationError("환불 계좌 정보를 입력해주세요.")

        # 교환인 경우 교환 상품 필수
        if attrs["type"] == "exchange":
            if not attrs.get("exchange_product"):
                raise serializers.ValidationError("교환할 상품을 선택해주세요.")

            # 교환 상품 재고 확인
            exchange_product = attrs["exchange_product"]
            if exchange_product.stock < 1:
                raise serializers.ValidationError("교환 상품의 재고가 부족합니다.")

        # 반품 상품 검증
        return_items = attrs.get("return_items", [])
        if not return_items:
            raise serializers.ValidationError("반품할 상품을 선택해주세요.")

        for item_data in return_items:
            order_item_id = item_data.get("order_item_id")
            quantity = item_data.get("quantity")

            # OrderItem 존재 여부 확인
            try:
                order_item = OrderItem.objects.get(id=order_item_id, order=order)
            except OrderItem.DoesNotExist:
                raise serializers.ValidationError(f"주문 상품(ID: {order_item_id})을 찾을 수 없습니다.")

            # 수량 검증
            if quantity > order_item.quantity:
                raise serializers.ValidationError(
                    f"{order_item.product_name}: 반품 수량({quantity})이 주문 수량({order_item.quantity})을 초과할 수 없습니다."
                )

        attrs["order"] = order
        return attrs

    def create(self, validated_data):
        """교환/환불 신청 생성"""
        request = self.context.get("request")
        return_items_data = validated_data.pop("return_items", [])

        with transaction.atomic():
            # Return 생성
            return_obj = Return.objects.create(user=request.user, **validated_data)

            # ReturnItem 생성
            for item_data in return_items_data:
                order_item_id = item_data.pop("order_item_id")
                order_item = OrderItem.objects.get(id=order_item_id)

                ReturnItem.objects.create(
                    return_request=return_obj,
                    order_item=order_item,
                    quantity=item_data["quantity"],
                    product_name=order_item.product_name,
                    product_price=order_item.price,
                )

            # 환불 금액 재계산
            if return_obj.type == "refund":
                return_obj.refund_amount = return_obj.calculate_refund_amount()
                return_obj.save(update_fields=["refund_amount"])

            # 판매자에게 알림 발송
            from shopping.models import Notification

            Notification.objects.create(
                user=return_obj.order.user,  # 주문자가 아닌 판매자에게 알림 (향후 개선)
                type="return",
                title=f"새로운 {return_obj.get_type_display()} 신청",
                message=f"{return_obj.return_number} - {return_obj.get_reason_display()}",
                metadata={"return_id": return_obj.id, "return_number": return_obj.return_number},
            )

        return return_obj


class ReturnListSerializer(serializers.ModelSerializer):
    """교환/환불 목록 Serializer"""

    type_display = serializers.CharField(source="get_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    item_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Return
        fields = [
            "id",
            "return_number",
            "type",
            "type_display",
            "status",
            "status_display",
            "reason",
            "reason_display",
            "order_number",
            "refund_amount",
            "item_count",
            "created_at",
        ]

    def get_item_count(self, obj):
        """반품 상품 개수"""
        return obj.return_items.count()


class ReturnDetailSerializer(serializers.ModelSerializer):
    """교환/환불 상세 Serializer"""

    type_display = serializers.CharField(source="get_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    order_info = serializers.SerializerMethodField(read_only=True)
    return_items = ReturnItemSerializer(many=True, read_only=True)
    exchange_product_info = serializers.SerializerMethodField(read_only=True)

    # 액션 가능 여부
    can_cancel = serializers.SerializerMethodField(read_only=True)
    can_update_tracking = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Return
        fields = [
            "id",
            "return_number",
            "type",
            "type_display",
            "status",
            "status_display",
            "reason",
            "reason_display",
            "reason_detail",
            # 주문 정보
            "order_info",
            "return_items",
            # 반품 배송 정보
            "return_shipping_company",
            "return_tracking_number",
            "return_shipping_fee",
            # 환불 정보
            "refund_amount",
            "refund_method",
            "refund_account_bank",
            "refund_account_number",
            "refund_account_holder",
            # 교환 정보
            "exchange_product_info",
            "exchange_shipping_company",
            "exchange_tracking_number",
            # 처리 정보
            "rejected_reason",
            "approved_at",
            "completed_at",
            # 타임스탬프
            "created_at",
            "updated_at",
            # 액션 가능 여부
            "can_cancel",
            "can_update_tracking",
        ]

    def get_order_info(self, obj):
        """주문 정보"""
        return {
            "id": obj.order.id,
            "order_number": obj.order.order_number,
            "total_amount": obj.order.total_amount,
            "created_at": obj.order.created_at,
        }

    def get_exchange_product_info(self, obj):
        """교환 상품 정보"""
        if obj.type != "exchange" or not obj.exchange_product:
            return None

        product = obj.exchange_product
        return {
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "stock": product.stock,
        }

    def get_can_cancel(self, obj):
        """신청 취소 가능 여부"""
        return obj.status == "requested"

    def get_can_update_tracking(self, obj):
        """송장번호 입력 가능 여부"""
        return obj.status == "approved"


class ReturnUpdateSerializer(serializers.ModelSerializer):
    """송장번호 업데이트 Serializer (고객)"""

    class Meta:
        model = Return
        fields = [
            "return_shipping_company",
            "return_tracking_number",
        ]

    def validate(self, attrs):
        """송장번호 입력 가능 상태인지 확인"""
        if self.instance.status != "approved":
            raise serializers.ValidationError("승인된 신청만 송장번호를 입력할 수 있습니다.")

        if not attrs.get("return_shipping_company") or not attrs.get("return_tracking_number"):
            raise serializers.ValidationError("택배사와 송장번호를 모두 입력해주세요.")

        return attrs

    def update(self, instance, validated_data):
        """송장번호 업데이트 및 상태 변경"""
        instance.return_shipping_company = validated_data["return_shipping_company"]
        instance.return_tracking_number = validated_data["return_tracking_number"]
        instance.status = "shipping"  # 상태를 '반품배송중'으로 변경
        instance.save()

        # 판매자에게 알림
        from shopping.models import Notification

        Notification.objects.create(
            user=instance.order.user,  # 판매자 (향후 개선)
            type="return",
            title="반품 상품 발송",
            message=f"{instance.return_number} - 고객이 반품 상품을 발송했습니다. 송장번호: {instance.return_tracking_number}",
            metadata={
                "return_id": instance.id,
                "return_number": instance.return_number,
                "tracking_number": instance.return_tracking_number,
            },
        )

        return instance


class ReturnApproveSerializer(serializers.Serializer):
    """승인 Serializer (판매자)"""

    admin_memo = serializers.CharField(required=False, allow_blank=True, help_text="관리자 메모")

    def validate(self, attrs):
        """승인 가능 상태인지 확인"""
        return_obj = self.context.get("return_obj")

        if return_obj.status != "requested":
            raise serializers.ValidationError("신청 상태에서만 승인할 수 있습니다.")

        return attrs

    def save(self):
        """승인 처리"""
        return_obj = self.context.get("return_obj")
        admin_memo = self.validated_data.get("admin_memo", "")

        if admin_memo:
            return_obj.admin_memo = admin_memo

        return_obj.approve()
        return return_obj


class ReturnRejectSerializer(serializers.Serializer):
    """거부 Serializer (판매자)"""

    rejected_reason = serializers.CharField(required=True, help_text="거부 사유")

    def validate(self, attrs):
        """거부 가능 상태인지 확인"""
        return_obj = self.context.get("return_obj")

        if return_obj.status != "requested":
            raise serializers.ValidationError("신청 상태에서만 거부할 수 있습니다.")

        return attrs

    def save(self):
        """거부 처리"""
        return_obj = self.context.get("return_obj")
        rejected_reason = self.validated_data["rejected_reason"]

        return_obj.reject(rejected_reason)
        return return_obj


class ReturnConfirmReceiveSerializer(serializers.Serializer):
    """반품 도착 확인 Serializer (판매자)"""

    def validate(self, attrs):
        """수령 확인 가능 상태인지 확인"""
        return_obj = self.context.get("return_obj")

        if return_obj.status != "shipping":
            raise serializers.ValidationError("배송 중 상태에서만 수령 확인할 수 있습니다.")

        return attrs

    def save(self):
        """수령 확인 처리"""
        return_obj = self.context.get("return_obj")
        return_obj.confirm_receive()
        return return_obj


class ReturnCompleteSerializer(serializers.Serializer):
    """완료 처리 Serializer (판매자)"""

    # 교환인 경우 교환 상품 송장번호 필수
    exchange_tracking_number = serializers.CharField(
        required=False, allow_blank=True, help_text="교환 상품 송장번호 (교환인 경우 필수)"
    )
    exchange_shipping_company = serializers.CharField(
        required=False, allow_blank=True, help_text="교환 상품 택배사 (교환인 경우 필수)"
    )

    def validate(self, attrs):
        """완료 처리 가능 상태인지 확인"""
        return_obj = self.context.get("return_obj")

        if return_obj.status != "received":
            raise serializers.ValidationError("반품 도착 상태에서만 완료 처리할 수 있습니다.")

        # 교환인 경우 송장번호 필수
        if return_obj.type == "exchange":
            if not attrs.get("exchange_tracking_number") or not attrs.get("exchange_shipping_company"):
                raise serializers.ValidationError("교환 상품의 택배사와 송장번호를 입력해주세요.")

        return attrs

    def save(self):
        """완료 처리 (환불 또는 교환)"""
        return_obj = self.context.get("return_obj")

        if return_obj.type == "refund":
            # 환불 처리
            return_obj.complete_refund()
        else:
            # 교환 처리
            return_obj.exchange_tracking_number = self.validated_data["exchange_tracking_number"]
            return_obj.exchange_shipping_company = self.validated_data["exchange_shipping_company"]
            return_obj.save(update_fields=["exchange_tracking_number", "exchange_shipping_company"])

            return_obj.complete_exchange()

        return return_obj
