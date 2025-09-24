from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.db.models import Count, Avg, Q
from mptt.admin import DraggableMPTTAdmin
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta


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

from .models.payment import Payment, PaymentLog

from .models.point import PointHistory

# 이메일 인증 모델
from shopping.models.email_verification import EmailVerificationToken, EmailLog


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
    readonly_fields = ["created_at", "updated_at"]

    # 상세 페이지 필드 구성
    fieldsets = (
        ("기본 정보", {"fields": ("name", "slug", "category", "sku", "seller")}),
        ("가격 및 재고", {"fields": ("price", "stock")}),
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
        "used_points",
        "final_amount",
        "earned_points",
    ]

    list_filter = ["status", "created_at"]
    search_fields = ["order_number", "user__username", "user__email"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    readonly_fields = ["order_number", "total_amount", "created_at", "updated_at"]
    fieldsets = (
        (
            "주문 정보",
            {"fields": ("user", "status", "order_number", "total_amount")},
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
        (
            "포인트",
            {
                "fields": (
                    "used_points",
                    "final_amount",
                    "earned_points",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "시간정보",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),  # 접을 수 있게
            },
        ),
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


# PaymentAdmin
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """
    결제 관리 Admin
    """

    list_display = [
        "id",
        "order_link",
        "order_id",
        "colored_status",
        "amount_display",
        "method",
        "user_display",
        "approved_at",
        "created_at",
    ]

    list_filter = [
        "status",
        "method",
        "is_canceled",
        "created_at",
        "approved_at",
    ]

    search_fields = [
        "order_id",
        "payment_key",
        "order__user__username",
        "order__user__email",
        "order__shipping_name",
    ]

    readonly_fields = [
        "payment_key",
        "order_id",
        "approved_at",
        "canceled_at",
        "receipt_url_link",
        "raw_response_formatted",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        ("주문 정보", {"fields": ("order", "order_id")}),
        (
            "결제 정보",
            {
                "fields": (
                    "payment_key",
                    "amount",
                    "status",
                    "method",
                    "approved_at",
                    "receipt_url_link",
                )
            },
        ),
        (
            "카드 정보",
            {
                "fields": (
                    "card_company",
                    "card_number",
                    "installment_plan_months",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "취소 정보",
            {
                "fields": (
                    "is_canceled",
                    "canceled_amount",
                    "cancel_reason",
                    "canceled_at",
                ),
                "classes": ("collapse",),
            },
        ),
        ("실패 정보", {"fields": ("fail_reason",), "classes": ("collapse",)}),
        (
            "원본 데이터",
            {"fields": ("raw_response_formatted",), "classes": ("collapse",)},
        ),
        ("시간 정보", {"fields": ("created_at", "updated_at")}),
    )

    def order_link(self, obj):
        """주문 상세 페이지 링크"""
        if obj.order:
            url = reverse("admin:shopping_order_change", args=[obj.order.pk])
            return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
        return "-"

    order_link.short_description = "주문번호"

    def colored_status(self, obj):
        """상태별 색상 표시"""
        colors = {
            "ready": "#FFA500",  # 주황
            "in_progress": "#4169E1",  # 파랑
            "done": "#008000",  # 초록
            "canceled": "#DC143C",  # 빨강
            "aborted": "#8B0000",  # 진한 빨강
            "expired": "#808080",  # 회색
        }
        color = colors.get(obj.status, "#000000")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    colored_status.short_description = "상태"

    def amount_display(self, obj):
        """금액 포맷팅"""
        formatted_amount = "{:,}".format(int(obj.amount))
        return format_html("<strong>{}원</strong>", formatted_amount)

    amount_display.short_description = "결제금액"

    def user_display(self, obj):
        """사용자 정보"""
        if obj.order and obj.order.user:
            user = obj.order.user
            return f"{user.username} ({user.email})"
        return "-"

    user_display.short_description = "사용자"

    def receipt_url_link(self, obj):
        """영수증 링크"""
        if obj.receipt_url:
            return format_html(
                '<a href="{}" target="_blank">영수증 보기</a>', obj.receipt_url
            )
        return "-"

    receipt_url_link.short_description = "영수증"

    def raw_response_formatted(self, obj):
        """JSON 응답 포맷팅"""
        import json

        if obj.raw_response:
            formatted = json.dumps(obj.raw_response, indent=2, ensure_ascii=False)
            return format_html("<pre>{}</pre>", formatted)
        return "-"

    raw_response_formatted.short_description = "토스페이먼츠 응답"

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        """쿼리 최적화"""
        return super().get_queryset(request).select_related("order", "order__user")


# PaymentLogAdmin
@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    """
    결제 로그 Admin
    """

    list_display = [
        "id",
        "payment_link",
        "colored_log_type",
        "message_preview",
        "created_at",
    ]

    list_filter = [
        "log_type",
        "created_at",
    ]

    search_fields = [
        "payment__order_id",
        "payment__payment_key",
        "message",
    ]

    readonly_fields = [
        "payment",
        "log_type",
        "message",
        "data_formatted",
        "created_at",
    ]

    fieldsets = (
        ("기본 정보", {"fields": ("payment", "log_type", "message")}),
        ("추가 데이터", {"fields": ("data_formatted",), "classes": ("collapse",)}),
        ("시간 정보", {"fields": ("created_at",)}),
    )

    def payment_link(self, obj):
        """결제 상세 링크"""
        url = reverse("admin:shopping_payment_change", args=[obj.payment.pk])
        return format_html('<a href="{}">{}</a>', url, obj.payment.order_id)

    payment_link.short_description = "주문번호"

    def colored_log_type(self, obj):
        """로그 타입별 색상"""
        colors = {
            "request": "#4169E1",  # 파랑
            "approve": "#008000",  # 초록
            "cancel": "#FFA500",  # 주황
            "webhook": "#9370DB",  # 보라
            "error": "#DC143C",  # 빨강
        }
        color = colors.get(obj.log_type, "#000000")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_log_type_display(),
        )

    colored_log_type.short_description = "로그 타입"

    def message_preview(self, obj):
        """메시지 미리보기"""
        if len(obj.message) > 50:
            return obj.message[:50] + "..."
        return obj.message

    message_preview.short_description = "메시지"

    def data_formatted(self, obj):
        """JSON 데이터 포맷팅"""
        import json

        if obj.data:
            formatted = json.dumps(obj.data, indent=2, ensure_ascii=False)
            return format_html("<pre>{}</pre>", formatted)
        return "-"

    data_formatted.short_description = "데이터"

    def has_add_permission(self, request):
        """로그는 수동 추가 불가"""
        return False

    def has_delete_permission(self, request, obj=None):
        """로그는 삭제 불가"""
        return False

    def has_change_permission(self, request, obj=None):
        """로그는 수정 불가"""
        return False


@admin.register(PointHistory)
class PointHistoryAdmin(admin.ModelAdmin):
    """포인트 이력 관리자"""

    list_display = [
        "id",
        "user",
        "formatted_points",
        "type",
        "balance",
        "order",
        "description",
        "created_at",
    ]

    list_filter = [
        "type",
        "created_at",
        ("expires_at", admin.DateFieldListFilter),
    ]

    search_fields = [
        "user__username",
        "user__email",
        "order__order_number",
        "description",
    ]

    readonly_fields = [
        "user",
        "points",
        "balance",
        "type",
        "order",
        "description",
        "expires_at",
        "metadata",
        "created_at",
    ]

    ordering = ["-created_at"]

    def formatted_points(self, obj):
        """포인트 표시 형식"""
        if obj.points > 0:
            return f"+{obj.points}P"
        else:
            return f"{obj.points}P"

    formatted_points.short_description = "포인트"

    def has_add_permission(self, request):
        """직접 추가 방지 (시스템에서만 생성)"""
        return False

    def has_delete_permission(self, request, obj=None):
        """삭제 방지"""
        return False

    class Media:
        css = {"all": ("admin/css/point_history.css",)}


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    """이메일 인증 토큰 관리"""

    list_display = [
        "user_email",
        "verification_code_display",
        "status_display",
        "created_at",
        "is_expired_display",
        "used_at",
    ]

    list_filter = ["is_used", "created_at", ("user", admin.RelatedOnlyFieldListFilter)]

    search_fields = ["user__email", "user__username", "verification_code", "token"]

    readonly_fields = ["token", "verification_code", "created_at", "used_at"]

    ordering = ["created_at"]

    def user_email(self, obj):
        return obj.user.email

    user_email.short_description = "사용자 이메일"
    user_email.admin_order_field = "user__email"

    def verification_code_display(self, obj):
        return format_html(
            '<code style="font-size: 14px; font-weight: bold; '
            'background: #f0f0f0; padding: 2px 6px; border-radius: 3px;">{}</code>',
            obj.verification_code,
        )

    verification_code_display.short_description = "인증 코드"

    def status_display(self, obj):
        if obj.is_used:
            return format_html('<span style="color: green;">✓ 사용됨</span>')
        elif obj.is_expired():
            return format_html('<span style="color: red;">✗ 만료됨</span>')
        else:
            return format_html('<span style="color: blue;">● 유효</span>')

    status_display.short_description = "상태"

    def is_expired_display(self, obj):
        return obj.is_expired()

    is_expired_display.short_description = "만료 여부"
    is_expired_display.boolean = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """이메일 발송 로그 관리"""

    list_display = [
        "id",
        "email_type",
        "recipient_email",
        "status_badge",
        "sent_at",
        "verified_at",
        "created_at",
    ]

    list_filter = ["email_type", "status", "created_at", "sent_at", "verified_at"]

    search_fields = ["recipient_email", "subject", "user__email", "user__username"]

    readonly_fields = [
        "created_at",
        "sent_at",
        "opened_at",
        "clicked_at",
        "verified_at",
    ]

    ordering = ["-created_at"]

    date_hierarchy = "created_at"

    def status_badge(self, obj):
        colors = {
            "pending": "#ffc107",
            "sent": "#28a745",
            "failed": "#dc3545",
            "opened": "#17a2b8",
            "clicked": "#6610f2",
            "verified": "#28a745",
        }

        icons = {
            "pending": "⏳",
            "sent": "✉️",
            "failed": "❌",
            "opened": "👁️",
            "clicked": "👆",
            "verified": "✅",
        }

        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 3px 8px; border-radius: 3px; font-size: 11px;">'
            "{} {}</span>",
            colors.get(obj.status, "#6c757d"),
            icons.get(obj.status, ""),
            obj.get_status_display(),
        )

    status_badge.short_description = "상태"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "token")

    # 액션 추가
    actions = ["mark_as_sent", "mark_as_failed"]

    def mark_as_sent(self, request, queryset):
        updated = queryset.filter(status="pending").update(
            status="sent", sent_at=timezone.now()
        )
        self.message_user(request, f"{updated}개의 이메일을 발송 완료로 표시했습니다.")

    mark_as_sent.short_description = "선택한 이메일을 발송 완료로 표시"

    def mark_as_failed(self, request, queryset):
        updated = queryset.filter(status="pending").update(status="failed")
        self.message_user(request, f"{updated}개의 이메일을 발송 실패로 표시했습니다.")

    mark_as_failed.short_description = "선택한 이메일을 발송 실패로 표시"

    # 통계 표시 (상단에 표시)
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        # 오늘 통계
        today = timezone.now().date()
        today_logs = EmailLog.objects.filter(
            created_at__date=today, email_type="verification"
        )

        # 전체 통계
        total_logs = EmailLog.objects.filter(email_type="verification")

        extra_context["summary"] = {
            "today_sent": today_logs.filter(status="sent").count(),
            "today_verified": today_logs.filter(status="verified").count(),
            "today_failed": today_logs.filter(status="failed").count(),
            "total_sent": total_logs.filter(status="sent").count(),
            "total_verified": total_logs.filter(status="verified").count(),
            "verification_rate": self.calculate_verification_rate(total_logs),
        }

        return super().changelist_view(request, extra_context=extra_context)

    def calculate_verification_rate(self, queryset):
        """인증 완료율 계산"""
        sent_count = queryset.filter(status="sent").count()
        verified_count = queryset.filter(status="verified").count()

        if sent_count > 0:
            rate = (verified_count / sent_count) * 100
            return f"{rate:.1f}%"
        return "0%"


# Admin 사이트 설정
admin.site.site_header = "쇼핑몰 관리자"
admin.site.site_title = "쇼핑몰 Admin"
admin.site.index_title = "쇼핑몰 관리"
