from django.urls import path, include
from rest_framework.routers import DefaultRouter

# ViewSet import
from shopping.views.product_views import ProductViewSet, CategoryViewSet
from shopping.views.cart_views import CartViewSet, CartItemViewSet
from shopping.views.order_views import OrderViewSet

# Auth Views import
from shopping.views.auth_views import (
    RegisterView,
    LoginView,
    CustomTokenRefreshView,
    LogoutView,
    ProfileView,
    PasswordChangeView,
    check_token,
    email_verification_request,
    withdraw,
)

# Email Verification Views import
from shopping.views.email_verification_views import (
    SendVerificationEmailView,
    VerifyEmailView,
    ResendVerificationEmailView,
    check_verification_status,
)


# Payment Views import
from shopping.views.payment_views import (
    PaymentRequestView,
    PaymentConfirmView,
    PaymentCancelView,
    PaymentDetailView,
    PaymentListView,
    payment_test_page,
    payment_success,
    payment_fail,
)

# Point view import
from .views import point_views

# Webhook import
from shopping.webhooks.toss_webhook_view import toss_webhook

# wishlist import
from shopping.views.wishlist_views import WishlistViewSet

# social login
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.kakao.views import KakaoOAuth2Adapter
from allauth.socialaccount.providers.naver.views import NaverOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.conf import settings
from django.views.generic import TemplateView

# notification import
from rest_framework_nested import routers
from .views.notification_views import NotificationViewSet
from .views.product_qa_views import ProductQuestionViewSet, MyQuestionViewSet


# 소셜 로그인 뷰 정의
class GoogleLogin(SocialLoginView):
    """구글 소셜 로그인"""

    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    callback_url = settings.SOCIAL_LOGIN_REDIRECT_URI


class KakaoLogin(SocialLoginView):
    """카카오 소셜 로그인"""

    adapter_class = KakaoOAuth2Adapter
    client_class = OAuth2Client
    callback_url = settings.SOCIAL_LOGIN_REDIRECT_URI


class NaverLogin(SocialLoginView):
    """네이버 소셜 로그인"""

    adapter_class = NaverOAuth2Adapter
    client_class = OAuth2Client
    callback_url = settings.SOCIAL_LOGIN_REDIRECT_URI


# DRF의 라우터 생성
router = DefaultRouter()

# ViewSet 등록
router.register(r"products", ProductViewSet, basename="product")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"orders", OrderViewSet, basename="order")

# 알림 라우터
router.register(r"notifications", NotificationViewSet, basename="notification")

# 내 문의 라우터
router.register(r"my/questions", MyQuestionViewSet, basename="my-question")

# 상품별 문의 중첩 라우터
# /api/products/{product_pk}/questions/
products_router = routers.NestedSimpleRouter(router, r"products", lookup="product")
products_router.register(
    r"questions", ProductQuestionViewSet, basename="product-question"
)


# Cart 관련 ViewSet 등록
# CartViewSet은 특별한 actions만 있으므로 수동 등록
router.register(r"cart-items", CartItemViewSet, basename="cart-item")

# URL 패턴 정의
urlpatterns = [
    # 웹페이지 URL
    path(
        "payment/test/<int:order_id>/",
        payment_test_page,
        name="payment_test",
    ),
    path("payment/success/", payment_success, name="payment_success"),
    path("payment/fail/", payment_fail, name="payment_fail"),
    # API root - 라우터가 자동으로 생성하는 URL들
    path("", include(router.urls)),
    path("", include(products_router.urls)),  # 중첩 라우터
    # 인증(Auth) 관련 URLs
    # 회원가입 및 로그인
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    # 토큰 관리
    path("auth/token/refresh/", CustomTokenRefreshView.as_view(), name="token-refresh"),
    path("auth/token/verify/", check_token, name="token-verify"),
    # 프로필 관리
    path("auth/profile/", ProfileView.as_view(), name="auth-profile"),
    path("auth/password/change/", PasswordChangeView.as_view(), name="password-change"),
    # 이메일 인증
    path(
        "auth/email/send/",
        SendVerificationEmailView.as_view(),
        name="email-verification-send",
    ),
    path(
        "auth/email/verify/",
        VerifyEmailView.as_view(),
        name="email-verification-verify",
    ),
    path(
        "auth/email/resend/",
        ResendVerificationEmailView.as_view(),
        name="email-verification-resend",
    ),
    path(
        "auth/email/status/",
        check_verification_status,
        name="email-verification-status",
    ),
    # 추가 기능
    path("auth/email/verify/", email_verification_request, name="email-verify"),
    path("auth/withdraw/", withdraw, name="auth-withdraw"),
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
    # 결제(Payment) 관련 URLs
    # 결제 요청 및 처리
    path("payments/request/", PaymentRequestView.as_view(), name="payment-request"),
    path("payments/confirm/", PaymentConfirmView.as_view(), name="payment-confirm"),
    path("payments/cancel/", PaymentCancelView.as_view(), name="payment-cancel"),
    path("payments/fail/", payment_fail, name="payment-fail"),
    # 결제 조회
    path("payments/", PaymentListView.as_view(), name="payment-list"),
    path(
        "payments/<int:payment_id>/", PaymentDetailView.as_view(), name="payment-detail"
    ),
    # 포인트 관련 URL
    path("points/my/", point_views.MyPointView.as_view(), name="my_points"),
    path(
        "points/history/",
        point_views.PointHistoryListView.as_view(),
        name="point_history",
    ),
    path("points/check/", point_views.PointCheckView.as_view(), name="point_check"),
    path(
        "points/expiring/",
        point_views.ExpiringPointsView.as_view(),
        name="expiring_points",
    ),
    path("points/statistics/", point_views.point_statistics, name="point_statistics"),
    # 웹훅(Webhook) URLs
    path("webhooks/toss/", toss_webhook, name="toss-webhook"),
    # 찜하기(Wishlist) 관련 URLs
    path("wishlist/", WishlistViewSet.as_view({"get": "list"}), name="wishlist-list"),
    path(
        "wishlist/toggle/",
        WishlistViewSet.as_view({"post": "toggle"}),
        name="wishlist-toggle",
    ),
    path(
        "wishlist/add/", WishlistViewSet.as_view({"post": "add"}), name="wishlist-add"
    ),
    path(
        "wishlist/remove/",
        WishlistViewSet.as_view({"delete": "remove"}),
        name="wishlist-remove",
    ),
    path(
        "wishlist/bulk_add/",
        WishlistViewSet.as_view({"post": "bulk_add"}),
        name="wishlist-bulk-add",
    ),
    path(
        "wishlist/clear/",
        WishlistViewSet.as_view({"delete": "clear"}),
        name="wishlist-clear",
    ),
    path(
        "wishlist/check/",
        WishlistViewSet.as_view({"get": "check"}),
        name="wishlist-check",
    ),
    path(
        "wishlist/stats/",
        WishlistViewSet.as_view({"get": "stats"}),
        name="wishlist-stats",
    ),
    path(
        "wishlist/move_to_cart/",
        WishlistViewSet.as_view({"post": "move_to_cart"}),
        name="wishlist-move-to-cart",
    ),
    # 소셜 로그인 엔드포인트
    path("auth/social/google/", GoogleLogin.as_view(), name="google-login"),
    path("auth/social/kakao/", KakaoLogin.as_view(), name="kakao-login"),
    path("auth/social/naver/", NaverLogin.as_view(), name="naver-login"),
    # dj-rest-auth 기본 엔드포인트 (소셜 계정 관리)
    path("auth/social/", include("dj_rest_auth.registration.urls")),
    # 소셜 로그인 테스트 페이지
    path(
        "social/test/",
        TemplateView.as_view(template_name="social_test.html"),
        name="social-test-page",
    ),
]

"""
생성되는 URL 패턴:

결제 처리:
- POST   /api/payments/request/      - 결제 요청 (결제창 열기 전)
- POST   /api/payments/confirm/      - 결제 승인 (결제창 완료 후)
- POST   /api/payments/cancel/       - 결제 취소 (전체 취소)
- POST   /api/payments/fail/         - 결제 실패 콜백

결제 조회:
- GET    /api/payments/              - 내 결제 목록
- GET    /api/payments/{id}/         - 결제 상세 정보

웹훅:
- POST   /api/webhooks/toss/         - 토스페이먼츠 웹훅 수신

회원가입 및 로그인:
- POST   /api/auth/register/         - 회원가입 (새 사용자 생성 + 토큰 발급)
- POST   /api/auth/login/            - 로그인 (인증 + 토큰 발급)
- POST   /api/auth/logout/           - 로그아웃 (토큰 블랙리스트 추가)

토큰 관리:
- POST   /api/auth/token/refresh/    - 토큰 갱신 (Refresh Token으로 새 Access Token 발급)
- GET    /api/auth/token/verify/     - 토큰 유효성 확인

프로필 관리:
- GET    /api/auth/profile/          - 내 프로필 조회
- PUT    /api/auth/profile/          - 프로필 전체 수정
- PATCH  /api/auth/profile/          - 프로필 부분 수정
- POST   /api/auth/password/change/  - 비밀번호 변경

추가 기능:
- POST   /api/auth/email/verify/     - 이메일 인증 요청 (구현 예정)
- POST   /api/auth/withdraw/         - 회원 탈퇴

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

조회 및 확인:
- GET    /api/wishlist/              - 내 찜 목록 조회
- GET    /api/wishlist/check/        - 특정 상품 찜 상태 확인
- GET    /api/wishlist/stats/        - 찜 목록 통계

상품 추가/제거:
- POST   /api/wishlist/toggle/       - 찜하기 토글 (추가/제거)
- POST   /api/wishlist/add/          - 찜 목록에 추가
- DELETE /api/wishlist/remove/       - 찜 목록에서 제거
- POST   /api/wishlist/bulk_add/     - 여러 상품 한번에 찜하기
- DELETE /api/wishlist/clear/        - 찜 목록 전체 삭제

장바구니 연동:
- POST   /api/wishlist/move_to_cart/ - 찜 목록에서 장바구니로 이동

검색 및 필터링 예시:
- /api/wishlist/?ordering=-created_at      - 최신순 정렬
- /api/wishlist/?ordering=price            - 가격 낮은순
- /api/wishlist/?is_available=true         - 구매 가능한 상품만
- /api/wishlist/?on_sale=true              - 세일 중인 상품만

알림:
- GET    /api/notifications/              - 알림 목록
- GET    /api/notifications/{id}/         - 알림 상세
- GET    /api/notifications/unread/       - 읽지 않은 알림 개수
- POST   /api/notifications/mark_read/    - 알림 읽음 처리
- DELETE /api/notifications/clear/        - 읽은 알림 삭제

상품 문의:
- GET    /api/products/{product_id}/questions/              - 문의 목록
- POST   /api/products/{product_id}/questions/              - 문의 작성
- GET    /api/products/{product_id}/questions/{id}/         - 문의 상세
- PATCH  /api/products/{product_id}/questions/{id}/         - 문의 수정
- DELETE /api/products/{product_id}/questions/{id}/         - 문의 삭제
- POST   /api/products/{product_id}/questions/{id}/answer/  - 답변 작성
- PATCH  /api/products/{product_id}/questions/{id}/answer/  - 답변 수정
- DELETE /api/products/{product_id}/questions/{id}/answer/  - 답변 삭제

내 문의:
- GET    /api/my/questions/               - 내가 작성한 문의 목록
- GET    /api/my/questions/{id}/          - 문의 상세
"""
