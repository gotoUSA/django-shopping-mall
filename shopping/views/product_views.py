from django.db.models import Avg, Count, Q
from django.utils.text import slugify

from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

# 모델 import
from shopping.models.product import Category, Product, ProductReview

# Serializer import
from shopping.serializers import (
    CategorySerializer,
    CategoryTreeSerializer,
    ProductCreateUpdateSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductReviewSerializer,
)

# Swagger


class ProductPagination(PageNumberPagination):
    """
    상품 목록 페이지네이션 설정
    - 페이지당 12개 상품 표시 (기본값)
    -클라이언트가 page_size 파라미터로 조정 가능 (최대 100개)
    """

    page_size = 12  # 페이지당 기본 아이템수
    page_size_query_param = "page_size"  # 클라이언트가 페이지 크기를 조정할 수 있는 파라미터
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
    상품 CRUD 및 검색/필터링 ViewSet

    엔드포인트:
    - GET    /api/products/              - 상품 목록 조회
    - GET    /api/products/{id}/         - 상품 상세 조회
    - POST   /api/products/              - 상품 생성 (인증 필요)
    - PUT    /api/products/{id}/         - 상품 전체 수정 (판매자만)
    - PATCH  /api/products/{id}/         - 상품 부분 수정 (판매자만)
    - DELETE /api/products/{id}/         - 상품 삭제 (판매자만)
    - GET    /api/products/{id}/reviews/ - 리뷰 목록
    - POST   /api/products/{id}/add_review/ - 리뷰 작성
    - GET    /api/products/popular/      - 인기 상품
    - GET    /api/products/best_rating/  - 평점 높은 상품
    - GET    /api/products/low_stock/    - 재고 부족 상품

    검색/필터링 파라미터:
    - search: 검색어 (상품명, 설명, 카테고리명)
    - category: 카테고리 ID
    - min_price: 최소 가격
    - max_price: 최대 가격
    - in_stock: 재고 여부 (true/false)
    - seller: 판매자 ID
    - ordering: 정렬 (price, -price, created_at, -created_at, stock, name)
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
        액션별 Serializer 선택

        - list: ProductListSerializer (간단한 정보)
        - retrieve: ProductDetailSerializer (전체 정보)
        - create/update/partial_update: ProductCreateUpdateSerializer
        """
        if self.action == "list":
            return ProductListSerializer
        elif self.action == "retrieve":
            return ProductDetailSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return ProductCreateUpdateSerializer

        # 기본값은 목록용 Serializer
        return ProductListSerializer

    def get_queryset(self):
        """
        상품 쿼리셋 조회 및 필터링

        성능 최적화:
        - select_related: seller, category (JOIN 최적화)
        - prefetch_related: images, reviews (N+1 문제 방지)
        - annotate: avg_rating, review_cnt (집계)

        필터링:
        - category: 카테고리 및 하위 카테고리 포함
        - min_price, max_price: 가격 범위
        - in_stock: 재고 여부
        - seller: 판매자
        - is_active: 활성 상품만 (기본)
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
        POST /api/products/

        자동 처리:
        - seller: 현재 로그인한 사용자로 설정
        - slug: 상품명으로 자동 생성 (한글 지원)
        - slug 중복 시 숫자 추가 (예: product-1, product-2)
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
        PUT/PATCH /api/products/{id}/

        - name 변경 시 slug 자동 재생성
        - slug 중복 시 숫자 추가
        """

        # slug 변경시 중복 체크
        if "name" in serializer.validated_data and not serializer.validated_data.get("slug"):
            name = serializer.validated_data.get("name", "")
            slug = slugify(name, allow_unicode=True)

            # 현재 상품 제외하고 중복 체크
            existing = Product.objects.filter(slug=slug).exclude(pk=serializer.instance.pk)
            if existing.exists():
                base_slug = slug
                counter = 1
                while Product.objects.filter(slug=slug).exclude(pk=serializer.instance.pk).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1

            serializer.validated_data["slug"] = slug

        serializer.save()

    @action(detail=True, methods=["get"])
    def reviews(self, request, pk=None):
        """
        상품 리뷰 목록 조회
        GET /api/products/{id}/reviews/

        쿼리 파라미터:
        - ordering: 정렬 (created_at, -created_at, rating, -rating)
        - page: 페이지 번호

        권한: 누구나 조회 가능
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

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def add_review(self, request, pk=None):
        """
        상품 리뷰 작성
        POST /api/products/{id}/add_review/

        요청 본문:
        {
            "rating": 5,
            "comment": "좋은 상품입니다!"
        }

        권한: 인증 필요
        제약: 상품당 1개 리뷰만 작성 가능
        에러:
        - 400: 이미 리뷰 작성한 경우
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
        인기 상품 목록 조회
        GET /api/products/popular/

        정렬: 리뷰 많은 순
        개수: 최대 12개
        권한: 누구나 조회 가능
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

        조건: 리뷰 3개 이상인 상품만
        정렬: 평균 평점 높은 순
        개수: 최대 12개
        권한: 누구나 조회 가능
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
        재고 부족 상품 목록 조회 (판매자 전용)
        GET /api/products/low_stock/

        조건: 재고 10개 이하
        정렬: 재고 적은 순
        권한: 본인 상품만 조회 가능
        에러:
        - 401: 인증 필요
        """
        if not request.user.is_authenticated:
            return Response({"error": "로그인이 필요합니다."}, status=status.HTTP_401_UNAUTHORIZED)

        # 현재 사용자의 상품 중 재고가 10개 이하인 상품
        low_stock_products = self.get_queryset().filter(seller=request.user, stock__lte=10).order_by("stock")

        serializer = ProductListSerializer(low_stock_products, many=True)
        return Response(serializer.data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    카테고리 조회 전용 ViewSet (읽기 전용)

    엔드포인트:
    - GET /api/categories/             - 카테고리 목록
    - GET /api/categories/{id}/        - 카테고리 상세
    - GET /api/categories/tree/        - 계층 구조 조회
    - GET /api/categories/{id}/products/ - 카테고리별 상품 목록

    권한: 누구나 조회 가능
    """

    queryset = Category.objects.all()
    permission_classes = [permissions.AllowAny]  # 누구나 조회 가능

    def get_serializer_class(self):
        """
        액션별 Serializer 선택

        - tree: CategoryTreeSerializer (계층 구조)
        - 기본: CategorySerializer (일반 정보)
        """
        if self.action == "tree":
            return CategoryTreeSerializer
        return CategorySerializer

    def get_queryset(self):
        """
        카테고리 쿼리셋 조회

        - 활성 카테고리만 표시 (is_active=True)
        - select_related: parent (JOIN 최적화)
        - annotate: products_count (상품 개수 집계)
        """
        return (
            Category.objects.filter(is_active=True)
            .select_related("parent")
            .annotate(products_count=Count("products", filter=Q(products__is_active=True)))
        )

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """
        카테고리 계층 구조 조회
        GET /api/categories/tree/

        응답: 최상위부터 하위까지 재귀적 구조
        각 카테고리에 상품 개수 포함
        권한: 누구나 조회 가능
        """

        def build_tree(parent=None):
            """재귀적으로 카테고리 트리 구성"""
            categories = []
            for category in Category.objects.filter(parent=parent, is_active=True):
                cat_data = {
                    "id": category.id,
                    "name": category.name,
                    "slug": category.slug,
                    "product_count": Product.objects.filter(category=category, is_active=True).count(),
                    "children": build_tree(category),
                }
                categories.append(cat_data)
            return categories

        tree = build_tree()
        return Response(tree)

    @action(detail=True, methods=["get"])
    def products(self, request, pk=None):
        """
        카테고리별 상품 목록 조회
        GET /api/categories/{id}/products/

        특징:
        - 하위 카테고리 상품 포함 (MPTT 활용)
        - 페이지네이션 적용
        - 활성 상품만 표시

        권한: 누구나 조회 가능
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
