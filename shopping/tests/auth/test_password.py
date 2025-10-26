import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestPasswordChange:
    def test_change_password_success(self, authenticated_client):
        """정상 비밀번호 변경"""
        pass

    def test_wrong_old_password(self, authenticated_client):
        """잘못된 현재 비밀번호"""
        pass

    def test_new_password_mismatch(self, authenticated_client):
        """새 비밀번호 불일치"""
        pass

    def test_same_as_old_password(self, authenticated_client):
        """현재 비밀번호와 동일한 새 비밀번호"""
        pass

    def test_weak_new_password(self, authenticated_client):
        """약한 새 비밀번호"""
        pass

    def test_login_with_new_password(self, api_client, authenticated_client):
        """변경 후 새 비밀번호로 로그인"""
        pass


@pytest.mark.django_db
class TestPasswordChangeTokens:
    """비밀번호 변경 후 토큰 처리 ⚠️ 빠짐!"""

    def test_old_tokens_still_valid_after_password_change(self, authenticated_client):
        """비밀번호 변경 후 기존 토큰 사용 가능 여부"""
        # JWT는 비밀번호 변경 후에도 유효기간 내에는 사용 가능함
        # 하지만 보안상 무효화해야 하는지 확인 필요
        pass
