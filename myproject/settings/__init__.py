"""
Django Settings Package
환경변수 DJANGO_ENV에 따라 적절한 설정을 로드합니다.

사용법:
- 로컬 개발: DJANGO_ENV=local (기본값)
- 프로덕션: DJANGO_ENV=production
- 테스트: DJANGO_ENV=test (pytest에서 자동 설정됨)

예시:
    # .env 파일
    DJANGO_ENV=local

    # 또는 명령줄에서
    DJANGO_ENV=production python manage.py runserver
"""

import os
import sys

# pytest 또는 Django test 실행 감지
_is_testing = (
    "test" in sys.argv  # Django test
    or ("pytest" in sys.argv[0] if sys.argv else False)  # pytest
    or os.getenv("PYTEST_CURRENT_TEST") is not None  # pytest 실행 중
    or os.getenv("TESTING") == "True"  # 수동 설정
)

# 환경 결정: 테스트 > 환경변수 > 기본값(local)
if _is_testing:
    _env = "test"
else:
    _env = os.environ.get("DJANGO_ENV", "local")

# 환경에 맞는 설정 로드
if _env == "production":
    from myproject.settings.production import *  # noqa: F401, F403
elif _env == "test":
    from myproject.settings.test import *  # noqa: F401, F403
else:
    from myproject.settings.local import *  # noqa: F401, F403
