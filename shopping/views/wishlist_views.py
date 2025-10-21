from decimal import Decimal

from django.db.models import F, Q
from django.shortcuts import get_object_or_404

from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

# 모델 import
from shopping.models.product import Product

# Serializer import
from shopping.serializers.wishlist_serializers import (
    WishlistBulkAddSerializer,
    WishlistProductSerializer,
    WishlistStatsSerializer,
    WishlistToggleSerializer,
)


class WishlistViewSet(GenericViewSet):
    """
    찜하기 관리 ViewSet

    인증된 사용자만 사용 가능하며, 본인의 찜 목록만 조회/관리 가능합니다.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """현재 사용자의 찜한 상품 쿼리셋 반환"""
        return self.request.user.wishlist_products.select_related("category").prefetch_related("images")

    @action(detail=False, methods=["get"])
    def list(self, request):
        """
        찜 목록 조회
        GET /api/wishlist/

        쿼리 파라미터:
        - ordering: 정렬 (created_at, -created_at, price, -price, name)
        - is_available: 구매 가능한 상품만 필터링 (true/false)
        - on_sale: 세일 중인 상품만 필터링 (true/false)
        """
        queryset = self.get_queryset()

        # 필터링
        is_available = request.query_params.get("is_available")
        if is_available == "true":
            queryset = queryset.filter(stock__gt=0, is_active=True)
        elif is_available == "false":
            queryset = queryset.filter(Q(stock=0) | Q(is_active=False))

        on_sale = request.query_params.get("on_sale")
        if on_sale == "true":
            queryset = queryset.filter(compare_price__isnull=False, compare_price__gt=F("price"))

        # 정렬
        ordering = request.query_params.get("ordering", "-created_at")
        valid_orderings = ["created_at", "-created_at", "price", "-price", "name"]
        if ordering in valid_orderings:
            queryset = queryset.order_by(ordering)

        serializer = WishlistProductSerializer(queryset, many=True)

        return Response({"count": queryset.count(), "results": serializer.data})

    @action(detail=False, methods=["post"])
    def toggle(self, request):
        """
        찜하기 토글 (추가/제거)
        POST /api/wishlist/toggle/

        요청 본문:
        {
            "product_id": 1
        }

        응답:
        {
            "is_wished": true,  // 현재 찜 상태
            "message": "찜 목록에 추가되었습니다.",
            "wishlist_count": 123  // 이 상품의 전체 찜 개수
        }
        """
        serializer = WishlistToggleSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product_id = serializer.validated_data["product_id"]
        product = get_object_or_404(Product, id=product_id)
        user = request.user

        # 토글 처리
        if user.is_in_wishlist(product):
            user.remove_from_wishlist(product)
            is_wished = False
            message = "찜 목록에서 제거되었습니다."
        else:
            user.add_to_wishlist(product)
            is_wished = True
            message = "찜 목록에 추가되었습니다."

        # 이 상품의 전체 찜 개수
        wishlist_count = product.wished_by_users.count()

        return Response(
            {
                "is_wished": is_wished,
                "message": message,
                "wishlist_count": wishlist_count,
            }
        )

    @action(detail=False, methods=["post"])
    def add(self, request):
        """
        찜 목록에 추가만 하기 (이미 있으면 무시)
        POST /api/wishlist/add/

        요청 본문:
        {
            "product_id": 1
        }
        """
        serializer = WishlistToggleSerializer(data=request.data)

        if not serializer.is_valid():
            if "product_id" in serializer.errors:
                return Response(
                    {"error": str(serializer.errors["product_id"][0])},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product_id = serializer.validated_data["product_id"]
        product = get_object_or_404(Product, id=product_id)
        user = request.user

        if user.is_in_wishlist(product):
            return Response(
                {"message": "이미 찜한 상품입니다.", "is_wished": True},
                status=status.HTTP_200_OK,
            )

        user.add_to_wishlist(product)

        return Response(
            {
                "message": "찜 목록에 추가되었습니다.",
                "is_wished": True,
                "wishlist_count": product.wished_by_users.count(),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["delete"])
    def remove(self, request):
        """
        찜 목록에서 제거
        DELETE /api/wishlist/remove/?product_id=1
        """
        product_id = request.query_params.get("product_id")

        if not product_id:
            return Response(
                {"error": "product_id가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = get_object_or_404(Product, id=product_id)
        user = request.user

        if not user.is_in_wishlist(product):
            return Response(
                {"message": "찜 목록에 없는 상품입니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.remove_from_wishlist(product)

        return Response(
            {"message": "찜 목록에서 제거되었습니다."},
            status=status.HTTP_204_NO_CONTENT,
        )

    @action(detail=False, methods=["post"])
    def bulk_add(self, request):
        """
        여러 상품 한번에 찜하기
        POST /api/wishlist/bulk_add/

        요청 본문:
        {
            "product_ids": [1, 2, 3]
        }

        장바구니에서 여러 상품을 한번에 찜할 때 유용합니다.
        """
        serializer = WishlistBulkAddSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product_ids = serializer.validated_data["product_ids"]
        user = request.user

        # 현재 찜한 상품들
        current_wishlist = set(user.wishlist_products.values_list("id", flat=True))

        # 추가할 상품들
        products_to_add = []
        skipped = 0

        for pid in product_ids:
            if pid in current_wishlist:
                skipped += 1
            else:
                products_to_add.append(pid)

        # 새 상품들 추가
        if products_to_add:
            products = Product.objects.filter(id__in=products_to_add)
            user.wishlist_products.add(*products)
            added_count = products.count()
        else:
            added_count = 0

        return Response(
            {
                "message": f"{added_count}개 상품이 찜 목록에 추가되었습니다.",
                "added_count": added_count,
                "skipped_count": skipped,  # 이미 찜한 상품 수
                "total_wishlist_count": user.get_wishlist_count(),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["delete"])
    def clear(self, request):
        """
        찜 목록 전체 삭제
        DELETE /api/wishlist/clear/

        쿼리 파라미터:
        - confirm: true (실수 방지)
        """
        confirm = request.query_params.get("confirm")

        if confirm != "true":
            return Response(
                {"error": "찜 목록 전체 삭제를 확인하려면 confirm=True를 추가하세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        count = request.user.get_wishlist_count()
        request.user.clear_wishlist()

        return Response(
            {"message": f"{count}개의 상품이 찜 목록에서 삭제되었습니다."},
            status=status.HTTP_204_NO_CONTENT,
        )

    @action(detail=False, methods=["get"])
    def check(self, request):
        """
        특정 상품의 찜 상태 확인
        GET /api/wishlist/check/?product_id=1
        """
        product_id = request.query_params.get("product_id")

        if not product_id:
            return Response(
                {"error": "product_id가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = get_object_or_404(Product, id=product_id)

        return Response(
            {
                "product_id": product.id,
                "is_wished": request.user.is_in_wishlist(product),
                "wishlist_count": product.wished_by_users.count(),
            }
        )

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """
        내 찜 목록 통계
        GET /api/wishlist/stats/

        응답:
        {
            "total_count": 10,  // 전체 찜한 상품 수
            "available_count": 8,  // 구매 가능한 상품 수
            "out_of_stock_count": 2,  // 품절 상품 수
            "on_sale_count": 3,  // 세일 중인 상품 수
            "total_price": 500000,  // 정가 총합
            "total_sale_price": 450000,  // 실제 가격 총합
            "total_discount": 50000  // 총 할인 금액
        }
        """
        user = request.user
        products = user.wishlist_products.all()

        # 기본 통계
        total_count = products.count()
        available_count = products.filter(stock__gt=0, is_active=True).count()
        out_of_stock_count = products.filter(Q(stock=0) | Q(is_active=False)).count()

        # 가격 통계
        on_sale_count = 0
        total_price = Decimal("0")
        total_sale_price = Decimal("0")
        total_discount = Decimal("0")

        for product in products:
            # 세일 상품 체크
            if product.compare_price and product.compare_price > product.price:
                on_sale_count += 1
                # 세일 상품인 경우
                total_price += product.compare_price  # 원가 합계
                total_sale_price += product.price  # 할인가 합계
                total_discount += product.compare_price - product.price  # 할인액
            else:
                # 일반 상품인 경우
                total_price += product.price
                total_sale_price += product.price

        stats = {
            "total_count": total_count,
            "available_count": available_count,
            "out_of_stock_count": out_of_stock_count,
            "on_sale_count": on_sale_count,
            "total_price": total_price,
            "total_sale_price": total_sale_price,
            "total_discount": total_discount,
        }

        serializer = WishlistStatsSerializer(stats)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def move_to_cart(self, request):
        """
        찜 목록에서 장바구니로 이동
        POST /api/wishlist/move_to_cart/

        요청 본문:
        {
            "product_ids": [1, 2, 3],  // 이동할 상품 ID들
            "remove_from_wishlist": true  // 찜 목록에서 제거 여부 (기본: false)
        }
        """
        try:
            from shopping.models.cart import Cart, CartItem
        except ImportError:
            return Response(
                {"error": "장바구니 기능이 아직 구현되지 않았습니다."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        products_ids = request.data.get("product_ids", [])
        remove_from_wishlist = request.data.get("remove_from_wishlist", False)

        if not products_ids:
            return Response({"error": "상품을 선택해주세요."}, status=status.HTTP_400_BAD_REQUEST)

        # Boolean으로 명시적 변환
        if isinstance(remove_from_wishlist, str):
            remove_from_wishlist = remove_from_wishlist.lower() in ["true", "1", "yes"]
        else:
            remove_from_wishlist = bool(remove_from_wishlist)

        # 찜 목록에 있는 상품만 필터링
        products = request.user.wishlist_products.filter(id__in=products_ids)

        if not products.exists():
            # 왜 못 찾는지 상세 정보 반환
            user_wishlist_ids = list(request.user.wishlist_products.values_list("id", flat=True))
            return Response(
                {
                    "error": "찜 목록에 해당 상품이 없습니다.",
                    "requested_ids": products_ids,
                    "user_wishlist_ids": user_wishlist_ids,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        # 장바구니 가져오기 또는 생성
        cart, _ = Cart.get_or_create_active_cart(request.user)

        added_items = []
        already_in_cart = []
        out_of_stock = []

        for product in products:
            # 재고 확인
            if product.stock <= 0:
                out_of_stock.append(product.name)
                continue

            # 장바구니에 추가
            cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": 1})

            if created:
                added_items.append(product.name)
            else:
                already_in_cart.append(product.name)

        # 찜 목록에서 제거 옵션
        if remove_from_wishlist and added_items:
            moved_products = Product.objects.filter(name__in=added_items)
            request.user.wishlist_products.remove(*moved_products)

        # 응답 메시지 생성
        message_parts = []
        if added_items:
            message_parts.append(f"{len(added_items)}개 상품이 장바구니에 추가되었습니다.")
        if already_in_cart:
            message_parts.append(f"{len(already_in_cart)}개 상품은 이미 장바구니에 있습니다.")
        if out_of_stock:
            message_parts.append(f"{len(out_of_stock)}개 상품은 품절입니다.")

        return Response(
            {
                "message": (" ".join(message_parts) if message_parts else "처리할 상품이 없습니다."),
                "added_items": added_items,
                "already_in_cart": already_in_cart,
                "out_of_stock": out_of_stock,
            },
            status=status.HTTP_200_OK,
        )
