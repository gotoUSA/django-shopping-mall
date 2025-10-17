from rest_framework import serializers
from django.db import transaction
from decimal import Decimal
from django.db.models import F

from ..models.order import Order, OrderItem
from ..models.cart import Cart, CartItem
from ..models.product import Product
from ..models.point import PointHistory
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

    def get_total_shipping_fee(self, obj):
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

    def get_total_shipping_fee(self, obj):
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
            "shipping_name",
            "shipping_phone",
            "shipping_postal_code",
            "shipping_address",
            "shipping_address_detail",
            "order_memo",
            "use_points",
        ]

    def validate(self, attrs):
        """장바구니 검증"""
        user = self.context["request"].user
        use_points = attrs.get("use_points", 0)

        # 이메일 인증 확인
        if not user.is_email_verified:
            raise serializers.ValidationError(
                "이메일 인증이 필요합니다. 먼저 이메일을 인증해주세요."
            )
        # 장바구니 확인
        cart = Cart.objects.filter(user=user, is_active=True).first()
        if not cart or not cart.items.exists():
            raise serializers.ValidationError("장바구니가 비어있습니다.")

        # 재고 확인 (차감하지 않고 체크만)
        for item in cart.items.all():
            if item.product.stock < item.quantity:
                raise serializers.ValidationError(
                    f"{item.product.name}의 재고가 부족합니다. "
                    f"(현재 재고: {item.product.stock}개)"
                )

        # 배송비 미리 계산
        total_amount = cart.total_amount

        # 도서 산간 지역 체크 (우편번호 기반)
        shipping_postal_code = attrs.get("shipping_postal_code", "")
        remote_area_postal_codes = ["63", "59", "52"]  # 제주, 울릉도 등
        is_remote = any(
            shipping_postal_code.startswith(code) for code in remote_area_postal_codes
        )

        # 배송비 계산
        FREE_SHIPPING_THRESHOLD = Decimal("30000")
        DEFAULT_SHIPPING_FEE = Decimal("3000")
        REMOTE_AREA_FEE = Decimal("3000")

        if total_amount >= FREE_SHIPPING_THRESHOLD:
            shipping_fee = Decimal("0")
            additional_shipping_fee = REMOTE_AREA_FEE if is_remote else Decimal("0")
        else:
            shipping_fee = DEFAULT_SHIPPING_FEE
            additional_shipping_fee = REMOTE_AREA_FEE if is_remote else Decimal("0")

        # 배송비를 포함한 총 결제 예정 금액
        total_payment_amount = total_amount + shipping_fee + additional_shipping_fee

        # 포인트 검증
        if use_points > 0:
            # 최소 사용 포인트 체크 (100포인트)
            if use_points < 100:
                raise serializers.ValidationError(
                    "포인트는 최소 100포인트 이상 사용 가능합니다."
                )

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

    @transaction.atomic
    def create(self, validated_data):
        """
        트랜잭션으로 주문 생성

        변경사항:
        - 포인트 사용 처리 추가
        - 포인트 이력 기록
        """

        user = self.context["request"].user
        cart = self.cart
        use_points = validated_data.pop("use_points", 0)

        # 1. Order 생성
        total_amount = cart.total_amount
        final_amount = max(Decimal("0"), total_amount - Decimal(str(use_points)))

        order = Order.objects.create(
            user=user,
            status="pending",  # 결제 대기 상태
            total_amount=total_amount,
            used_points=use_points,  # 양수로 저장 (0 이상)
            final_amount=final_amount,
            **validated_data,
        )

        # 도서 산간 지역 체크 (우편번호 기반)
        remote_area_postal_codes = ["63", "59", "52"]  # 제주, 울릉도 등
        is_remote = any(
            order.shipping_postal_code.startswith(code)
            for code in remote_area_postal_codes
        )

        # 배송비 적용 (이미 생성된 order 객체에 적용)
        order.apply_shipping_fee(is_remote_area=is_remote)

        # 2. CartItem -> OrderItem 변환
        for cart_item in cart.items.all():
            # 재고 최종 확인(select_for_update로 동시성 제어)
            product = Product.objects.select_for_update().get(pk=cart_item.product.pk)

            if product.stock < cart_item.quantity:
                raise serializers.ValidationError(
                    f"{product.name}의 재고가 부족합니다. "
                    f"(요청: {cart_item.quantity}개, 재고: {product.stock}개)"
                )

            # OrderItem 생성 (재고는 차감하지 않음)
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_name=cart_item.product.name,
                quantity=cart_item.quantity,
                price=cart_item.product.price,
            )

        # 3. 포인트 사용 처리
        if use_points > 0:
            # 포인트 차감
            user.use_points(use_points)

            # 포인트 사용 이력 기록
            PointHistory.create_history(
                user=user,
                points=-use_points,  # 음수로 기록
                type="use",
                order=order,
                description=f"주문 #{order.order_number} 결제시 사용",
                metadata={
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "total_amount": str(total_amount),
                    "final_amount": str(final_amount),
                },
            )

        return order
