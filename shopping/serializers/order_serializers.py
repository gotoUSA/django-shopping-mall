from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F, QuerySet

from rest_framework import serializers

from ..models.cart import Cart
from ..models.order import Order, OrderItem
from ..models.point import PointHistory
from ..models.product import Product
from ..services.order_service import OrderService, OrderServiceError
from ..services.shipping_service import ShippingService
from .product_serializers import ProductListSerializer


class OrderItemSerializer(serializers.ModelSerializer):
    """주문 상품 조회용 Serializer"""

    product_info = ProductListSerializer(source="product", read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_info",
            "product_name",  # 주문 당시 상품명
            "quantity",
            "price",  # 주문 당시 가격
            "subtotal",
        ]
        read_only_fields = ["product_name", "price"]

    def get_subtotal(self, obj: OrderItem) -> str:
        return str(obj.get_subtotal())


class OrderListSerializer(serializers.ModelSerializer):
    """주문 목록 조회용 Serializer"""

    user_username = serializers.CharField(source="user.username", read_only=True)
    item_count = serializers.IntegerField(source="order_items.count", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    total_shipping_fee = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "user_username",
            "status",
            "status_display",
            "total_amount",
            "shipping_fee",
            "total_shipping_fee",
            "used_points",
            "final_amount",
            "item_count",
            "created_at",
        ]

    def get_total_shipping_fee(self, obj: Order) -> str:
        """전체 배송비 반환"""
        return str(obj.get_total_shipping_fee())


class OrderDetailSerializer(serializers.ModelSerializer):
    """주문 상세 조회용 Serializer"""

    order_items = OrderItemSerializer(many=True, read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    can_cancel = serializers.BooleanField(read_only=True)
    total_shipping_fee = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "user_username",
            "status",
            "status_display",
            "order_items",
            "total_amount",
            "shipping_fee",
            "additional_shipping_fee",
            "is_free_shipping",
            "total_shipping_fee",
            "used_points",
            "final_amount",
            "earned_points",
            "shipping_name",
            "shipping_phone",
            "shipping_postal_code",
            "shipping_address",
            "shipping_address_detail",
            "order_memo",
            "payment_method",
            "can_cancel",
            "created_at",
            "updated_at",
        ]

    def get_total_shipping_fee(self, obj: Order) -> str:
        """전체 배송비 반환"""
        return str(obj.get_total_shipping_fee())


class OrderCreateSerializer(serializers.ModelSerializer):
    """
    주문 생성용 Serializer (장바구니 -> 주문 변환)

    ⚠️ 변경사항: 포인트 사용 기능 추가
    - 주문 생성시 포인트 사용 가능
    - 최소 100포인트 이상 사용
    - 최대 주문 금액의 100%까지 사용 가능
    """

    use_points = serializers.IntegerField(
        default=0,
        min_value=0,
        required=False,
        help_text="사용할 포인트 (최소 100포인트)",
    )

    class Meta:
        model = Order
        fields = [
            "id",
            "shipping_name",
            "shipping_phone",
            "shipping_postal_code",
            "shipping_address",
            "shipping_address_detail",
            "order_memo",
            "use_points",
        ]
        read_only_fields = ["id"]

    def _validate_cart_items(self, cart: Cart) -> QuerySet:
        """
            장바구니 항목 검증 (별도 메서드)

        검증 항목:
        - 비활성 상품 (is_active=False)
        - 품절 상품 (stock=0)
        - 재고 부족 (stock < quantity)

        Args:
            cart: 검증할 장바구니 객체

        Returns:
            QuerySet: 검증된 장바구니 항목들

        Raises:
            ValidationError: 검증 실패 시 (모든 에러를 리스트로 반환)
        """
        cart_items = cart.items.select_related("product")

        if not cart_items.exists():
            raise serializers.ValidationError("장바구니가 비어있습니다.")

        # 검증 에러 목록
        errors = []

        for item in cart_items:
            product = item.product

            # 1. 비활성 상품 체크
            if not product.is_active:
                errors.append(f"'{product.name}'은(는) 현재 판매하지 않는 상품입니다.")
                continue

            # 2. 품절 체크
            if product.stock == 0:
                errors.append(f"'{product.name}'은(는) 품절되었습니다.")

            # 3. 재고 부족 체크
            if product.stock < item.quantity:
                errors.append(f"'{product.name}'의 재고가 부족합니다. " f"(요청: {item.quantity}개, 재고: {product.stock}개)")

        # 에러가 있으면 모두 반환
        if errors:
            raise serializers.ValidationError({"cart_items": errors})

        return cart_items

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """장바구니 및 포인트 검증"""
        user = self.context["request"].user
        use_points = attrs.get("use_points", 0)

        # 이메일 인증 확인
        if not user.is_email_verified:
            raise serializers.ValidationError("이메일 인증이 필요합니다. 먼저 이메일을 인증해주세요.")

        # 장바구니 확인
        cart = Cart.objects.filter(user=user, is_active=True).first()
        if not cart or not cart.items.exists():
            raise serializers.ValidationError("장바구니가 비어있습니다.")

        # 장바구니 항목 검증 (비활성 상품, 품절, 재고 부족)
        self._validate_cart_items(cart)

        # 배송비 계산 (ShippingService 사용)
        total_amount = cart.total_amount
        shipping_postal_code = attrs.get("shipping_postal_code", "")
        shipping_result = ShippingService.calculate_fee(
            total_amount=total_amount, postal_code=shipping_postal_code
        )

        # 배송비를 포함한 총 결제 예정 금액
        total_payment_amount = (
            total_amount + shipping_result["shipping_fee"] + shipping_result["additional_fee"]
        )

        # 포인트 검증
        if use_points > 0:
            # 최소 사용 포인트 체크 (100포인트)
            if use_points < 100:
                raise serializers.ValidationError("포인트는 최소 100포인트 이상 사용 가능합니다.")

            # 보유 포인트 체크
            if use_points > user.points:
                raise serializers.ValidationError(
                    f"보유 포인트가 부족합니다. (보유: {user.points}P, 사용 요청: {use_points}P)"
                )

            # 배송비를 포함한 총 금액보다 많은 포인트 사용 불가
            if use_points > total_payment_amount:
                raise serializers.ValidationError(
                    f"주문 금액보다 많은 포인트를 사용할 수 없습니다. "
                    f"(주문 금액: {total_payment_amount}원, 사용 요청: {use_points}P)"
                )

        self.cart = cart
        attrs["use_points"] = use_points
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Order:
        """
        주문 생성 (OrderService 위임)

        비즈니스 로직은 OrderService에서 처리
        """
        user = self.context["request"].user
        cart = self.cart
        use_points = validated_data.pop("use_points", 0)

        try:
            # OrderService를 통한 주문 생성
            order = OrderService.create_order_from_cart(
                user=user,
                cart=cart,
                shipping_name=validated_data["shipping_name"],
                shipping_phone=validated_data["shipping_phone"],
                shipping_postal_code=validated_data["shipping_postal_code"],
                shipping_address=validated_data["shipping_address"],
                shipping_address_detail=validated_data.get("shipping_address_detail", ""),
                order_memo=validated_data.get("order_memo", ""),
                use_points=use_points,
            )
            return order
        except OrderServiceError as e:
            raise serializers.ValidationError(str(e))

    def to_representation(self, instance: Order) -> dict[str, Any]:
        """
        생성 응답시 OrderDetailSerializer 사용
        배송비 등 모든 정보를 응답에 포함
        """
        return OrderDetailSerializer(instance, context=self.context).data
