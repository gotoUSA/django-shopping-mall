import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestProfileView:
    def test_get_profile_authenticated(self, authenticated_client):
        """인증된 사용자 프로필 조회"""
        pass

    def test_get_profile_unauthenticated(self, api_client):
        """인증 없이 프로필 조회"""
        pass


@pytest.mark.django_db
class TestProfileUpdate:
    def test_update_profile(self, authenticated_client):
        """프로필 수정"""
        pass

    def test_readonly_field_update_attempt(self, authenticated_client):
        """읽기 전용 필드 수정 시도 (points, membership_level)"""
        pass

    def test_partial_update(self, authenticated_client):
        """부분 수정 (PATCH)"""
        pass


@pytest.mark.django_db
class TestProfilePermission:
    def test_access_other_user_profile(self, authenticated_client, db):
        """다른 사용자 프로필 접근 시도"""
        pass


@pytest.mark.django_db
class TestProfileEmailChange:
    """이메일 변경 테스트 ⚠️ 빠짐!"""

    def test_email_change_not_allowed(self, authenticated_client):
        """이메일 변경 불가 (또는 재인증 필요)"""
        # UserSerializer의 read_only_fields 확인 필요
        pass
