"""
shopping/serializers/__init__.py

Serializer 모듈의 진입점입니다.
모든 Serializer를 여기서 import하여 다른 모듈에서 쉽게 사용할 수 있도록 합니다.

사용 예시:
    from shopping.serializers import ProductListSerializer, CategorySerializer
    
    # 또는 전체 import
    from shopping.serializers import *
"""

# Product 관련 Serializers
from .product_serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ProductImageSerializer,
    ProductReviewSerializer,
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
    CartSerializer,
    CartItemSerializer,
    CartItemCreateSerializer,
    CartItemUpdateSerializer,
    SimpleCartSerializer,
    CartClearSerializer,
)

# Order 관련 Serializers (아직 구현 전)
# from .order_serializers import (
#     OrderSerializer,
#     OrderItemSerializer,
#     OrderCreateSerializer,
#     OrderDetailSerializer,
# )

# User 관련 Serializers (아직 구현 전)
# from .user_serializers import (
#     UserSerializer,
#     UserRegistrationSerializer,
#     UserProfileSerializer,
#     UserUpdateSerializer,
# )

# 외부에서 사용 가능한 모든 Serializer 목록
__all__ = [
    # Product
    "ProductListSerializer",
    "ProductDetailSerializer",
    "ProductCreateUpdateSerializer",
    "ProductImageSerializer",
    "ProductReviewSerializer",
    # Category
    "CategorySerializer",
    "CategoryTreeSerializer",
    "CategoryCreateUpdateSerializer",
    "SimpleCategorySerializer",
    # Cart
    "CartSerializer",
    "CartItemSerializer",
    "CartItemCreateSerializer",
    "CartItemUpdateSerializer",
    "SimpleCartSerializer",
    "CartClearSerializer",
    # Order (추후 추가)
    # 'OrderSerializer',
    # 'OrderItemSerializer',
    # 'OrderCreateSerializer',
    # 'OrderDetailSerializer',
    # User (추후 추가)
    # 'UserSerializer',
    # 'UserRegistrationSerializer',
    # 'UserProfileSerializer',
    # 'UserUpdateSerializer',
]
