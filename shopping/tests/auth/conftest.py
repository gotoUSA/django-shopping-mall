"""
Auth 테스트 전용 Fixture

전역 conftest.py의 fixture는 그대로 사용하고,
auth 테스트에만 필요한 특화된 fixture를 정의합니다.

사용 가능한 전역 fixture:
- api_client: DRF APIClient
- user: 기본 사용자 (인증 완료)
- seller_user: 판매자 사용자
- unverified_user: 이메일 미인증 사용자
- inactive_user: 비활성화된 사용자
- withdrawn_user: 탈퇴한 사용자
- authenticated_client: 인증된 클라이언트
- seller_authenticated_client: 판매자 인증 클라이언트
- get_tokens: JWT 토큰 발급 헬퍼
- user_factory: 사용자 생성 팩토리
"""

import base64
import json
from datetime import timedelta
from datetime import timezone as dt_timezone

import pytest
from django.contrib.sites.models import Site
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from allauth.socialaccount.models import SocialApp
from shopping.models.email_verification import EmailVerificationToken


# ==========================================
# 1. JWT 토큰 관련 Fixture
# ==========================================


@pytest.fixture
def expired_access_token(user):
    """
    만료된 Access Token (30분 경과)

    사용 예시:
        def test_expired_token(api_client, expired_access_token):
            api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired_access_token}")
            response = api_client.get("/api/auth/profile/")
            assert response.status_code == 401
    """
    token = AccessToken.for_user(user)
    # 30분 + 1초 전에 만료되도록 설정
    token.set_exp(lifetime=timedelta(minutes=-30, seconds=-1))
    return str(token)


@pytest.fixture
def expired_refresh_token(user):
    """
    만료된 Refresh Token (7일 경과)

    사용 예시:
        def test_refresh_with_expired_token(api_client, expired_refresh_token):
            response = api_client.post("/api/auth/token/refresh/",
                                      {"refresh": expired_refresh_token})
            assert response.status_code == 401
    """
    token = RefreshToken.for_user(user)
    # 7일 + 1초 전에 만료되도록 설정
    token.set_exp(lifetime=timedelta(days=-7, seconds=-1))
    return str(token)


@pytest.fixture
def invalid_token():
    """
    형식이 잘못된 JWT 토큰

    완전히 잘못된 문자열 (JWT 형식이 아님)

    사용 예시:
        def test_malformed_token(api_client, invalid_token):
            api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {invalid_token}")
            response = api_client.get("/api/auth/profile/")
            assert response.status_code == 401
    """
    return "this_is_not_a_valid_jwt_token_12345"


@pytest.fixture
def tampered_token(user):
    """
    서명이 조작된 JWT 토큰 (보안 테스트용)

    정상적인 JWT 구조를 가지지만 서명(signature)이 변조된 토큰
    JWT는 header.payload.signature 구조인데,
    payload를 변경하고 서명은 그대로 두면 검증 실패

    사용 예시:
        def test_tampered_token(api_client, tampered_token):
            api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tampered_token}")
            response = api_client.get("/api/auth/profile/")
            assert response.status_code == 401
    """
    # 정상 토큰 생성
    token = AccessToken.for_user(user)
    token_str = str(token)

    # JWT는 header.payload.signature 형태
    parts = token_str.split(".")

    if len(parts) == 3:
        header, payload, signature = parts

        # payload 디코딩 (padding 추가)
        payload_padded = payload + "=" * (4 - len(payload) % 4)
        try:
            decoded_payload = base64.urlsafe_b64decode(payload_padded)
            payload_data = json.loads(decoded_payload)

            # user_id를 변조 (다른 사용자 ID로 변경)
            payload_data["user_id"] = 99999  # 존재하지 않는 ID

            # 변조된 payload를 다시 인코딩
            tampered_payload_bytes = json.dumps(payload_data).encode("utf-8")
            tampered_payload = base64.urlsafe_b64encode(tampered_payload_bytes).decode("utf-8").rstrip("=")

            # 변조된 토큰 생성 (서명은 그대로)
            tampered = f"{header}.{tampered_payload}.{signature}"
            return tampered

        except Exception:
            # 디코딩 실패 시 간단한 변조
            return f"{header}.{payload}modified.{signature}"

    # 형식이 이상한 경우 기본값
    return token_str + "tampered"


@pytest.fixture
def blacklisted_refresh_token(api_client, get_tokens):
    """
    블랙리스트에 등록된 Refresh Token

    로그아웃 후 무효화된 토큰 (재사용 불가)

    사용 예시:
        def test_use_blacklisted_token(api_client, blacklisted_refresh_token):
            response = api_client.post("/api/auth/token/refresh/",
                                      {"refresh": blacklisted_refresh_token})
            assert response.status_code == 401
    """
    from django.urls import reverse

    tokens = get_tokens
    access_token = tokens["access"]
    refresh_token = tokens["refresh"]

    # 인증 설정
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    # 로그아웃하여 refresh token을 블랙리스트에 추가
    logout_url = reverse("auth-logout")
    api_client.post(logout_url, {"refresh": refresh_token})

    # 인증 헤더 제거 (다음 테스트를 위해)
    api_client.credentials()

    return refresh_token


# ==========================================
# 2. 이메일 인증 관련 Fixture
# ==========================================


@pytest.fixture
def verification_token(unverified_user):
    """
    유효한 이메일 인증 토큰

    방금 생성되어 아직 사용되지 않은 정상 토큰 (24시간 이내)

    사용 예시:
        def test_verify_email_success(api_client, verification_token):
            response = api_client.get("/api/auth/email/verify/",
                                     {"token": str(verification_token.token)})
            assert response.status_code == 200
    """
    return EmailVerificationToken.objects.create(user=unverified_user)


@pytest.fixture
def expired_verification_token(unverified_user):
    """
    만료된 이메일 인증 토큰 (24시간 경과)

    사용 예시:
        def test_verify_expired_token(api_client, expired_verification_token):
            response = api_client.get("/api/auth/email/verify/",
                                     {"token": str(expired_verification_token.token)})
            assert response.status_code == 400
            assert "만료" in response.data["error"]
    """
    token = EmailVerificationToken.objects.create(user=unverified_user)
    # 24시간 + 1초 전으로 설정
    token.created_at = timezone.now() - timedelta(hours=24, seconds=1)
    token.save()
    return token


@pytest.fixture
def used_verification_token(unverified_user):
    """
    이미 사용된 이메일 인증 토큰

    인증 완료된 토큰 (재사용 불가)

    사용 예시:
        def test_reuse_verification_token(api_client, used_verification_token):
            response = api_client.get("/api/auth/email/verify/",
                                     {"token": str(used_verification_token.token)})
            assert response.status_code == 400
            assert "이미 사용" in response.data["error"]
    """
    token = EmailVerificationToken.objects.create(user=unverified_user)
    # 사용됨 처리
    token.mark_as_used()
    return token


@pytest.fixture
def recent_verification_token(unverified_user):
    """
    방금 생성된 인증 토큰 (1분 미만)

    재발송 제한 테스트용 (1분 이내 재발송 불가)

    사용 예시:
        def test_resend_too_soon(api_client, unverified_user, recent_verification_token):
            # recent_verification_token이 이미 존재하므로
            response = api_client.post("/api/auth/email/resend/")
            assert response.status_code == 400
            assert "1분 후" in response.data["error"]
    """
    token = EmailVerificationToken.objects.create(user=unverified_user)
    # 30초 전에 생성 (1분 미만)
    token.created_at = timezone.now() - timedelta(seconds=30)
    token.save()
    return token


@pytest.fixture
def verification_token_factory(db):
    """
    이메일 인증 토큰 팩토리 (유연한 토큰 생성)

    다양한 상태의 토큰을 쉽게 생성

    사용 예시:
        def test_multiple_tokens(verification_token_factory, unverified_user):
            # 유효한 토큰
            valid_token = verification_token_factory(user=unverified_user)

            # 만료된 토큰
            expired = verification_token_factory(
                user=unverified_user,
                hours_ago=25
            )

            # 사용된 토큰
            used = verification_token_factory(
                user=unverified_user,
                is_used=True
            )
    """

    def _create_token(user, hours_ago=0, minutes_ago=0, is_used=False):
        """
        Args:
            user: 사용자 객체
            hours_ago: 몇 시간 전에 생성되었는지
            minutes_ago: 몇 분 전에 생성되었는지
            is_used: 사용 여부
        """
        token = EmailVerificationToken.objects.create(user=user)

        # 생성 시간 조정
        if hours_ago > 0 or minutes_ago > 0:
            token.created_at = timezone.now() - timedelta(hours=hours_ago, minutes=minutes_ago)
            token.save()

        # 사용됨 처리
        if is_used:
            token.mark_as_used()

        return token

    return _create_token


# ==========================================
# 3. 소셜 로그인 관련 Fixture
# ==========================================


@pytest.fixture
def social_site():
    """
    Django Site 객체 (소셜 앱에 필요)

    allauth는 django.contrib.sites를 사용하므로 필수
    """
    site, _ = Site.objects.get_or_create(id=1, defaults={"domain": "testserver", "name": "testserver"})
    return site


@pytest.fixture
def social_app_google(db, social_site):
    """
    Google 소셜 앱 설정

    테스트용 Google OAuth 앱 설정

    사용 예시:
        def test_google_login(api_client, social_app_google):
            # social_app_google이 설정된 상태에서 테스트
            response = api_client.post("/api/auth/social/google/", {...})
    """
    # 기존 Google 앱 모두 삭제 (중복 방지)
    SocialApp.objects.filter(provider="google").delete()

    app = SocialApp.objects.create(
        provider="google",
        name="Google Test",
        client_id="test_google_client_id_12345",
        secret="test_google_secret_67890",
    )
    app.sites.add(social_site)
    return app


@pytest.fixture
def social_app_kakao(db, social_site):
    """
    Kakao 소셜 앱 설정

    테스트용 Kakao OAuth 앱 설정

    사용 예시:
        def test_kakao_login(api_client, social_app_kakao):
            response = api_client.post("/api/auth/social/kakao/", {...})
    """
    SocialApp.objects.filter(provider="kakao").delete()

    app = SocialApp.objects.create(
        provider="kakao",
        name="Kakao Test",
        client_id="test_kakao_rest_api_key_12345",
        secret="test_kakao_secret_67890",
    )
    app.sites.add(social_site)
    return app


@pytest.fixture
def social_app_naver(db, social_site):
    """
    Naver 소셜 앱 설정

    테스트용 Naver OAuth 앱 설정

    사용 예시:
        def test_naver_login(api_client, social_app_naver):
            response = api_client.post("/api/auth/social/naver/", {...})
    """
    SocialApp.objects.filter(provider="naver").delete()

    app = SocialApp.objects.create(
        provider="naver",
        name="Naver Test",
        client_id="test_naver_client_id_12345",
        secret="test_naver_secret_67890",
    )
    app.sites.add(social_site)
    return app


@pytest.fixture
def mock_google_oauth_data():
    """
    Google OAuth 응답 Mock 데이터

    Google에서 받는 사용자 정보 형식

    사용 예시:
        def test_google_oauth(mocker, mock_google_oauth_data):
            mock = mocker.patch("allauth.socialaccount.providers.google...")
            mock.return_value = mock_google_oauth_data
    """
    return {
        "id": "google_user_id_123456",
        "email": "testuser@gmail.com",
        "verified_email": True,
        "name": "Test User",
        "given_name": "Test",
        "family_name": "User",
        "picture": "https://lh3.googleusercontent.com/a/default-user",
        "locale": "ko",
    }


@pytest.fixture
def mock_kakao_oauth_data():
    """
    Kakao OAuth 응답 Mock 데이터

    Kakao에서 받는 사용자 정보 형식

    사용 예시:
        def test_kakao_oauth(mocker, mock_kakao_oauth_data):
            mock = mocker.patch("allauth.socialaccount.providers.kakao...")
            mock.return_value = mock_kakao_oauth_data
    """
    return {
        "id": 123456789,
        "connected_at": "2025-01-28T10:00:00Z",
        "kakao_account": {
            "profile_needs_agreement": False,
            "profile": {"nickname": "테스트유저", "profile_image_url": "http://k.kakaocdn.net/img.jpg"},
            "has_email": True,
            "email_needs_agreement": False,
            "is_email_valid": True,
            "is_email_verified": True,
            "email": "testuser@kakao.com",
        },
    }


@pytest.fixture
def mock_naver_oauth_data():
    """
    Naver OAuth 응답 Mock 데이터

    Naver에서 받는 사용자 정보 형식

    사용 예시:
        def test_naver_oauth(mocker, mock_naver_oauth_data):
            mock = mocker.patch("allauth.socialaccount.providers.naver...")
            mock.return_value = mock_naver_oauth_data
    """
    return {
        "resultcode": "00",
        "message": "success",
        "response": {
            "id": "naver_user_id_12345",
            "email": "testuser@naver.com",
            "name": "테스트",
            "nickname": "테스터",
            "profile_image": "https://ssl.pstatic.net/static/pwe/address/img_profile.png",
            "age": "20-29",
            "gender": "M",
            "birthday": "01-28",
            "birthyear": "1990",
        },
    }


# ==========================================
# 4. 유틸리티 Fixture
# ==========================================


@pytest.fixture
def mock_time():
    """
    시간 고정 유틸리티 (pytest-freezegun 대체)

    특정 시간으로 고정하여 시간 의존 테스트 수행

    사용 예시:
        def test_with_fixed_time(mock_time):
            frozen_time = datetime(2025, 1, 28, 10, 0, 0, tzinfo=dt_timezone.utc)
            with mock_time(frozen_time):
                # 이 블록 안에서는 시간이 고정됨
                token = EmailVerificationToken.objects.create(...)
                assert token.created_at == frozen_time
    """
    from unittest.mock import patch
    from contextlib import contextmanager

    @contextmanager
    def _freeze_time(frozen_datetime):
        with patch("django.utils.timezone.now", return_value=frozen_datetime):
            yield frozen_datetime

    return _freeze_time


# ==========================================
# 5. 비밀번호 재설정 관련 Fixture
# ==========================================

from shopping.models.password_reset import PasswordResetToken


@pytest.fixture
def password_reset_token(user):
    """
    유효한 비밀번호 재설정 토큰

    방금 생성되어 아직 사용되지 않은 정상 토큰 (24시간 이내)

    사용 예시:
        def test_reset_password(api_client, password_reset_token):
            response = api_client.post("/api/auth/password/reset/confirm/", {
                "token": str(password_reset_token.token),
                "new_password": "NewPass123!",
                "new_password2": "NewPass123!"
            })
            assert response.status_code == 200
    """
    return PasswordResetToken.objects.create(user=user)


@pytest.fixture
def expired_password_reset_token(user):
    """
    만료된 비밀번호 재설정 토큰 (24시간 경과)

    사용 예시:
        def test_reset_with_expired_token(api_client, expired_password_reset_token):
            response = api_client.post("/api/auth/password/reset/confirm/", {
                "token": str(expired_password_reset_token.token),
                "new_password": "NewPass123!",
                "new_password2": "NewPass123!"
            })
            assert response.status_code == 400
            assert "만료" in response.data
    """
    token = PasswordResetToken.objects.create(user=user)
    # 24시간 + 1초 전으로 설정
    token.created_at = timezone.now() - timedelta(hours=24, seconds=1)
    token.save()
    return token
