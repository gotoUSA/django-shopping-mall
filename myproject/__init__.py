"""
Django 프로젝트 초기화 파일
Celery 앱을 임포트하여 Django 시작 시 자동으로 로드
"""

from .celery import app as celery_app

# Celery 앱을 Django와 함께 로드
__all__ = ("celery_app",)
