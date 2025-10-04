"""
shopping/serializers/__init__.py

Serializer 모듈의 진입점입니다.
모든 Serializer를 여기서 import하여 다른 모듈에서 쉽게 사용할 수 있도록 합니다.

사용 예시:
    from shopping.serializers import ProductListSerializer, CategorySerializer
    
    # 또는 전체 import
    from shopping.serializers import *
"""

"""
Shopping 앱의 모든 Serializer를 한 곳에서 import할 수 있도록 설정
실제 grep 결과를 바탕으로 작성된 정확한 버전
"""

# User 관련 Serializers
from .user_serializers import (
    UserSerializer,
    RegisterSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    TokenResponseSerializer,
)

# Product 관련 Serializers
from .product_serializers import (
    ProductListSerializer,
    ProductImageSerializer,
    ProductReviewSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
)

# Category 관련 Serializers
from .category_serializers import (
    CategorySerializer,
    CategoryTreeSerializer,
    CategoryCreateUpdateSerializer,
    SimpleCategorySerializer,
)

# Cart 관련 Serializers
from .cart_serializers import (
    CartItemSerializer,
    CartItemCreateSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
    SimpleCartSerializer,
    CartClearSerializer,
)

# Order 관련 Serializers
from .order_serializers import (
    OrderItemSerializer,
    OrderListSerializer,
    OrderDetailSerializer,
    OrderCreateSerializer,
)

# Payment 관련 Serializers
from .payment_serializers import (
    PaymentSerializer,
    PaymentRequestSerializer,
    PaymentConfirmSerializer,
    PaymentCancelSerializer,
    PaymentLogSerializer,
    PaymentWebhookSerializer,
)

# Wishlist 관련 Serializers
from .wishlist_serializers import (
    WishlistProductSerializer,
    WishlistToggleSerializer,
    WishlistBulkAddSerializer,
    WishlistStatusSerializer,
    WishlistStatsSerializer,
)

# 외부에서 사용할 수 있도록 __all__ 정의
__all__ = [
    # User
    "UserSerializer",
    "RegisterSerializer",
    "LoginSerializer",
    "PasswordChangeSerializer",
    "TokenResponseSerializer",
    # Product
    "ProductListSerializer",
    "ProductImageSerializer",
    "ProductReviewSerializer",
    "ProductDetailSerializer",
    "ProductCreateUpdateSerializer",
    # Category
    "CategorySerializer",
    "CategoryTreeSerializer",
    "CategoryCreateUpdateSerializer",
    "SimpleCategorySerializer",
    # Cart
    "CartItemSerializer",
    "CartItemCreateSerializer",
    "CartItemUpdateSerializer",
    "CartSerializer",
    "SimpleCartSerializer",
    "CartClearSerializer",
    # Order
    "OrderItemSerializer",
    "OrderListSerializer",
    "OrderDetailSerializer",
    "OrderCreateSerializer",
    # Payment
    "PaymentSerializer",
    "PaymentRequestSerializer",
    "PaymentConfirmSerializer",
    "PaymentCancelSerializer",
    "PaymentLogSerializer",
    "PaymentWebhookSerializer",
    # Wishlist
    "WishlistProductSerializer",
    "WishlistToggleSerializer",
    "WishlistBulkAddSerializer",
    "WishlistStatusSerializer",
    "WishlistStatsSerializer",
]
