"""
Social Authentication Configuration (django-allauth 65.12+)
소셜 로그인 관련 모든 설정을 관리합니다.
"""

import os

# ==========================================
# Django Sites Framework (allauth 필수)
# ==========================================
SITE_ID = 1

# ==========================================
# allauth 기본 설정
# ==========================================

ACCOUNT_SIGNUP_FIELDS = [
    "email*",  # * = 필수
    "username*",  # * = 필수
    "password1*",
    "password2*",
]

ACCOUNT_EMAIL_VERIFICATION = "none"  # 소셜 로그인은 자동 인증
ACCOUNT_LOGIN_METHODS = {"email"}  # set 타입

# ==========================================
# 소셜 로그인 설정
# ==========================================
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_STORE_TOKENS = True
SOCIALACCOUNT_LOGIN_ON_GET = True

# ==========================================
# dj-rest-auth 7.0+ 설정
# ==========================================
REST_AUTH = {
    "USE_JWT": True,
    "JWT_AUTH_HTTPONLY": False,  # 프론트엔드에서 토큰 직접 관리
    "JWT_AUTH_COOKIE": None,  # 쿠키 미사용
    "USER_DETAILS_SERIALIZER": "shopping.serializers.user_serializers.UserSerializer",
    "JWT_AUTH_COOKIE_USE_CSRF": False,
    "JWT_AUTH_SECURE": False,  # HTTPS 사용 시 True로 변경
    "JWT_AUTH_SAMESITE": "Lax",  # CSRF 보호
}

# JWT 토큰 모델 미사용 (SimpleJWT 사용)
REST_AUTH_TOKEN_MODEL = None
REST_AUTH_TOKEN_CREATOR = None

# allauth 어댑터 (기본값이지만 명시)
ACCOUNT_ADAPTER = "allauth.account.adapter.DefaultAccountAdapter"
SOCIALACCOUNT_ADAPTER = "shopping.adapters.CustomSocialAccountAdapter"

# ==========================================
# 소셜 로그인 제공자별 설정
# ==========================================
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
        "APP": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "key": "",
        },
    },
    "kakao": {
        "APP": {
            "client_id": os.getenv("KAKAO_REST_API_KEY", ""),
            "secret": os.getenv("KAKAO_CLIENT_SECRET", ""),
            "key": "",
        },
    },
    "naver": {
        "APP": {
            "client_id": os.getenv("NAVER_CLIENT_ID", ""),
            "secret": os.getenv("NAVER_CLIENT_SECRET", ""),
            "key": "",
        },
    },
}

# 소셜 로그인 리다이렉트 URI (프론트엔드)
SOCIAL_LOGIN_REDIRECT_URI = os.getenv("SOCIAL_LOGIN_REDIRECT_URI", "http://localhost:8000/social/test/")
