"""
Celery 설정 파일
Redis를 브로커로 사용하여 비동기 작업 처리
"""

import os
from celery import Celery
from celery.schedules import crontab

# Django 설정 모듈 지정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

# Celery 앱 생성
app = Celery("myproject")

# Django 설정에서 CELERY_ 접두사가 붙은 설정 로드
app.config_from_object("django.conf:settings", namespace="CELERY")

# 등록된 Django 앱에서 tasks.py 자동 로드
app.autodiscover_tasks()

# Celery Beat 스케줄 설정
app.conf.beat_schedule = {
    # 포인트 만료 처리 - 매일 새벽 2시
    "expire-points-daily": {
        "task": "shopping.tasks.expire_points_task",
        "schedule": crontab(hour=2, minute=0),  # 매일 02:00
        "options": {
            "expires": 3600,  # 1시간 후 만료
        },
    },
    # 포인트 만료 예정 알림 - 매일 오전 10시
    "send-expiry-notifications": {
        "task": "shopping.tasks.send_expiry_notification_task",
        "schedule": crontab(hour=10, minute=0),  # 매일 10:00
        "options": {
            "expires": 3600,
        },
    },
    # 테스트용: 5분마다 실행 (개발 환경에서만 사용)
    # 'test-periodic-task': {
    #     'task': 'shopping.tasks.test_periodic_task',
    #     'schedule': crontab(minute='*/5'),  # 5분마다
    # },
}

# Celery 설정
app.conf.update(
    # 작업 결과 만료 시간 (초)
    result_expires=3600,
    # 시간대 설정
    timezone="Asia/Seoul",
    # 작업 직렬화 방식
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # 작업 실행 옵션
    task_soft_time_limit=300,  # 5분
    task_time_limit=600,  # 10분
    # 워커 설정
    worker_max_tasks_per_child=1000,  # 메모리 누수 방지
    worker_prefetch_multiplier=4,
    # 큐 설정
    task_default_queue="default",
    task_queues={
        "default": {
            "exchange": "default",
            "exchange_type": "direct",
            "routing_key": "default",
        },
        "points": {  # 포인트 관련 작업 전용 큐
            "exchange": "points",
            "exchange_type": "direct",
            "routing_key": "points",
        },
        "notifications": {  # 알림 전용 큐
            "exchange": "notifications",
            "exchange_type": "direct",
            "routing_key": "notifications",
        },
    },
    # 라우팅 설정
    task_routes={
        "shopping.tasks.expire_points_task": {"queue": "points"},
        "shopping.tasks.send_expiry_notification_task": {"queue": "notifications"},
    },
)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """디버그용 태스크"""
    print(f"Request: {self.request!r}")
