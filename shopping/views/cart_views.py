from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, ValidationError
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Prefetch, F

# 모델 import
from shopping.models.cart import Cart, CartItem
from shopping.models.product import Product

# Serializer import
from shopping.serializers import (
    CartSerializer,
    CartItemSerializer,
    CartItemCreateSerializer,
    CartItemUpdateSerializer,
    SimpleCartSerializer,
    CartClearSerializer,
)


class CartViewSet(viewsets.GenericViewSet):
    """
    장바구니 관리 ViewSet

    사용자별로 하나의 활성 장바구니를 관리합니다.
    인증된 사용자만 사용 가능합니다.

    엔드포인트:
    - GET    /api/cart/            - 내 장바구니 조회
    - GET    /api/cart/summary/    - 장바구니 요약 정보
    - POST   /api/cart/add_item/   - 상품 추가
    - GET    /api/cart/items/      - 장바구니 아이템 목록
    - PATCH  /api/cart/items/{id}/ - 아이템 수량 변경
    - DELETE /api/cart/items/{id}/ - 아이템 삭제
    - POST   /api/cart/clear/      - 장바구니 비우기
    """

    permission_classes = [permissions.IsAuthenticated]  # 로그인 필수
    queryset = Cart.objects.none()

    def get_serializer_class(self):
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

    def get_cart(self):
        """
        현재 사용자의 활성 장바구니를 가져오거나 생성

        Returns:
            cart: 사용자의 활성 장바구니
        """
        # get_or_create_active_cart 메서드 사용 (모델에 정의됨)
        cart, created = Cart.get_or_create_active_cart(self.request.user)

        # 성능 최적화: 관련 데이터 미리 로드
        # select_related: 1:1, N:1 관계 (user)
        # prefetch_related: 1:N 관계 (items와 각 item의 product)
        cart = Cart.objects.prefetch_related(
            Prefetch(
                "items",
                queryset=CartItem.objects.select_related("product").order_by(
                    "-added_at"
                ),  # 최근 추가된 순서로
            )
        ).get(pk=cart.pk)

        return cart

    def retrieve(self, request):
        """
        내 장바구니 전체 정보 조회
        GET /api/cart/

        Returns:
            장바구니의 모든 정보 (아이템, 총액, 수량 등)
        """
        cart = self.get_cart()
        serializer = self.get_serializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        장바구니 요약 정보 조회
        GET /api/cart/summary/

        헤더나 사이드바에서 사용할 간단한 정보만 반환

        Returns:
            총액, 총 수량, 아이템 종류 수
        """
        cart = self.get_cart()
        serializer = self.get_serializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def add_item(self, request):
        """
        장바구니에 상품 추가
        POST /api/cart/add_item/

        요청 본문:
        {
            "product_id": 1,
            "quantity": 2
        }

        이미 담긴 상품이면 수량만 증가됩니다.
        """
        cart = self.get_cart()

        # Serializer에 cart 정보를 context로 전달
        serializer = self.get_serializer(
            data=request.data, context={"request": request, "cart": cart}
        )

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

    @action(detail=False, methods=["get"])
    def items(self, request):
        """
        장바구니 아이템 목록 조회
        GET /api/cart/items/

        장바구니의 아이템만 별도로 조회할 때 사용
        """
        cart = self.get_cart()
        items = cart.items.select_related("product").order_by("-added_at")
        serializer = CartItemSerializer(items, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="items")
    def update_item(self, request, pk=None):
        """
        장바구니 아이템 수량 변경
        PATCH /api/cart/items/{id}/

        요청 본문:
        {
            "quantity": 3
        }

        quantity가 0이면 아이템이 삭제됩니다.
        """
        cart = self.get_cart()

        # 해당 아이템이 현재 사용자의 장바구니에 있는지 확인
        try:
            cart_item = cart.items.get(pk=pk)
        except CartItem.DoesNotExist:
            raise NotFound("장바구니에 해당 상품이 없습니다.")

        serializer = self.get_serializer(
            cart_item, data=request.data, partial=True  # PATCH 요청이므로 부분 업데이트
        )

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

    @action(detail=True, methods=["delete"], url_path="items")
    def delete_item(self, request, pk=None):
        """
        장바구니 아이템 삭제
        DELETE /api/cart/items/{id}/

        장바구니에서 특정 상품을 완전히 제거합니다.
        """
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

    @action(detail=False, methods=["post"])
    def clear(self, request):
        """
        장바구니 비우기
        POST /api/cart/clear/

        요청 본문:
        {
            "confirm": true
        }

        실수 방지를 위해 confirm 값을 요구합니다.
        """
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

    @action(detail=False, methods=["post"])
    def bulk_add(self, request):
        """
        여러 상품을 한 번에 장바구니에 추가
        POST /api/cart/bulk_add/

        요청 본문:
        {
            "items": [
                {"product_id": 1, "quantity": 2},
                {"product_id": 3, "quantity": 1}
                ]
        }

        찜 목록에서 여러 상품을 한 번에 담을 때 유용합니다.
        """
        cart = self.get_cart()
        items_data = request.data.get("items", [])

        if not items_data:
            return Response(
                {"error": "추가할 상품 정보가 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        added_items = []
        errors = []

        # 트랜잭션으로 전체 처리
        with transaction.atomic():
            for idx, items_data in enumerate(items_data):
                serializer = CartItemCreateSerializer(
                    data=items_data, context={"request": request, "cart": cart}
                )

                if serializer.is_valid():
                    cart_item = serializer.save()
                    added_items.append(cart_item)
                else:
                    # 에러 정보 수집
                    errors.append(
                        {
                            "index": idx,
                            "product_id": items_data.get("product_id"),
                            "errors": serializer.errors,
                        }
                    )

        # 응답 생성
        response_data = {
            "message": f"{len(added_items)}개의 상품이 추가되었습니다.",
            "added_items": CartItemSerializer(added_items, many=True).data,
        }

        if errors:
            response_data["errors"] = errors
            return Response(response_data, status=status.HTTP_207_MULTI_STATUS)

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def check_stock(self, request):
        """
        장바구니 상품들의 재고 확인
        GET /api/cart/check_stock/

        주문 직전에 재고를 다시 확인할 때 사용합니다.
        """
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


class CartItemViewSet(viewsets.GenericViewSet):
    """
    장바구니 아이템 개별 관리 ViewSet

    RESTful하게 아이템을 관리하고 싶을 때 사용합니다.
    CartViewSet의 action들과 동일한 기능을 제공합니다.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CartItemSerializer

    def get_queryset(self):
        """
        현재 사용자의 장바구니 아이템만 반환
        """
        # 사용자의 활성 장바구니 찾기
        try:
            cart = Cart.objects.get(user=self.request.user, is_active=True)
            return cart.items.select_related("product").order_by("-added_at")
        except Cart.DoesNotExist:
            return CartItem.objects.none()

    def list(self, request):
        """
        장바구니 아이템 목록
        GET /api/cart-items/
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request):
        """
        장바구니에 아이템 추가
        POST /api/cart-items/
        """
        cart, created = Cart.get_or_create_active_cart(request.user)

        serializer = CartItemCreateSerializer(
            data=request.data, context={"request": request, "cart": cart}
        )

        if serializer.is_valid():
            cart_item = serializer.save()
            return Response(
                CartItemSerializer(cart_item).data, status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        """
        아이템 수량 변경
        PUT /api/cart-items/{id}/
        """
        try:
            cart_item = self.get_queryset().get(pk=pk)
        except CartItem.DoesNotExist:
            raise NotFound("장바구니 아이템을 찾을 수 없습니다.")

        serializer = CartItemUpdateSerializer(
            cart_item, data=request.data, partial=True
        )

        if serializer.is_valid():
            # quantity가 0이면 삭제됨
            if serializer.validated_data.get("quantity") == 0:
                cart_item.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)

            cart_item = serializer.save()
            return Response(CartItemSerializer(cart_item).data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        """
        아이템 삭제
        DELETE /api/cart-items/{id}/
        """
        try:
            cart_item = self.get_queryset().get(pk=pk)
        except CartItem.DoesNotExist:
            raise NotFound("장바구니 아이템을 찾을 수 없습니다.")

        cart_item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
