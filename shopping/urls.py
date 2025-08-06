from django.urls import path, include
from rest_framework.routers import DefaultRouter

# ViewSet import
from shopping.views.product_views import ProductViewSet, CategoryViewSet
from shopping.views.cart_views import CartViewSet, CartItemViewSet

# DRF의 라우터 생성
router = DefaultRouter()

# ViewSet 등록
router.register(r"products", ProductViewSet, basename="product")
router.register(r"categories", CategoryViewSet, basename="category")

# Cart 관련 ViewSet 등록
# CartViewSet은 특별한 actions만 있으므로 수동 등록
router.register(r"cart-items", CartItemViewSet, basename="cart-item")
# URL 패턴 정의
urlpatterns = [
    # API root - 라우터가 자동으로 생성하는 URL들
    path("", include(router.urls)),
    # Cart 관련 커스텀 URLs (CartViewSet의 actions)
    path("cart/", CartViewSet.as_view({"get": "retrieve"}), name="cart-detail"),
    path("cart/summary/", CartViewSet.as_view({"get": "summary"}), name="cart-summary"),
    path(
        "cart/add_item/",
        CartViewSet.as_view({"post": "add_item"}),
        name="cart-add-item",
    ),
    path("cart/items/", CartViewSet.as_view({"get": "items"}), name="cart-items"),
    path(
        "cart/items/<int:pk>/",
        CartViewSet.as_view({"patch": "update_item", "delete": "delete_item"}),
        name="cart-item-detail",
    ),
    path("cart/clear/", CartViewSet.as_view({"post": "clear"}), name="cart-clear"),
    path(
        "cart/bulk_add/",
        CartViewSet.as_view({"post": "bulk_add"}),
        name="cart-bulk-add",
    ),
    path(
        "cart/check_stock/",
        CartViewSet.as_view({"get": "check_stock"}),
        name="cart-check-stock",
    ),
    # 추가적인 커스텀 URL 패턴들을 여기에 정의
    # path('auth/', include('dj_rest_auth.urls')),  # 인증 관련 URL (나중에 추가)
    # path('cart/', CartView.as_view(), name='cart'),  # 장바구니 (나중에 추가)
]

"""
생성되는 URL 패턴:

상품(Product) 관련:
- GET    /api/products/              - 상품 목록
- POST   /api/products/              - 상품 생성
- GET    /api/products/{id}/         - 상품 상세
- PUT    /api/products/{id}/         - 상품 전체 수정
- PATCH  /api/products/{id}/         - 상품 부분 수정
- DELETE /api/products/{id}/         - 상품 삭제
- GET    /api/products/{id}/reviews/ - 상품 리뷰 목록
- POST   /api/products/{id}/add_review/ - 리뷰 작성
- GET    /api/products/popular/      - 인기 상품
- GET    /api/products/best_rating/  - 평점 높은 상품
- GET    /api/products/low_stock/    - 재고 부족 상품

카테고리(Category) 관련:
- GET    /api/categories/            - 카테고리 목록
- GET    /api/categories/{id}/       - 카테고리 상세
- GET    /api/categories/tree/       - 카테고리 트리 구조
- GET    /api/categories/{id}/products/ - 카테고리별 상품

장바구니(Cart) 관련:
- GET    /api/cart/                  - 내 장바구니 전체 조회
- GET    /api/cart/summary/          - 장바구니 요약 정보
- POST   /api/cart/add_item/         - 장바구니에 상품 추가
- GET    /api/cart/items/            - 장바구니 아이템 목록
- PATCH  /api/cart/items/{id}/       - 아이템 수량 변경
- DELETE /api/cart/items/{id}/       - 아이템 삭제
- POST   /api/cart/clear/            - 장바구니 비우기
- POST   /api/cart/bulk_add/         - 여러 상품 한번에 추가
- GET    /api/cart/check_stock/      - 재고 확인

장바구니 아이템(CartItem) RESTful:
- GET    /api/cart-items/            - 아이템 목록
- POST   /api/cart-items/            - 아이템 추가
- PUT    /api/cart-items/{id}/       - 아이템 수정
- DELETE /api/cart-items/{id}/       - 아이템 삭제

검색 및 필터링 예시:
- /api/products/?search=노트북
- /api/products/?category=1&min_price=10000&max_price=50000
- /api/products/?ordering=-price
- /api/products/?in_stock=true
- /api/products/?seller=3
"""
