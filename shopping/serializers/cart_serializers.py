from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from rest_framework import serializers

# 모델 import
from ..models.cart import Cart, CartItem
from ..models.product import Product

# 다른 Serializer import
from .product_serializers import ProductListSerializer


class CartItemSerializer(serializers.ModelSerializer):
    """
    장바구니 아이템 조회용 Serializer

    장바구니에 담긴 개별 상품 정보를 표시할 때 사용합니다.
    상품의 상세 정보와 함께 소계 금액, 재고 상태 등을 제공합니다.
    """

    # 상품 정보를 포함 (ProductListSerializer 재사용)
    product = ProductListSerializer(read_only=True)

    # 상품 기본 정보 (빠른 참조용)
    product_id = serializers.IntegerField(source="product.id", read_only=True, help_text="상품 ID")
    product_name = serializers.CharField(source="product.name", read_only=True, help_text="상품명")
    product_price = serializers.DecimalField(
        source="product.price",
        max_digits=10,
        decimal_places=0,
        read_only=True,
        help_text="상품 단가",
    )

    # 계산 필드들
    subtotal = serializers.SerializerMethodField(help_text="소계 (단가 x 수량)")
    is_available = serializers.SerializerMethodField(help_text="구매 가능 여부 (재고 확인)")
    available_stock = serializers.IntegerField(source="product.stock", read_only=True, help_text="현재 재고 수량")

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",  # 상품 전체 정보
            "product_id",  # 상품 ID만
            "product_name",  # 상품명만
            "product_price",  # 단가
            "quantity",  # 수량
            "subtotal",  # 소계
            "is_available",  # 구매 가능 여부
            "available_stock",  # 재고
            "added_at",  # 추가일시
            "updated_at",  # 수정일시
        ]
        read_only_fields = ["added_at", "updated_at"]

    def get_subtotal(self, obj: CartItem) -> str:
        """
        소계 계산 (모델의 property 활용)

        Returns:
            str: 소계 금액 (문자열로 변환하여 정확한 값 전달)
        """
        return str(obj.subtotal)

    def get_is_available(self, obj: CartItem) -> bool:
        """
        구매 가능 여부 확인

        상품이 활성화되어 있고 재고가 충분한지 확인합니다.

        Returns:
            bool: 구매 가능하면 True
        """
        return obj.is_available()


class CartItemCreateSerializer(serializers.ModelSerializer):
    """
    장바구니에 상품 추가용 Serializer

    POST 요청으로 장바구니에 새 상품을 추가할 때 사용합니다.
    이미 담긴 상품인 경우 수량을 증가시킵니다.
    """

    # 상품 ID로 받기 (필수)
    product_id = serializers.IntegerField(write_only=True, help_text="추가할 상품 ID")

    # 수량 (기본값 1)
    quantity = serializers.IntegerField(
        default=1,
        min_value=1,
        max_value=999,  # 최대 구매 수량 제한
        help_text="추가할 수량 (기본값: 1)",
    )

    class Meta:
        model = CartItem
        fields = ["product_id", "quantity"]

    def validate_product_id(self, value: int) -> int:
        """
        상품 ID 유효성 검증

        - 존재하는 상품인지 확인
        - 활성화된 상품인지 확인
        - 재고가 있는지 확인
        """
        try:
            product = Product.objects.get(pk=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError(f"상품 ID {value}를 찾을 수 없습니다.")

        # 비활성 상품 체크
        if not product.is_active:
            raise serializers.ValidationError("현재 판매하지 않는 상품입니다.")

        # 재고 체크
        if product.stock == 0:
            raise serializers.ValidationError("품절된 상품입니다.")

        # validated_data에 product 객체 저장
        self.product = product
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """
        전체 유효성 검증

        요청한 수량이 재고보다 많은지 확인합니다.
        """
        quantity = attrs.get("quantity", 1)

        # validate_product_id에서 저장한 product 사용
        if hasattr(self, "product"):
            if quantity > self.product.stock:
                raise serializers.ValidationError({"quantity": f"재고가 부족합니다. 현재 재고: {self.product.stock}개"})

        return attrs

    def create(self, validated_data: dict[str, Any]) -> CartItem:
        """
        장바구니 아이템 생성 또는 수량 증가

        트랜잭션을 사용하여 동시성 문제를 방지합니다.
        """
        product_id = validated_data.pop("product_id")
        quantity = validated_data.get("quantity", 1)

        # ViewSet에서 cart를 context로 전달받음
        cart = self.context.get("cart")
        if not cart:
            raise serializers.ValidationError("장바구니 정보가 없습니다.")

        with transaction.atomic():
            # Cart를 잠금 (동시 접근 방지)
            cart = Cart.objects.select_for_update().get(pk=cart.pk)

            try:
                # 기존 아이템을 잠금과 함께 조회
                cart_item = CartItem.objects.select_for_update().get(cart=cart, product_id=product_id)
                # F() 객체로 안전하게 수량 증가 (atomic update)
                CartItem.objects.filter(pk=cart_item.pk).update(quantity=F("quantity") + quantity, updated_at=timezone.now())
                cart_item.refresh_from_db()  # DB에서 최신 값 다시 로드
            except CartItem.DoesNotExist:
                # 없으면 생성
                cart_item = CartItem.objects.create(cart=cart, product_id=product_id, quantity=quantity)

            return cart_item

    def to_representation(self, instance: CartItem) -> dict[str, Any]:
        """
        응답 시 CartItemSerializer 형식으로 변환

        생성 후 전체 정보를 반환합니다.
        """
        return CartItemSerializer(instance, context=self.context).data


class CartItemUpdateSerializer(serializers.ModelSerializer):
    """
    장바구니 아이템 수량 변경용 Serializer

    PUT/PATCH 요청으로 수량을 변경할 때 사용합니다.
    수량이 0이 되면 자동으로 삭제됩니다.
    """

    quantity = serializers.IntegerField(
        min_value=0,  # 0 허용 (삭제 의미)
        max_value=999,
        help_text="변경할 수량 (0이면 삭제)",
    )

    class Meta:
        model = CartItem
        fields = ["quantity"]

    def validate_quantity(self, value: int) -> int:
        """
        수량 유효성 검증

        재고보다 많은 수량을 요청하는지 확인합니다.
        """
        if self.instance and value > 0:
            # 재고 확인
            if value > self.instance.product.stock:
                raise serializers.ValidationError(f"재고가 부족합니다. 현재 재고: {self.instance.product.stock}개")

        return value

    def update(self, instance: CartItem, validated_data: dict[str, Any]) -> CartItem:
        """
        수량 업데이트

        0이면 삭제, 아니면 수량 변경
        select_for_update()로 동시성 처리
        """
        from django.db import transaction

        quantity = validated_data.get("quantity")

        with transaction.atomic():
            # 해당 CartItem을 잠금
            cart_item = CartItem.objects.select_for_update().get(pk=instance.pk)

            if quantity == 0:
                # 수량이 0이면 삭제
                cart_item.delete()
                return cart_item
            else:
                # 직접 UPDATE 쿼리로 수량 변경 (race condition 방지)
                CartItem.objects.filter(pk=cart_item.pk).update(quantity=quantity, updated_at=timezone.now())
                cart_item.refresh_from_db()
                return cart_item


class CartSerializer(serializers.ModelSerializer):
    """
    장바구니 전체 정보 조회용 Serializer

    장바구니의 모든 아이템과 총액, 총 수량 등을 포함합니다.
    주로 장바구니 페이지에서 사용됩니다.
    """

    # 장바구니 아이템들
    items = CartItemSerializer(many=True, read_only=True)

    # 사용자 정보 (간단히)
    user_id = serializers.IntegerField(source="user.id", read_only=True, help_text="사용자 ID")
    user_username = serializers.CharField(source="user.username", read_only=True, help_text="사용자명")

    # 집계 정보
    total_amount = serializers.SerializerMethodField(help_text="총 금액")
    total_quantity = serializers.SerializerMethodField(help_text="총 수량")
    item_count = serializers.SerializerMethodField(help_text="상품 종류 수")

    # 구매 가능 여부
    is_all_available = serializers.SerializerMethodField(help_text="모든 상품 구매 가능 여부")
    unavailable_items = serializers.SerializerMethodField(help_text="구매 불가능한 상품 목록")

    class Meta:
        model = Cart
        fields = [
            "id",
            "user_id",
            "user_username",
            "items",  # 장바구니 아이템들
            "total_amount",  # 총액
            "total_quantity",  # 총 수량
            "item_count",  # 상품 종류 수
            "is_active",
            "is_all_available",  # 모두 구매 가능한지
            "unavailable_items",  # 구매 불가 아이템
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "is_active"]

    def get_total_amount(self, obj: Cart) -> str:
        """
        총 금액 계산 (prefetch된 items로 Python 계산)

        DB aggregate 대신 이미 로드된 데이터를 활용하여 성능 최적화
        """
        total = sum(item.subtotal for item in obj.items.all())
        return str(total)

    def get_total_quantity(self, obj: Cart) -> int:
        """
        총 수량 계산 (prefetch된 items로 Python 계산)

        DB aggregate 대신 이미 로드된 데이터를 활용하여 성능 최적화
        """
        return sum(item.quantity for item in obj.items.all())

    def get_item_count(self, obj: Cart) -> int:
        """
        장바구니에 담긴 상품 종류 수
        """
        return obj.items.count()

    def get_is_all_available(self, obj: Cart) -> bool:
        """
        모든 상품이 구매 가능한지 확인

        get_unavailable_items 결과를 재사용하여 중복 순회 방지
        """
        return len(self.get_unavailable_items(obj)) == 0

    def get_unavailable_items(self, obj: Cart) -> list[dict[str, Any]]:
        """
        구매 불가능한 상품 목록 반환

        재고 부족이나 비활성 상품을 찾아서 반환합니다.
        """
        unavailable = []

        for item in obj.items.all():
            if not item.is_available():
                reason = ""
                if not item.product.is_active:
                    reason = "판매 중단"
                elif item.product.stock == 0:
                    reason = "품절"
                elif item.product.stock < item.quantity:
                    reason = f"재고 부족 (현재 {item.product.stock}개)"

                unavailable.append(
                    {
                        "item_id": item.id,
                        "product_id": item.product.id,
                        "product_name": item.product.name,
                        "requested_quantity": item.quantity,
                        "available_stock": item.product.stock,
                        "reason": reason,
                    }
                )
        return unavailable


class SimpleCartSerializer(serializers.ModelSerializer):
    """
    간단한 장바구니 정보용 Serializer

    헤더나 사이드바에서 장바구니 요약 정보를 보여줄 때 사용합니다.
    """

    total_amount = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "total_amount",
            "total_quantity",
            "item_count",
        ]

    def get_total_amount(self, obj: Cart) -> str:
        """
        총 금액 (prefetch된 items로 Python 계산)
        """
        total = sum(item.subtotal for item in obj.items.all())
        return str(total)

    def get_total_quantity(self, obj: Cart) -> int:
        """
        총 수량 (prefetch된 items로 Python 계산)
        """
        return sum(item.quantity for item in obj.items.all())

    def get_item_count(self, obj: Cart) -> int:
        """
        상품 종류 수 (prefetch된 데이터 활용)
        """
        return len(obj.items.all())


class CartClearSerializer(serializers.Serializer):
    """
    장바구니 비우기 확인용 Serializer

    안전을 위해 확인 메시지를 요구합니다.
    """

    confirm = serializers.BooleanField(required=True, help_text="장바구니를 비우려면 true를 전송하세요.")

    def validate_confirm(self, value: bool) -> bool:  # 특정 필드 검증
        """확인 값 검증"""
        if not value:
            raise serializers.ValidationError("장바구니 비우기를 확인해주세요.")
        return value
