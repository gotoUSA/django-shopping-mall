"""
Celery 설정 및 기본 태스크 테스트

Phase 0: Task 0-2에서 요구하는 Celery 설정이 정상 작동하는지 검증
"""

import pytest

from shopping.tasks.point_tasks import expire_points_task


@pytest.mark.django_db(transaction=True)
class TestCelerySetup:
    """Celery 설정 검증"""

    def test_celery_task_can_run(self):
        """Celery 태스크가 정상 실행되는지 확인

        - Celery TASK_ALWAYS_EAGER 설정으로 동기 실행
        - 기본 포인트 만료 태스크 실행 테스트
        """
        # Act: 포인트 만료 태스크 실행
        result = expire_points_task.delay()

        # Assert: 태스크가 성공적으로 완료됨
        assert result.successful()

    def test_celery_config_eager_mode(self, settings):
        """테스트 환경에서 EAGER 모드가 활성화되어 있는지 확인

        - TASK_ALWAYS_EAGER: True로 설정되어야 함
        - TASK_EAGER_PROPAGATES: True로 설정되어야 함
        """
        # Assert: Eager 모드 설정 확인
        assert settings.CELERY_TASK_ALWAYS_EAGER is True
        assert settings.CELERY_TASK_EAGER_PROPAGATES is True
