import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestEmailVerificationSend:
    def test_send_verification_email(self, authenticated_client, unverified_user):
        """인증 이메일 발송"""
        pass


@pytest.mark.django_db
class TestEmailVerificationByToken:
    def test_verify_with_valid_token(self, api_client):
        """유효한 UUID 토큰으로 인증"""
        pass

    def test_verify_with_expired_token(self, api_client):
        """만료된 토큰"""
        pass

    def test_verify_with_used_token(self, api_client):
        """이미 사용된 토큰"""
        pass

    def test_verify_with_invalid_uuid(self, api_client):
        """잘못된 UUID 형식"""
        pass


@pytest.mark.django_db
class TestEmailVerificationByCode:
    def test_verify_with_valid_code(self, authenticated_client):
        """유효한 6자리 코드로 인증"""
        pass

    def test_verify_with_wrong_code(self, authenticated_client):
        """잘못된 코드"""
        pass

    def test_case_insensitive_code(self, authenticated_client):
        """대소문자 구분 없음 확인"""
        pass


@pytest.mark.django_db
class TestEmailResend:
    def test_resend_verification_email(self, authenticated_client, unverified_user):
        """인증 이메일 재발송"""
        pass

    def test_resend_rate_limit(self, authenticated_client, unverified_user):
        """재발송 제한 (1분 내)"""
        pass

    def test_resend_already_verified(self, authenticated_client, user):
        """이미 인증된 사용자 재발송 시도"""
        pass


@pytest.mark.django_db
class TestEmailVerificationOnSignup:
    """회원가입 시 자동 발송 테스트 ⚠️ 빠짐!"""

    def test_email_sent_on_signup(self, api_client, db):
        """회원가입하면 자동으로 인증 이메일 발송됨"""
        # RegisterView가 자동으로 EmailVerificationToken 생성 + 이메일 발송
        pass

    def test_token_created_on_signup(self, api_client, db):
        """회원가입 시 EmailVerificationToken 자동 생성"""
        pass
