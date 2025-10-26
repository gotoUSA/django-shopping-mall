import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestRegistrationSuccess:
    """정상 회원가입 테스트"""

    def test_register_with_valid_data(self, api_client):
        """올바른 데이터로 회원가입 성공"""
        # TODO: 정상 회원가입 + JWT 토큰 발급 확인
        pass


@pytest.mark.django_db
class TestDuplicateValidation:
    """중복 검증 테스트"""

    def test_duplicate_username(self, api_client, user):
        """중복 username으로 가입 실패"""
        # TODO: 이미 존재하는 username으로 가입 시도
        pass

    def test_duplicate_email(self, api_client, user):
        """중복 email으로 가입 실패"""
        # TODO: 이미 존재하는 email로 가입 시도
        pass


@pytest.mark.django_db
class TestEmailValidation:
    """이메일 형식 검증"""

    def test_invalid_email_format_no_at(self, api_client):
        """@ 없는 이메일"""
        # TODO: abc.com 형태의 이메일 테스트
        pass

    def test_invalid_email_format_no_domain(self, api_client):
        """도메인 없는 이메일"""
        # TODO: abc@ 형태의 이메일 테스트
        pass

    def test_invalid_email_consecutive_dots(self, api_client):
        """연속된 점"""
        # TODO: test..user@example.com 테스트
        pass


@pytest.mark.django_db
class TestPasswordValidation:
    """비밀번호 검증"""

    def test_short_password(self, api_client):
        """짧은 비밀번호 (8자 미만)"""
        # TODO: 7자 이하 비밀번호 테스트
        pass

    def test_numeric_only_password(self, api_client):
        """숫자만 있는 비밀번호"""
        # TODO: 12345678 같은 비밀번호 테스트
        pass

    def test_password_mismatch(self, api_client):
        """password와 password2 불일치"""
        # TODO: 두 비밀번호가 다른 경우 테스트
        pass


@pytest.mark.django_db
class TestRequiredFields:
    """필수 필드 검증"""

    def test_missing_username(self, api_client):
        """username 누락"""
        # TODO: username 없이 가입 시도
        pass

    def test_missing_email(self, api_client):
        """email 누락"""
        # TODO: email 없이 가입 시도
        pass

    def test_missing_password(self, api_client):
        """password 누락"""
        # TODO: password 없이 가입 시도
        pass


@pytest.mark.django_db
class TestEmptyInputs:
    """빈 문자열 검증"""

    def test_empty_username(self, api_client):
        """빈 username"""
        # TODO: username="" 테스트
        pass

    def test_empty_email(self, api_client):
        """빈 email"""
        # TODO: email="" 테스트
        pass

    def test_whitespace_only(self, api_client):
        """공백만 있는 필드"""
        # TODO: username="   " 테스트
        pass


@pytest.mark.django_db
class TestLongInputs:
    """길이 제한 테스트"""

    def test_username_too_long(self, api_client):
        """username 길이 초과 (150자)"""
        # TODO: 151자 username 테스트
        pass

    def test_email_too_long(self, api_client):
        """email 길이 초과 (254자)"""
        # TODO: 255자 email 테스트
        pass


@pytest.mark.django_db
class TestPhoneValidation:
    """전화번호 형식 검증"""

    def test_invalid_phone_format(self, api_client):
        """잘못된 전화번호 형식"""
        # TODO: 01012345678, 010-1234-567 테스트
        pass

    def test_phone_with_letters(self, api_client):
        """문자가 포함된 전화번호"""
        # TODO: 010-abcd-5678 테스트
        pass


@pytest.mark.django_db
class TestSecurityValidation:
    """보안 테스트 (SQL Injection, XSS)"""

    def test_sql_injection_attempt(self, api_client):
        """SQL Injection 시도"""
        # TODO: username="admin' OR '1'='1" 테스트
        pass

    def test_xss_attempt(self, api_client):
        """XSS 공격 시도"""
        # TODO: username="<script>alert('xss')</script>" 테스트
        pass


@pytest.mark.django_db
class TestRegistrationInitialState:
    """회원가입 후 초기 상태 확인 ⚠️ 빠짐!"""

    def test_initial_email_verified_false(self, api_client):
        """회원가입 직후 is_email_verified=False"""
        pass

    def test_db_user_created(self, api_client):
        """DB에 사용자 실제 생성 확인"""
        pass

    def test_jwt_tokens_issued(self, api_client):
        """회원가입 시 JWT 토큰 자동 발급"""
        pass

    def test_verification_email_sent(self, api_client):
        """회원가입 시 인증 이메일 자동 발송 ⭐ 중요!"""
        # RegisterView에서 자동으로 EmailVerificationToken 생성 + 이메일 발송
        pass

    def test_initial_points_zero(self, api_client):
        """초기 포인트 0 확인"""
        pass

    def test_initial_membership_level(self, api_client):
        """초기 등급 bronze 확인"""
        pass


@pytest.mark.django_db
class TestUsernameSpecialChars:
    """username 특수문자 검증 ⚠️ 빠짐!"""

    def test_username_with_underscore(self, api_client):
        """언더스코어 허용"""
        pass

    def test_username_with_hyphen(self, api_client):
        """하이픈 허용"""
        pass

    def test_username_with_special_chars(self, api_client):
        """특수문자 불허 (@, #, $ 등)"""
        pass

    def test_username_korean(self, api_client):
        """한글 username (허용 여부 확인 필요)"""
        pass
