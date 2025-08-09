from rest_framework import serializers
from django.db import transaction
from decimal import Decimal
from django.db.models import F

from ..models.order import Order, OrderItem
from ..models.cart import Cart, CartItem
from ..models.product import Product
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

    def get_subtotal(self, obj):
        return str(obj.get_subtotal())


class OrderListSerializer(serializers.ModelSerializer):
    """주문 목록 조회용 Serializer"""

    user_username = serializers.CharField(source="user.username", read_only=True)
    item_count = serializers.IntegerField(source="order_items.count", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user_username",
            "status",
            "status_display",
            "total_amount",
            "item_count",
            "created_at",
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    """주문 상세 조회용 Serializer"""

    order_items = OrderItemSerializer(many=True, read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    can_cancel = serializers.BooleanField(read_only=True)

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


class OrderCreateSerializer(serializers.ModelSerializer):
    """주문 생성용 Serializer (장바구니 -> 주문 변환)"""

    class Meta:
        model = Order
        fields = [
            "shipping_name",
            "shipping_phone",
            "shipping_postal_code",
            "shipping_address",
            "shipping_address_detail",
            "order_memo",
        ]

    def validate(self, attrs):
        """장바구니 검증"""
        user = self.context["request"].user

        # 활성 장바구니 확인
        try:
            cart = Cart.objects.get(user=user, is_active=True)
        except Cart.DoesNotExist:
            raise serializers.ValidationError("장바구니가 비어있습니다.")

        # 장바구니 아이템 확인
        if not cart.items.exists():
            raise serializers.ValidationError("장바구니가 비어있습니다.")

        # 재고 확인
        for item in cart.items.all():
            if not item.is_available():
                raise serializers.ValidationError(
                    f"{item.product.name}의 재고가 부족합니다."
                )

        self.cart = cart
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """트랜잭션으로 주문 생성"""

        user = self.context["request"].user
        cart = self.cart

        # 1. Order 생성
        order = Order.objects.create(
            user=user,
            status="pending",
            total_amount=cart.total_amount,
            **validated_data,
        )

        # 2. CartItem -> OrderItem 변환
        for cart_item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_name=cart_item.product.name,
                quantity=cart_item.quantity,
                price=cart_item.product.price,
            )

            # 재고 차감 전 한번 더 확인
            product = Product.objects.select_for_update().get(pk=cart_item.product.pk)

            if product.stock < cart_item.quantity:
                raise serializers.ValidationError(
                    f"{product.name}의 재고가 부족합니다."
                    f"(요청: {cart_item.quantity}개, 재고: {product.stock}개)"
                )

            # 3. 재고 차감
            Product.objects.filter(pk=cart_item.product.pk).update(
                stock=F("stock") - cart_item.quantity,
                sold_count=F("sold_count") + cart_item.quantity,
            )

        # 4. 장바구니 비우기
        cart.clear()

        return order
