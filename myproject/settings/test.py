"""
Django Test Settings
테스트 환경 전용 설정 (pytest, Django test)
"""

import os

from myproject.settings.base import *  # noqa: F401, F403
from myproject.settings.components.logging import get_logging_config

# ==========================================================================
# Test Mode Flag
# ==========================================================================

TESTING = True
DEBUG = True

# ==========================================================================
# Database (PostgreSQL - Test with optimized connection settings)
# ==========================================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_NAME", "myproject_dev"),
        "USER": os.getenv("DATABASE_USER", "postgres"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD", "postgres"),
        "HOST": os.getenv("DATABASE_HOST", "localhost"),
        "PORT": os.getenv("DATABASE_PORT", "5432"),
        # 테스트에서는 연결 즉시 닫기 (동시성 테스트에서 "too many clients" 방지)
        "CONN_MAX_AGE": 0,
        # Health checks 비활성화하여 연결 절약
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",
        },
    }
}

# ==========================================================================
# Cache (Dummy - 테스트에서는 캐시 비활성화)
# ==========================================================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# ==========================================================================
# Celery (동기 실행 - 테스트에서는 즉시 실행)
# ==========================================================================

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# ==========================================================================
# Rate Limiting - 테스트에서는 비활성화
# ==========================================================================

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

# ==========================================================================
# Logging (Quiet mode for tests)
# ==========================================================================

LOGGING = get_logging_config(debug=False)

# ==========================================================================
# Password Hashing (빠른 해싱 - 테스트 속도 향상)
# ==========================================================================

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ==========================================================================
# Email (콘솔 출력)
# ==========================================================================

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
