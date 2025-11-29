from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import F, Prefetch

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, serializers as drf_serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from shopping.models.cart import Cart, CartItem
from shopping.models.product import Product
from shopping.serializers import (
    CartClearSerializer,
    CartItemCreateSerializer,
    CartItemSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
    SimpleCartSerializer,
)


# ===== Swagger 문서화용 응답 Serializers =====

class CartAddItemResponseSerializer(drf_serializers.Serializer):
    """장바구니 상품 추가 응답"""
    message = drf_serializers.CharField()
    item = CartItemSerializer()


class CartUpdateItemResponseSerializer(drf_serializers.Serializer):
    """장바구니 수량 변경 응답"""
    message = drf_serializers.CharField()
    item = CartItemSerializer()


class CartMessageResponseSerializer(drf_serializers.Serializer):
    """장바구니 일반 메시지 응답"""
    message = drf_serializers.CharField()


class CartErrorResponseSerializer(drf_serializers.Serializer):
    """장바구니 에러 응답"""
    error = drf_serializers.CharField(required=False)
    message = drf_serializers.CharField(required=False)
    product_id = drf_serializers.ListField(child=drf_serializers.CharField(), required=False)
    quantity = drf_serializers.ListField(child=drf_serializers.CharField(), required=False)


class CartBulkAddItemSerializer(drf_serializers.Serializer):
    """장바구니 일괄 추가 개별 아이템"""
    product_id = drf_serializers.IntegerField(help_text="상품 ID")
    quantity = drf_serializers.IntegerField(default=1, help_text="수량 (기본값: 1)")


class CartBulkAddRequestSerializer(drf_serializers.Serializer):
    """장바구니 일괄 추가 요청"""
    items = drf_serializers.ListField(
        child=CartBulkAddItemSerializer(),
        help_text="추가할 상품 목록"
    )


class CartBulkAddResponseSerializer(drf_serializers.Serializer):
    """장바구니 일괄 추가 응답"""
    message = drf_serializers.CharField()
    added_items = CartItemSerializer(many=True)
    errors = drf_serializers.ListField(required=False)
    error_count = drf_serializers.IntegerField(required=False)


class CartStockCheckResponseSerializer(drf_serializers.Serializer):
    """재고 확인 응답"""
    has_issues = drf_serializers.BooleanField()
    issues = drf_serializers.ListField(required=False)
    message = drf_serializers.CharField()


@extend_schema_view(
    retrieve=extend_schema(
        summary="장바구니 조회",
        description="현재 사용자의 장바구니 전체 정보를 조회합니다.",
        tags=["장바구니"],
    ),
)
class CartViewSet(viewsets.GenericViewSet):
    """
    장바구니 관리 ViewSet

    회원/비회원 모두 사용 가능합니다.
    - 회원: user 기반 장바구니
    - 비회원: session_key 기반 장바구니

    엔드포인트:
    - GET    /api/cart/            - 장바구니 조회
    - GET    /api/cart/summary/    - 장바구니 요약
    - POST   /api/cart/add_item/   - 상품 추가
    - GET    /api/cart/items/      - 아이템 목록
    - PATCH  /api/cart/items/{id}/ - 수량 변경
    - DELETE /api/cart/items/{id}/ - 아이템 삭제
    - POST   /api/cart/clear/      - 장바구니 비우기
    - POST   /api/cart/bulk_add/   - 일괄 추가
    - GET    /api/cart/check_stock/ - 재고 확인
    """

    permission_classes = [permissions.AllowAny]
    queryset = Cart.objects.none()

    def get_serializer_class(self) -> type[BaseSerializer]:
        """
        액션에 따라 적절한 Serializer 반환
        """
        if self.action == "retrieve":
            return CartSerializer
        elif self.action == "summary":
            return SimpleCartSerializer
        elif self.action == "add_item":
            return CartItemCreateSerializer
        elif self.action == "update_item":
            return CartItemUpdateSerializer
        elif self.action == "clear":
            return CartClearSerializer
        else:
            return CartSerializer

    def get_cart(self) -> Cart:
        """
        현재 사용자/세션의 활성 장바구니를 가져오거나 생성

        회원: user 기반 장바구니
        비회원: session_key 기반 장바구니

        Returns:
            cart: 활성 장바구니
        """
        # 회원/비회원 구분
        if self.request.user.is_authenticated:
            # 회원 장바구니
            cart, created = Cart.get_or_create_active_cart(user=self.request.user)
        else:
            # 비회원 장바구니: 세션 키 사용
            session_key = self.request.session.session_key
            if not session_key:
                # 세션이 없으면 생성
                self.request.session.create()
                session_key = self.request.session.session_key
            cart, created = Cart.get_or_create_active_cart(session_key=session_key)

        # 성능 최적화: 관련 데이터 미리 로드
        # prefetch_related: 1:N 관계 (items와 각 item의 product)
        cart = Cart.objects.prefetch_related(
            Prefetch(
                "items",
                queryset=CartItem.objects.select_related("product").order_by("-added_at"),  # 최근 추가된 순서로
            )
        ).get(pk=cart.pk)

        return cart

    @extend_schema(
        responses={200: CartSerializer},
        summary="장바구니 조회",
        description="현재 사용자의 장바구니 전체 정보를 조회합니다.",
        tags=["장바구니"],
    )
    def retrieve(self, request: Request) -> Response:
        """장바구니 전체 정보 조회"""
        cart = self.get_cart()
        serializer = self.get_serializer(cart)
        return Response(serializer.data)

    @extend_schema(
        responses={200: SimpleCartSerializer},
        summary="장바구니 요약",
        description="헤더/사이드바용 간단한 장바구니 정보를 반환합니다.",
        tags=["장바구니"],
    )
    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        """장바구니 요약 정보 조회"""
        cart = self.get_cart()
        serializer = self.get_serializer(cart)
        return Response(serializer.data)

    @extend_schema(
        request=CartItemCreateSerializer,
        responses={
            201: CartAddItemResponseSerializer,
            400: CartErrorResponseSerializer,
        },
        summary="장바구니에 상품 추가",
        description="""
장바구니에 상품을 추가합니다.

**요청 본문:**
```json
{
    "product_id": 1,
    "quantity": 2
}
```

**특징:**
- 이미 담긴 상품이면 수량만 증가
- 회원/비회원 모두 사용 가능
        """,
        tags=["장바구니"],
    )
    @action(detail=False, methods=["post"])
    def add_item(self, request: Request) -> Response:
        """장바구니에 상품 추가"""
        cart = self.get_cart()

        # Serializer에 cart 정보를 context로 전달
        serializer = self.get_serializer(data=request.data, context={"request": request, "cart": cart})

        if serializer.is_valid():
            # 트랜잭션으로 처리 (동시성 문제 방지)
            with transaction.atomic():
                cart_item = serializer.save()

            # 성공 메시지와 함께 추가된 아이템 정보 반환
            return Response(
                {
                    "message": "장바구니에 추가되었습니다.",
                    "item": CartItemSerializer(cart_item).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={200: CartItemSerializer(many=True)},
        summary="장바구니 아이템 목록",
        description="장바구니의 아이템만 별도로 조회합니다.",
        tags=["장바구니"],
    )
    @action(detail=False, methods=["get"])
    def items(self, request: Request) -> Response:
        """장바구니 아이템 목록 조회"""
        cart = self.get_cart()
        items = cart.items.select_related("product").order_by("-added_at")
        serializer = CartItemSerializer(items, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=CartItemUpdateSerializer,
        responses={
            200: CartUpdateItemResponseSerializer,
            204: None,
            400: CartErrorResponseSerializer,
            404: CartErrorResponseSerializer,
        },
        summary="장바구니 아이템 수량 변경",
        description="""
아이템 수량을 변경합니다.

**요청 본문:**
```json
{
    "quantity": 3
}
```

**특징:**
- quantity가 0이면 아이템 삭제
        """,
        tags=["장바구니"],
    )
    @action(detail=True, methods=["patch"], url_path="items")
    def update_item(self, request: Request, pk: int | None = None) -> Response:
        """장바구니 아이템 수량 변경"""
        cart = self.get_cart()

        # 해당 아이템이 현재 사용자의 장바구니에 있는지 확인
        try:
            cart_item = cart.items.get(pk=pk)
        except CartItem.DoesNotExist:
            raise NotFound("장바구니에 해당 상품이 없습니다.")

        serializer = self.get_serializer(cart_item, data=request.data, partial=True)  # PATCH 요청이므로 부분 업데이트

        if serializer.is_valid():
            # 수량이 0이면 삭제됨
            quantity = serializer.validated_data.get("quantity")

            if quantity == 0:
                cart_item.delete()
                return Response(
                    {"message": "장바구니에서 삭제되었습니다."},
                    status=status.HTTP_204_NO_CONTENT,
                )
            else:
                cart_item = serializer.save()
                return Response(
                    {
                        "message": "수량이 변경되었습니다.",
                        "item": CartItemSerializer(cart_item).data,
                    }
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={
            204: CartMessageResponseSerializer,
            404: CartErrorResponseSerializer,
        },
        summary="장바구니 아이템 삭제",
        description="장바구니에서 특정 상품을 완전히 제거합니다.",
        tags=["장바구니"],
    )
    @action(detail=True, methods=["delete"], url_path="items")
    def delete_item(self, request: Request, pk: int | None = None) -> Response:
        """장바구니 아이템 삭제"""
        cart = self.get_cart()

        try:
            cart_item = cart.items.get(pk=pk)
        except CartItem.DoesNotExist:
            raise NotFound("장바구니에 해당 상품이 없습니다.")

        # 삭제 전 상품명 저장 (응답 메시지용)
        product_name = cart_item.product.name
        cart_item.delete()

        return Response(
            {"message": f"{product_name}이(가) 장바구니에서 삭제되었습니다."},
            status=status.HTTP_204_NO_CONTENT,
        )

    @extend_schema(
        request=CartClearSerializer,
        responses={
            200: CartMessageResponseSerializer,
            400: CartErrorResponseSerializer,
        },
        summary="장바구니 비우기",
        description="""
장바구니를 비웁니다.

**요청 본문:**
```json
{
    "confirm": true
}
```

**주의:**
- 실수 방지를 위해 confirm=true 필수
        """,
        tags=["장바구니"],
    )
    @action(detail=False, methods=["post"])
    def clear(self, request: Request) -> Response:
        """장바구니 비우기"""
        cart = self.get_cart()

        # 빈 장바구니인지 확인
        if not cart.items.exists():
            return Response(
                {"message": "장바구니가 이미 비어있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # 장바구니 비우기
            item_count = cart.items.count()
            cart.clear()

            return Response(
                {"message": f"{item_count}개의 상품이 장바구니에서 삭제되었습니다."},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=CartBulkAddRequestSerializer,
        responses={
            201: CartBulkAddResponseSerializer,
            207: CartBulkAddResponseSerializer,
            400: CartErrorResponseSerializer,
        },
        summary="여러 상품 한 번에 담기",
        description="""
여러 상품을 한 번에 장바구니에 추가합니다. (N+1 쿼리 최적화)

**요청 본문:**
```json
{
    "items": [
        {"product_id": 1, "quantity": 2},
        {"product_id": 3, "quantity": 1}
    ]
}
```

**활용:**
- 찜 목록에서 여러 상품을 한 번에 담을 때 유용

**응답:**
- 201: 전체 성공
- 207: 일부 성공 (Multi-Status)
        """,
        tags=["장바구니"],
    )
    @action(detail=False, methods=["post"])
    def bulk_add(self, request: Request) -> Response:
        """여러 상품을 한 번에 장바구니에 추가 (N+1 쿼리 최적화)"""
        cart = self.get_cart()
        items_data = request.data.get("items", [])

        if not items_data:
            return Response(
                {"error": "추가할 상품 정보가 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # N+1 쿼리 방지: 사전에 모든 product_id 수집 후 bulk 조회
        product_ids = [item.get("product_id") for item in items_data if "product_id" in item]
        products = {p.id: p for p in Product.objects.filter(id__in=product_ids, is_active=True)}

        added_items = []
        errors = []

        # 트랜잭션으로 전체 처리
        with transaction.atomic():
            # Cart 잠금 (동시성 제어)
            cart = Cart.objects.select_for_update().get(pk=cart.pk)

            for idx, item_data in enumerate(items_data):
                product_id = item_data.get("product_id")
                quantity = item_data.get("quantity", 1)

                # 유효성 검증
                if not product_id:
                    errors.append({"index": idx, "product_id": None, "errors": {"product_id": "상품 ID가 필요합니다."}})
                    continue

                # 사전 조회한 products dict 활용
                if product_id not in products:
                    errors.append(
                        {
                            "index": idx,
                            "product_id": product_id,
                            "errors": {"product_id": "상품을 찾을 수 없거나 판매 중단되었습니다."},
                        }
                    )
                    continue

                product = products[product_id]

                # 수량 검증
                if not isinstance(quantity, int) or quantity < 1:
                    errors.append(
                        {"index": idx, "product_id": product_id, "errors": {"quantity": "수량은 1 이상이어야 합니다."}}
                    )
                    continue

                if quantity > 999:
                    errors.append(
                        {"index": idx, "product_id": product_id, "errors": {"quantity": "수량은 999 이하여야 합니다."}}
                    )
                    continue

                # 재고 검증
                if product.stock < quantity:
                    errors.append(
                        {
                            "index": idx,
                            "product_id": product_id,
                            "errors": {"quantity": f"재고 부족. 현재 재고: {product.stock}개"},
                        }
                    )
                    continue

                # CartItem 생성/업데이트 (F() 사용하여 atomic update)
                try:
                    # select_for_update()와 get_or_create()를 분리하여 cart_id null 문제 방지
                    cart_item = cart.items.filter(product_id=product_id).select_for_update().first()

                    if cart_item:
                        # 이미 있으면 수량 증가
                        CartItem.objects.filter(pk=cart_item.pk).update(quantity=F("quantity") + quantity)
                        cart_item.refresh_from_db()
                    else:
                        # 새로 생성 - cart FK를 명시적으로 설정
                        cart_item = CartItem.objects.create(cart=cart, product_id=product_id, quantity=quantity)

                    added_items.append(cart_item)
                except Exception as e:
                    errors.append({"index": idx, "product_id": product_id, "errors": {"detail": str(e)}})

        # 응답 생성
        response_data = {
            "message": f"{len(added_items)}개의 상품이 추가되었습니다.",
            "added_items": CartItemSerializer(added_items, many=True).data,
        }

        if errors:
            response_data["errors"] = errors
            response_data["error_count"] = len(errors)
            return Response(response_data, status=status.HTTP_207_MULTI_STATUS)

        return Response(response_data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={
            200: CartStockCheckResponseSerializer,
        },
        summary="장바구니 재고 확인",
        description="""
장바구니 상품들의 재고를 확인합니다.

**활용:**
- 주문 직전에 재고를 다시 확인할 때 사용

**응답:**
- has_issues: 재고 문제 여부
- issues: 재고 문제가 있는 상품 목록 (판매 중단, 품절, 재고 부족)
        """,
        tags=["장바구니"],
    )
    @action(detail=True, methods=["get"])
    def check_stock(self, request: Request) -> Response:
        """장바구니 상품들의 재고 확인"""
        cart = self.get_cart()

        # 재고 부족 상품 찾기
        stock_issues = []

        for item in cart.items.select_related("product"):
            product = item.product

            if not product.is_active:
                stock_issues.append(
                    {
                        "item_id": item.id,
                        "product_id": product.id,
                        "product_name": product.name,
                        "issue": "판매 중단",
                        "requested": item.quantity,
                        "available": 0,
                    }
                )
            elif product.stock == 0:
                stock_issues.append(
                    {
                        "item_id": item.id,
                        "product_id": product.id,
                        "product_name": product.name,
                        "issue": "품절",
                        "requested": item.quantity,
                        "available": 0,
                    }
                )
            elif product.stock < item.quantity:
                stock_issues.append(
                    {
                        "item_id": item.id,
                        "product_id": product.id,
                        "product_name": product.name,
                        "issue": "재고 부족",
                        "requested": item.quantity,
                        "available": product.stock,
                    }
                )

        if stock_issues:
            return Response(
                {
                    "has_issues": True,
                    "issues": stock_issues,
                    "message": "일부 상품의 재고가 부족합니다.",
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"has_issues": False, "message": "모든 상품을 구매할 수 있습니다."},
            status=status.HTTP_200_OK,
        )


# ===== CartItemViewSet 응답 Serializers =====


class CartItemListResponseSerializer(drf_serializers.Serializer):
    """장바구니 아이템 목록 응답"""

    # CartItemSerializer와 동일한 구조의 리스트


class CartItemCreateResponseSerializer(drf_serializers.Serializer):
    """장바구니 아이템 생성 응답"""

    id = drf_serializers.IntegerField()
    product = drf_serializers.DictField()
    quantity = drf_serializers.IntegerField()


class CartItemUpdateResponseSerializer(drf_serializers.Serializer):
    """장바구니 아이템 수정 응답"""

    id = drf_serializers.IntegerField()
    product = drf_serializers.DictField()
    quantity = drf_serializers.IntegerField()


@extend_schema_view(
    list=extend_schema(
        responses={200: CartItemListResponseSerializer(many=True)},
        summary="장바구니 아이템 목록",
        description="현재 사용자/세션의 장바구니 아이템 목록을 조회합니다.",
        tags=["장바구니"],
    ),
    create=extend_schema(
        request=CartItemCreateSerializer,
        responses={
            201: CartItemCreateResponseSerializer,
            400: CartErrorResponseSerializer,
        },
        summary="장바구니에 아이템 추가",
        description="장바구니에 상품을 추가합니다. 회원/비회원 모두 사용 가능합니다.",
        tags=["장바구니"],
    ),
    update=extend_schema(
        request=CartItemUpdateSerializer,
        responses={
            200: CartItemUpdateResponseSerializer,
            204: None,
            400: CartErrorResponseSerializer,
            404: CartErrorResponseSerializer,
        },
        summary="아이템 수량 변경",
        description="장바구니 아이템의 수량을 변경합니다. 수량을 0으로 설정하면 삭제됩니다.",
        tags=["장바구니"],
    ),
    destroy=extend_schema(
        responses={
            204: None,
            404: CartErrorResponseSerializer,
        },
        summary="아이템 삭제",
        description="장바구니에서 아이템을 삭제합니다.",
        tags=["장바구니"],
    ),
)
class CartItemViewSet(viewsets.GenericViewSet):
    """
    장바구니 아이템 개별 관리 ViewSet

    RESTful하게 아이템을 관리하고 싶을 때 사용합니다.
    CartViewSet의 action들과 동일한 기능을 제공합니다.
    회원/비회원 모두 사용 가능합니다.
    """

    permission_classes = [permissions.AllowAny]  # 회원/비회원 모두 허용
    serializer_class = CartItemSerializer

    def get_queryset(self) -> Any:
        """
        현재 사용자/세션의 장바구니 아이템만 반환

        회원: user 기반 장바구니
        비회원: session_key 기반 장바구니
        """
        try:
            if self.request.user.is_authenticated:
                # 회원 장바구니
                cart = Cart.objects.get(user=self.request.user, is_active=True)
            else:
                # 비회원 장바구니
                session_key = self.request.session.session_key
                if not session_key:
                    return CartItem.objects.none()
                cart = Cart.objects.get(session_key=session_key, is_active=True)

            return cart.items.select_related("product").order_by("-added_at")
        except Cart.DoesNotExist:
            return CartItem.objects.none()

    def list(self, request: Request) -> Response:
        """장바구니 아이템 목록"""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request: Request) -> Response:
        """장바구니에 아이템 추가"""
        # 회원/비회원 구분하여 장바구니 가져오기
        if request.user.is_authenticated:
            cart, created = Cart.get_or_create_active_cart(user=request.user)
        else:
            session_key = request.session.session_key
            if not session_key:
                request.session.create()
                session_key = request.session.session_key
            cart, created = Cart.get_or_create_active_cart(session_key=session_key)

        serializer = CartItemCreateSerializer(data=request.data, context={"request": request, "cart": cart})

        if serializer.is_valid():
            cart_item = serializer.save()
            return Response(CartItemSerializer(cart_item).data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request: Request, pk: int | None = None) -> Response:
        """아이템 수량 변경"""
        try:
            cart_item = self.get_queryset().get(pk=pk)
        except CartItem.DoesNotExist:
            raise NotFound("장바구니 아이템을 찾을 수 없습니다.")

        serializer = CartItemUpdateSerializer(cart_item, data=request.data, partial=True)

        if serializer.is_valid():
            # quantity가 0이면 삭제됨
            if serializer.validated_data.get("quantity") == 0:
                cart_item.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)

            cart_item = serializer.save()
            return Response(CartItemSerializer(cart_item).data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request: Request, pk: int | None = None) -> Response:
        """아이템 삭제"""
        try:
            cart_item = self.get_queryset().get(pk=pk)
        except CartItem.DoesNotExist:
            raise NotFound("장바구니 아이템을 찾을 수 없습니다.")

        cart_item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
