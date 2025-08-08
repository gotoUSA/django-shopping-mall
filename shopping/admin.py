from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.db.models import Count, Avg
from mptt.admin import DraggableMPTTAdmin

from .models import (
    Product,
    Category,
    ProductImage,
    ProductReview,
    Order,
    OrderItem,
    User,
    Cart,
    CartItem,
)


# User Admin
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    사용자 관리자 페이지 설정
    """

    list_display = ["username", "email", "phone_number", "date_joined", "is_active"]
    list_filter = ["is_active", "is_staff", "date_joined"]
    search_fields = ["username", "email", "phone_number"]
    date_hierarchy = "date_joined"
    ordering = ["-date_joined"]


# Category Admin
@admin.register(Category)
class CategoryAdmin(DraggableMPTTAdmin):
    """
    카테고리 관리자 페이지 설정
    MPTT 드래그 앤 드롭 기능 포함
    """

    # MPTT 관련 설정
    mptt_level_indent = 20  # 계층별 들여쓰기 픽셀

    # DraggableMPTTAdmin의 기본 설정
    list_display = [
        "tree_actions",  # MPTT가 제공하는 트리 액션 버튼
        "indented_title",  # 들여쓰기된 제목
        "related_products_count",
        "related_products_cumulative_count",
    ]

    list_display_links = ["indented_title"]  # 클릭 가능한 필드

    # 필터
    list_filter = [
        "is_active",
    ]

    # 검색
    search_fields = ["name", "slug"]

    # name 입력시 slug 자동 생성
    prepopulated_fields = {"slug": ("name",)}

    # 읽기 전용 필드
    readonly_fields = ["created_at", "updated_at"]

    def related_products_count(self, obj):
        """현재 카테고리의 제품 수"""
        return obj.products.count()

    related_products_count.short_description = "직접 제품 수"

    def related_products_cumulative_count(self, obj):
        """현재 카테고리와 하위 카테고리의 모든 제품 수"""
        return Product.objects.filter(
            category__in=obj.get_descendants(include_self=True)
        ).count()

    related_products_cumulative_count.short_description = "전체 제품 수"


# Product 관련 Inline
class ProductImageInline(admin.TabularInline):
    """제품 이미지 인라인 (제품 수정 페이지에서 함께 편집)"""

    model = ProductImage
    extra = 1
    fields = ["image", "alt_text", "order", "is_primary"]
    ordering = ["order"]


class ProductReviewInline(admin.TabularInline):
    """상품 편집 페이지에서 리뷰 확인"""

    model = ProductReview
    extra = 0
    readonly_fields = ["user", "rating", "comment", "created_at"]
    can_delete = False  # 리뷰는 여기서 삭제 못함


# Product Admin
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    상품 관리
    - 이미지, 리뷰 함께 관리
    - 재고, 가격 한눈에 확인
    """

    list_display = [
        "name",
        "category",
        "seller",
        "price",
        "formatted_price",  # 가격 포맷팅
        "stock",
        "is_active",
        "created_at",
    ]

    list_filter = ["category", "is_active", "created_at"]
    search_fields = ["name", "description", "sku"]
    prepopulated_fields = {"slug": ("name",)}
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    # 상세 페이지 필드 구성
    fieldsets = (
        ("기본 정보", {"fields": ("name", "slug", "category", "sku", "seller")}),
        ("가격 및 재고", {"fields": ("price", "stock_quantity")}),
        ("상세 정보", {"fields": ("description", "is_active")}),
        (
            "시간 정보",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    # 인라인으로 이미지와 리뷰 표시
    inlines = [ProductImageInline, ProductReviewInline]

    def formatted_price(self, obj):
        """가격을 원화 형식으로 표시"""
        return f"₩{obj.price:,.0f}"

    formatted_price.short_description = "가격"
    formatted_price.admin_order_field = "price"  # 정렬 가능하게


# ProductReview Admin
@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    """
    리뷰 전체 관리
    - 부적절한 리뷰 관리
    - 평점별 필터링
    """

    list_display = ["product", "user", "rating", "comment_preview", "created_at"]
    list_filter = ["rating", "created_at"]
    search_fields = ["product__name", "user__username", "comment"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    def comment_preview(self, obj):
        """댓글 미리보기 (50자)"""
        if len(obj.comment) > 50:
            return obj.comment[:50] + "..."
        return obj.comment

    comment_preview.short_description = "리뷰 내용"


# Order 관련 Inline
class OrderItemInline(admin.TabularInline):
    """Order 편집 페이지에서 OrderItem을 함께 관리"""

    model = OrderItem
    extra = 0
    readonly_fields = ["product", "quantity", "price"]
    can_delete = False


# Order admin
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """
    주문 관리자 페이지 설정
    """

    list_display = [
        "id",
        "user",
        "status",
        "formatted_total_amount",
        "created_at",
    ]

    list_filter = ["status", "created_at"]
    search_fields = ["order_number", "user__username", "user__email"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    fieldsets = (
        (
            "주문 정보",
            {"fields": ("user", "status", "total_amount", "created_at", "updated_at")},
        ),
        (
            "배송 정보",
            {
                "fields": (
                    "shipping_name",
                    "shipping_phone",
                    ("shipping_postal_code", "shipping_address"),
                    "shipping_address_detail",
                    "order_memo",
                )
            },
        ),
        ("결제 정보", {"fields": ("payment_method",), "classes": ("collapse",)}),
    )

    inlines = [OrderItemInline]

    # 상태별 액션
    actions = ["mark_as_paid", "mark_as_shipped", "mark_as_delivered"]

    def formatted_total_amount(self, obj):
        """금액을 원화 형식으로 표시"""
        return f"₩{obj.total_amount:,.0f}"

    formatted_total_amount.short_description = "총 금액"
    formatted_total_amount.admin_order_field = "total_amount"

    def mark_as_paid(self, request, queryset):
        """선택된 주문을 결제완료로 변경"""
        queryset.update(status="paid")
        self.message_user(
            request, f"{queryset.count()}개 주문이 결제완료로 변경되었습니다."
        )

    mark_as_paid.short_description = "선택된 주문을 결제완료로 변경"

    def mark_as_shipped(self, request, queryset):
        """선택된 주문을 배송중으로 변경"""
        queryset.update(status="shipped")
        self.message_user(
            request, f"{queryset.count()}개 주문이 배송중으로 변경되었습니다."
        )

    mark_as_shipped.short_description = "선택된 주문을 배송중으로 변경"

    def mark_as_delivered(self, request, queryset):
        """선택된 주문을 배송완료로 변경"""
        queryset.update(status="delivered")
        self.message_user(
            request, f"{queryset.count()}개 주문이 배송완료로 변경되었습니다."
        )

    mark_as_delivered.short_description = "선택된 주문을 배송완료로 변경"


# CartItem Inline
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ["product", "quantity", "get_subtotal", "added_at"]
    readonly_fields = ["get_subtotal", "added_at"]

    def get_subtotal(self, obj):
        """소계 표시"""
        return f"₩{obj.subtotal:,.0f}"

    get_subtotal.short_description = "소계"


# Cart Admin 설정 추가
class CartAdmin(admin.ModelAdmin):
    """
    장바구니 관리자 페이지 설정
    """

    list_display = [
        "id",
        "user",
        "session_key",
        "item_count",
        "created_at",
    ]
    list_filter = ["created_at"]
    search_fields = ["user__username", "session_key"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    def item_count(self, obj):
        """장바구니 아이템 수"""
        return obj.items.count()

    item_count.short_description = "아이템 수"


# CartItem Admin
@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """
    장바구니 아이템 관리자 페이지 설정
    """

    list_display = ["cart", "product", "quantity", "formatted_subtotal"]
    list_filter = ["cart__created_at"]
    search_fields = ["cart__user__username", "product__name"]

    def formatted_subtotal(self, obj):
        """소계 원화 형식"""
        subtotal = obj.product.price * obj.quantity
        return f"₩{subtotal:,.0f}"

    formatted_subtotal.short_description = "소계"


# 모델 등록 (맨 아래에 추가)
admin.site.register(Cart, CartAdmin)


# Admin 사이트 설정
admin.site.site_header = "쇼핑몰 관리자"
admin.site.site_title = "쇼핑몰 Admin"
admin.site.index_title = "쇼핑몰 관리"
