from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.db.models import Count, Avg
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


# Category Admin
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """
    카테고리 관리
    - 계층 구조 표시
    - 상품 개수 확인
    """

    list_display = ["name", "parent", "product_count", "is_active"]
    list_filter = ["is_active", "parent"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}  # name 입력시 slug 자동 생성

    def product_count(self, obj):
        """해당 카테고리의 상품 개수"""
        return obj.products.count()

    product_count.short_description = "상품 수"


# Product 관련 Inline
class ProductImageInline(admin.TabularInline):
    """상품 편집 페이지에서 이미지를 함께 관리"""

    model = ProductImage
    extra = 1
    fields = ["image", "alt_text", "is_primary"]


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
        "price",
        "stock",
        "is_active",
        "average_rating",
        "created_at",
    ]

    list_filter = ["category", "is_active", "created_at"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}

    # 상세 페이지 필드 구성
    fieldsets = (
        ("기본 정보", {"fields": ("name", "slug", "category", "description")}),
        ("가격 및 재고", {"fields": ("price", "stock")}),
        ("상태", {"fields": ("is_active",)}),
    )

    # 인라인으로 이미지와 리뷰 표시
    inlines = [ProductImageInline, ProductReviewInline]

    # 목록에서 바로 수정 가능
    list_editable = ["price", "stock", "is_active"]

    def price_display(self, obj):
        """가격을 원화 형식으로 표시"""
        return f"₩{obj.price:,.0f}"

    price_display.short_description = "가격"

    def average_rating(self, obj):
        """평균 평점 표시"""
        avg = obj.reviews.aggregate(Avg("rating"))["rating__avg"]
        if avg:
            return f"⭐ {avg:.1f}"
        return "-"

    average_rating.short_description = "평균 평점"


# ProductReview Admin
@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    """
    리뷰 전체 관리
    - 부적절한 리뷰 관리
    - 평점별 필터링
    """

    list_display = ["product", "user", "rating_stars", "comment_preview", "created_at"]
    list_filter = ["rating", "created_at"]
    search_fields = ["product__name", "user__username", "comment"]
    readonly_fields = ["user", "product", "created_at"]

    def rating_stars(self, obj):
        """평점을 별로 표시"""
        return "⭐" * obj.rating

    rating_stars.short_description = "평점"

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
    readonly_fields = ("product_name", "price", "get_subtotal_display")
    fields = ("product", "product_name", "quantity", "price", "get_subtotal_display")

    def get_subtotal_display(self, obj):
        """소계를 보기 좋게 표시"""
        if obj.id:
            return f"₩{obj.get_subtotal():,.0f}"
        return "-"

    get_subtotal_display.short_discription = "소계"


# Order admin
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """
    주문 관리
    - 주문 상태 관리
    - 배송 정보 확인
    - 주문 상품 함께 관리
    """

    list_display = [
        "id",
        "user",
        "status",
        "status_colored",
        "total_amount_display",
        "shipping_name",
        "created_at",
    ]

    list_filter = ["status", "payment_method", "created_at"]
    search_fields = ["user__username", "user__email", "shipping_name", "shipping_phone"]
    list_editable = ["status"]
    date_hierarchy = "created_at"

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

    readonly_fields = ("created_at", "updated_at", "total_amount")
    inlines = [OrderItemInline]

    def total_amount_display(self, obj):
        """금액을 원화 형식으로 표시"""
        return f"₩{obj.total_amount:,.0f}"

    total_amount_display.short_description = "총 금액"

    def status_colored(self, obj):
        """주문 상태를 색상으로 구분"""
        colors = {
            "pending": "#FFA500",
            "paid": "#008000",
            "preparing": "#0000FF",
            "shipped": "#800080",
            "delivered": "#006400",
            "cancelled": "#FF0000",
            "refunded": "#8B0000",
        }

        color = colors.get(obj.status, "#000000")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_colored.short_discription = "주문 상태"

    actions = ["make_paid", "make_shipped"]

    def make_paid(self, request, queryset):
        """선택한 주문들을 '결제완료'로 변경"""
        updated = queryset.update(status="paid")
        self.message_user(request, f"{updated}개의 주문이 결제완료로 변경되었습니다.")

    make_paid.short_description = "선택한 주문을 결제완료로 변경"

    def make_shipped(self, request, queryset):
        """선택한 주문들을 '배송중'으로 변경"""
        updated = queryset.update(status="shipped")
        self.message_user(request, f"{updated}개의 주문이 배송중으로 변경되었습니다.")

    make_shipped.short_description = "선택한 주문을 배송중으로 변경"


# UserAdmin 설정
class UserAdmin(BaseUserAdmin):
    """커스텀 User 모델을 위한 Admin 설정"""

    # 목록 표시 필드
    list_display = [
        "username",
        "email",
        "get_full_name",
        "phone_number",
        "membership_level",
        "points",
        "is_active",
        "is_staff",
    ]

    # 목록 필터
    list_filter = [
        "membership_level",
        "is_staff",
        "is_superuser",
        "is_active",
        "is_email_verified",
        "is_phone_verified",
    ]

    # 검색 필드
    search_fields = [
        "username",
        "email",
        "first_name",
        "last_name",
        "phone_number",
        "address",
    ]

    # 정렬
    ordering = ["-date_joined"]

    # 상세 페이지 필드 그룹
    fieldsets = BaseUserAdmin.fieldsets + (
        ("추가 정보", {"fields": ("phone_number", "birth_date")}),
        ("주소 정보", {"fields": ("postal_code", "address", "address_detail")}),
        (
            "회원 정보",
            {
                "fields": (
                    "membership_level",
                    "points",
                    "is_email_verified",
                    "is_phone_verified",
                )
            },
        ),
        ("마케팅 동의", {"fields": ("agree_marketing_email", "agree_marketing_sms")}),
    )

    # 새 사용자 추가시 필드
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("추가 정보", {"fields": ("email", "phone_number", "birth_date")}),
    )


# User 모델 등록
admin.site.register(User, UserAdmin)


# Admin 사이트 설정
admin.site.site_header = "쇼핑몰 관리"
admin.site.site_title = "쇼핑몰 관리"
admin.site.index_title = "쇼핑몰 관리 홈"


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
    list_display = [
        "id",
        "user",
        "get_total_amount",
        "get_total_quantity",
        "is_active",
        "created_at",
        "updated_at",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "get_total_amount",
        "get_total_quantity",
    ]
    inlines = [CartItemInline]

    fieldsets = (
        ("기본 정보", {"fields": ("user", "is_active")}),
        ("요약 정보", {"fields": ("get_total_amount", "get_total_quantity")}),
        (
            "시간 정보",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_total_amount(self, obj):
        """총 금액 표시"""
        return format_html("<strong>₩{}</strong>", f"{obj.total_amount:,.0f}")

    get_total_amount.short_description = "총 금액"

    def get_total_quantity(self, obj):
        """총 수량 표시"""
        return f"{obj.total_quantity}개"

    get_total_quantity.short_description = "총 수량"

    actions = ["clear_cart_items"]

    def clear_cart_items(self, request, queryset):
        """선택한 장바구니 비우기"""
        for cart in queryset:
            cart.clear()
        self.message_user(request, f"{queryset.count()}개의 장바구니를 비웠습니다.")

    clear_cart_items.short_description = "선택한 장바구니 비우기"


# 모델 등록 (맨 아래에 추가)
admin.site.register(Cart, CartAdmin)
