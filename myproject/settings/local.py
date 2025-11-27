"""
Django Local Development Settings
로컬 개발 환경 전용 설정
"""

import os
import socket

from myproject.settings.base import *  # noqa: F401, F403
from myproject.settings.components.logging import get_logging_config

# ==========================================================================
# Debug Settings
# ==========================================================================

DEBUG = True

# ==========================================================================
# Debug Toolbar
# ==========================================================================

INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405

MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]

# Docker 환경에서도 작동하도록
hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
INTERNAL_IPS += [ip[: ip.rfind(".")] + ".1" for ip in ips]

# ==========================================================================
# Database (PostgreSQL - Dev/Prod parity)
# ==========================================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_NAME", "myproject_dev"),
        "USER": os.getenv("DATABASE_USER", "postgres"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD", "postgres"),
        "HOST": os.getenv("DATABASE_HOST", "localhost"),
        "PORT": os.getenv("DATABASE_PORT", "5432"),
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",
        },
    }
}

# ==========================================================================
# Cache (Redis)
# ==========================================================================

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# ==========================================================================
# Rate Limiting - 개발 환경에서는 실제 제한 적용
# ==========================================================================

DISABLE_RATE_LIMITING = os.getenv("DISABLE_RATE_LIMITING", "FALSE") == "TRUE"

if DISABLE_RATE_LIMITING:
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
        "login": "1000/min",
        "register": "1000/hour",
        "token_refresh": "1000/min",
        "password_reset": "1000/hour",
        "email_verification": "1000/min",
        "email_verification_resend": "1000/hour",
        "payment_request": "1000/min",
        "payment_confirm": "1000/min",
        "payment_cancel": "1000/min",
        "order_create": "1000/min",
        "order_cancel": "1000/min",
        "anon_global": "10000/hour",
        "user_global": "10000/hour",
        "webhook": "1000/min",
    }
else:
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [  # noqa: F405
        "shopping.throttles.GlobalAnonRateThrottle",
        "shopping.throttles.GlobalUserRateThrottle",
    ]
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
        "login": "3/min",
        "register": "3/hour",
        "token_refresh": "10/min",
        "password_reset": "3/hour",
        "email_verification": "1/min",
        "email_verification_resend": "3/hour",
        "payment_request": "10/min",
        "payment_confirm": "5/min",
        "payment_cancel": "5/min",
        "order_create": "10/min",
        "order_cancel": "5/min",
        "anon_global": "100/hour",
        "user_global": "1000/hour",
        "webhook": "100/min",
    }

# ==========================================================================
# Logging (Debug mode)
# ==========================================================================

LOGGING = get_logging_config(debug=True)

# ==========================================================================
# Encryption Key Warning (개발 환경에서만)
# ==========================================================================

if not ENCRYPTION_KEY:  # noqa: F405
    import warnings

    warnings.warn(
        "⚠️ ENCRYPTION_KEY가 설정되지 않았습니다. "
        "계좌번호 암호화 기능이 작동하지 않습니다. "
        ".env 파일에 ENCRYPTION_KEY를 추가해주세요."
    )
