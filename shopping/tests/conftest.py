import pytest
from django.conf import settings


@pytest.fixture(scope="session", autouse=True)
def setup_celery_for_tests():
    """테스트 환경에서 Celery 동기 실행 설정"""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
