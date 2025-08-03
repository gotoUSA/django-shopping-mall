from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils.text import slugify

# 모델 import
from shopping.models.product import Product, Category, ProductImage, ProductReview
from shopping.models.user import User

# Serializer import
from shopping.serializers import (
    ProductCreateUpdateSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductReviewSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
)


class ProductPagination(PageNumberPagination):
    """
    상품 목록 페이지네이션 설정
    - 페이지당 12개 상품 표시 (기본값)
    -클라이언트가 page_size 파라미터로 조정 가능 (최대 100개)
    """

    page_size = 12  # 페이지당 기본 아이템수
    page_size_query_param = (
        "page_size"  # 클라이언트가 페이지 크기를 조정할 수 있는 파라미터
    )
    max_page_size = 100  # 최대 페이지 크기 제한


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    객체 수준 권한 설정
    - 누구나 읽기 가능
    - 수정/삭제는 소유자(판매자)만 가능
    """

    def has_object_permission(self, request, view, obj):
        # 읽기 권한은 모두에게 허용
        if request.method in permissions.SAFE_METHODS:
            return True

        # 쓰기 권한은 소유자에게만 허용
        # seller가 None인 경우도 고려 (legacy 데이터)
        return obj.seller == request.user if obj.seller else False


class ProductViewSet(viewsets.ModelViewSet):
    """
    상품 CRUD 및 검색/필터링 기능을 제공하는 ViewSet

    지원 기능:
    - 목록 조회 (GET /api/products/)
    - 상세 조회 (GET /api/products/{id})
    - 생성 (POST /api/product/) - 인증 필요
    - 수정 (PUT/PATCH /api/products/{id}/) - 판매자만
    - 삭제 (DELELTE /api/products/{id}/) - 판매자만
    - 검색 (GET /api/products/?search=검색어)
    - 필터링 (GET /api/products/?category=1&min_price=10000)
    - 정렬 (GET /api/products/?ordering=-created_at)
    """

    queryset = Product.objects.all()
    pagination_class = ProductPagination
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    # 검색 필드 설정
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "name",
        "description",
        "category__name",
    ]  # 상품명, 설명, 카테고리명으로 검색

    # 정렬 필드 설정
    ordering_fields = [
        "price",
        "created_at",
        "stock",
        "name",
    ]  # 가격, 등록일, 재고, 이름순 정렬
    ordering = ["-created_at"]  # 기본 정렬: 최신순

    def get_serializer_class(self):
        """
        액션에 따라 다른 Serializer 사용
        - tree 액션: CategoryTreeSerializer
        - 기본: CategorySerializer
        """
        if self.action == "tree":
            return CategoryTreeSerializer
        return CategorySerializer

    def get_queryset(self):
        """
        쿼리셋 최적화 및 필터링
        - select_related: seller, category (1:1, N:1 관계)
        - prefetch_related: images, reviews (1:N 관계)
        - 활성 상품만 표시 (is_active=True)
        """
        queryset = (
            Product.objects.filter(is_active=True)
            .select_related("seller", "category")
            .prefetch_related("images", "reviews")
            .annotate(
                # 평균 평점과 리뷰 수를 미리 계산
                avg_rating=Avg("reviews__rating"),
                review_cnt=Count("reviews"),
            )
        )

        # 카테고리 필터링
        category_id = self.request.query_params.get("category", None)
        if category_id:
            try:
                # 하위 카테고리도 포함하여 필터링
                category = Category.objects.get(pk=category_id)
                # 현재 카테고리와 모든 하위 카테고리의 상품 조회
                categories = category.get_descendants(include_self=True)
                queryset = queryset.filter(category__in=categories)
            except Category.DoesNotExist:
                pass

        # 가격 범위 필터링
        min_price = self.request.query_params.get("min_price", None)
        max_price = self.request.query_params.get("max_price", None)

        if min_price:
            try:
                queryset = queryset.filter(price__gte=int(min_price))
            except ValueError:
                pass

        if max_price:
            try:
                queryset = queryset.filter(price__lte=int(max_price))
            except ValueError:
                pass

        # 재고 상태 필터링
        in_stock = self.request.query_params.get("in_stock", None)
        if in_stock is not None:
            if in_stock.lower() == "true":
                queryset = queryset.filter(stock__gt=0)
            elif in_stock.lower() == "false":
                queryset = queryset.filter(stock=0)

        # 판매자 필터링
        seller_id = self.request.query_params.get("seller", None)
        if seller_id:
            queryset = queryset.filter(seller_id=seller_id)

        return queryset

    def perform_create(self, serializer):
        """
        상품 생성 시 추가 처리
        - 현재 로그인한 사용자를 판매자로 설정
        - slug 자동 생성 (한글 상품명 지원)
        """
        # slug가 없으면 상품명으로 생성
        if not serializer.validated_data.get("slug"):
            name = serializer.validated_data.get("name", "")
            # 한굴 slug 지원을 위해 allow_unicode=True
            slug = slugify(name, allow_unicode=True)

            # 중복 방지: 같은 slug가 있으면 숫자 추가
            base_slug = slug
            counter = 1
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            serializer.validated_data["slug"] = slug

        # 현재 사용자를 판매자로 설정
        serializer.save(seller=self.request.user)

    def perform_update(self, serializer):
        """
        상품 수정 시 추가 처리
        - slug 업데이트 시 중복 체크
        """

        # slug 변경시 중복 체크
        if "name" in serializer.validated_data and not serializer.validated_data.get(
            "slug"
        ):
            name = serializer.validated_data.get("name", "")
            slug = slugify(name, allow_unicode=True)

            # 현재 상품 제외하고 중복 체크
            existing = Product.objects.filter(slug=slug).exclude(
                pk=serializer.instance.pk
            )
            if existing.exists():
                base_slug = slug
                counter = 1
                while (
                    Product.objects.filter(slug=slug)
                    .exclude(pk=serializer.instance.pk)
                    .exists()
                ):
                    slug = f"{base_slug}-{counter}"
                    counter += 1

            serializer.validated_data["slug"] = slug

        serializer.save()

    @action(detail=True, methods=["get"])
    def reviews(self, request, pk=None):
        """
        특정 상품의 리뷰 목록 조회
        GET /api/products/{id}/reviews/

        쿼리 파라미터:
        - ordering: created_at, -created_at, rating, -raing
        - page: 페이지 번호
        """
        product = self.get_object()
        reviews = product.reviews.all().select_related("user")

        # 정렬
        ordering = request.query_params.get("ordering", "-created_at")
        if ordering in ["created_at", "-created_at", "rating", "-rating"]:
            reviews = reviews.order_by(ordering)

        # 페이지네이션 적용
        page = self.paginate_queryset(reviews)
        if page is not None:
            serializer = ProductReviewSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductReviewSerializer(reviews, many=True)
        return Response(serializer.data)

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def add_review(self, request, pk=None):
        """
        상품 리뷰 작성
        POST /api/products/{id}/add_review/

        요청 본문:
        {
            "rating": 5,
            "comment": "좋은 상품입니다!"
        }
        """
        product = self.get_object()

        # 이미 리뷰를 작성했는지 확인
        if ProductReview.objects.filter(product=product, user=request.user).exists():
            return Response(
                {"error": "이미 이 상품에 대한 리뷰를 작성하셨습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 리뷰 생성
        serializer = ProductReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user, product=product)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def popular(self, request):
        """
        인기 상품 목록 조회 (리뷰가 많은 순)
        GET /api/products/popular/
        """
        popular_products = (
            self.get_queryset()
            .annotate(review_count=Count("review"))
            .filter(review_count__gt=0)
            .order_by("-review_count")[:12]
        )

        serializer = ProductListSerializer(popular_products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def best_rating(self, request):
        """
        평점 높은 상품 목록 조회
        GET /api/products/best_rating/
        """
        best_products = (
            self.get_queryset()
            .annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews"))
            .filter(review_count__gte=3)  # 최소 3개 이상의 리뷰가 있는 상품만
            .order_by("-avg_rating")[:12]
        )

        serializer = ProductListSerializer(best_products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def low_stock(self, request):
        """
        재고 부족 상품 목록 (판매자 전용)
        GET /api/products/low_stock/
        """
        if not request.user.is_authenticated:
            return Response(
                {"error": "로그인이 필요합니다."}, status=status.HTTP_401_UNAUTHORIZED
            )

        # 현재 사용자의 상품 중 재고가 10개 이하인 상품
        low_stock_products = (
            self.get_queryset()
            .filter(seller=request.user, stock__lte=10)
            .order_by("stock")
        )

        serializer = ProductListSerializer(low_stock_products, many=True)
        return Response(serializer.data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    카테고리 조회 전용 ViewSet
    - 목록 조회: GET /api/categories/
    - 상세 조회: GET /api/categories/{id}
    - 계층 구조 조회: GET /api/categories/tree/
    """

    queryset = Category.objects.all()
    permission_classes = [permissions.AllowAny]  # 누구나 조호 ㅣ가능

    def get_serializer_class(self):
        """
        기본적으로 CategorySerializer 사용
        (CategorySerializer는 별도로 작성 필요)
        """
        # 임시로 기본 ModelSerializer 반환
        from rest_framework import serializers

        class CategorySerializer(serializers.ModelSerializer):
            """카테고리 기본 Serializer"""

            parent_id = serializers.IntegerField(
                source="parent.id", read_only=True, allouw_null=True
            )
            parent_name = serializers.CharField(source="parent.name", read_only=True)
            product_count = serializers.IntegerField(read_only=True)

            class Meta:
                model = Category
                fields = [
                    "id",
                    "name",
                    "slug",
                    "parent",
                    "parent_id",
                    "parent_name",
                    "is_active",
                    "product_count",
                    "created_at",
                ]

        return CategorySerializer

    def get_queryset(self):
        """
        활성 카테고리만 조회하고 상품 수 포함
        """
        return (
            Category.objects.filter(is_active=True)
            .select_related("parent")
            .annotate(product_count=Count("product", filter=Q(product__is_active=True)))
        )

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """
        카테고리 트리 구조 조회
        GET /api/categories/tree/

        최상위 카테고리부터 계층적으로 표시
        """

        def build_tree(parent=None):
            """재귀적으로 카테고리 트리 구성"""
            categories = []
            for category in Category.objects.filter(parent=parent, is_active=True):
                cat_data = {
                    "id": category.id,
                    "name": category.name,
                    "slug": category.slug,
                    "product_count": Product.objects.filter(
                        category=category, is_active=True
                    ).count(),
                    "children": build_tree(category),
                }
                categories.append(cat_data)
            return categories

        tree = build_tree()
        return Response(tree)

    @action(detail=True, methods=["get"])
    def products(self, request, pk=None):
        """
        특정 카테고리의 상품 목록 조회
        GET /api/categories/{id}/products/

        하위 카테고리의 상품도 포함
        """
        category = self.get_object()

        # 현재 카테고리와 모든 하위 카테고리 가져오기
        categories = category.get_descendants(include_self=True)

        # 해당 카테고리들의 상품 조회
        products = (
            Product.objects.filter(category__in=categories, is_active=True)
            .select_related("seller", "category")
            .prefetch_related("images")
        )

        # ProductViewSet의 필터링 로직 재사용
        # 페이지네이션 적용
        paginator = ProductPagination()
        page = paginator.paginate_queryset(products, request)

        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)
