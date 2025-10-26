import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestLoginSuccess:
    def test_login_with_valid_credentials(self, api_client, user):
        """정상 로그인"""
        # TODO: 올바른 username/password로 로그인
        pass


@pytest.mark.django_db
class TestLoginFailure:
    def test_login_wrong_password(self, api_client, user):
        """잘못된 비밀번호"""
        pass

    def test_login_nonexistent_user(self, api_client):
        """존재하지 않는 사용자"""
        pass

    def test_login_withdrawn_user(self, api_client, withdrawn_user):
        """탈퇴한 사용자"""
        pass

    def test_login_inactive_user(self, api_client, inactive_user):
        """비활성화된 사용자"""
        pass


@pytest.mark.django_db
class TestLoginValidation:
    def test_empty_credentials(self, api_client):
        """빈 username/password"""
        pass

    def test_case_sensitive(self, api_client, user):
        """대소문자 구분 확인"""
        pass


@pytest.mark.django_db
class TestLoginMetadata:
    def test_last_login_updated(self, api_client, user):
        """마지막 로그인 시간 업데이트"""
        pass
