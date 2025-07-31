from django.urls import path, include
from rest_framework.routers import DefaultRouter

# ViewSet들을 나중에 import할 예정
# from .views import ProductViewSet, OrderViewSet, etc...

# DRF의 라우터 생성
router = DefaultRouter()

# 나중에 ViewSet들을 등록할 예정
# router.register(r'products', ProductViewSet, basename='product')
# router.register(r'orders', OrderViewSet, basename='order')
# router.register(r'categories', CategoryViewSet, basename='category')

# URL 패턴 정의
urlpatterns = [
    # API root - 라우터가 자동으로 생성하는 URL들
    path("", include(router.urls)),
    # 추가적인 커스텀 URL 패턴들을 여기에 정의
    # path('auth/', include('dj_rest_auth.urls')),  # 인증 관련 URL (나중에 추가)
    # path('cart/', CartView.as_view(), name='cart'),  # 장바구니 (나중에 추가)
]

# 현재는 빈 urlpatterns이지만, 에러를 방지하기 위해 기본 구조를 만들어둠
