from django.urls import path, include
from rest_framework.routers import DefaultRouter

# ViewSet import
from shopping.views.product_views import ProductViewSet, CategoryViewSet

# DRF의 라우터 생성
router = DefaultRouter()

# ViewSet 등록
router.register(r"products", ProductViewSet, basename="product")
router.register(r"categories", CategoryViewSet, basename="category")

# URL 패턴 정의
urlpatterns = [
    # API root - 라우터가 자동으로 생성하는 URL들
    path("", include(router.urls)),
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

검색 및 필터링 예시:
- /api/products/?search=노트북
- /api/products/?category=1&min_price=10000&max_price=50000
- /api/products/?ordering=-price
- /api/products/?in_stock=true
- /api/products/?seller=3
"""
