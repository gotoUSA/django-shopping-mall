"""
JWT 인증 시스템 테스트

이 파일은 회원가입, 로그인, 토큰 갱신 등
인증 관련 모든 기능을 테스트합니다.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from shopping.models.user import User


class AuthenticationTestCase(TestCase):
    """JWT 인증 시스템 전체 테스트"""

    def setUp(self):
        """
        각 테스트 메서드 실행 전에 자동으로 호출되는 초기 설정

        setUp은 TestCase의 특별한 메서드로,
        모든 테스트 전에 깨끗한 환경을 준비합니다.
        """
        # API 클라이언트 생성 (브라우저 역할)
        self.client = APIClient()

        # 테스트용 기본 사용자 데이터
        self.test_user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "TestPass123!",
            "password2": "TestPass123!",  # 비밀번호 확인
            "first_name": "테스트",
            "last_name": "유저",
            "phone_number": "010-1234-5678",
        }

        # 이미 가입된 사용자 생성 (로그인 테스트용)
        self.existing_user = User.objects.create_user(
            username="existing_user",
            email="existing@example.com",
            password="ExistingPass123!",
            first_name="기존",
            last_name="유저",
        )

        # URL 미리 정의 (재사용을 위해)
        self.register_url = reverse("auth-register")
        self.login_url = reverse("auth-login")
        self.logout_url = reverse("auth-logout")
        self.profile_url = reverse("auth-profile")
        self.refresh_url = reverse("token-refresh")
        self.password_change_url = reverse("password-change")
        self.withdraw_url = reverse("auth-withdraw")

    # ========== 회원가입 테스트 ==========

    def test_user_registration_success(self):
        """
        정상적인 회원가입 테스트

        테스트 내용:
        1. 올바른 데이터로 회원가입 요청
        2. 201 Created 응답 확인
        3. JWT 토큰 발급 확인
        4. 데이터베이스에 사용자 생성 확인
        """
        # API 요청 보내기
        response = self.client.post(self.register_url, data=self.test_user_data, format="json")

        # 응답 상태 코드 확인 (201 = created)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 응답 데이터 확인
        response_data = response.json()

        # JWT 토큰이 발급되었는지 확인
        self.assertIn("tokens", response_data)
        self.assertIn("access", response_data["tokens"])
        self.assertIn("refresh", response_data["tokens"])

        # 사용자 정보가 응답에 포함되었는지 확인
        self.assertIn("user", response_data)
        self.assertEqual(response_data["user"]["username"], "testuser")

        # 데이터베이스에 실제로 사용자가 생성되었는지 확인
        user_exists = User.objects.filter(email="test@example.com").exists()
        self.assertTrue(user_exists)

        # 생성된 사용자 정보 확인
        created_user = User.objects.get(email="test@example.com")
        self.assertEqual(created_user.first_name, "테스트")
        self.assertEqual(created_user.last_name, "유저")
        self.assertEqual(created_user.phone_number, "010-1234-5678")

    def test_user_registration_duplicate_email(self):
        """
        중복 이메일로 회원가입 시도 테스트

        테스트 내용:
        1. 이미 존재하는 이메일로 회원가입 시도
        2. 400 Bad Request 응답 확인
        3. 적절한 에러 메시지 확인
        """
        # 중복 이메일 데이터 준비
        duplicate_data = self.test_user_data.copy()
        duplicate_data["email"] = "existing@example.com"  # 이미 존재하는 이메일
        duplicate_data["username"] = "newusername"  # 다른 username

        # API 요청
        response = self.client.post(self.register_url, data=duplicate_data, format="json")

        # 실패 응답 확인 (400 = Bad Request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # 에러 메시지 확인
        response_data = response.json()
        self.assertIn("email", response_data)
        self.assertIn("이미 사용중인 이메일", response_data["email"][0])

    def test_user_registration_password_mismatch(self):
        """
        비밀번호 불일치로 회원가입 실패 테스트

        테스트 내용:
        1. password와 password2가 다른 경우
        2. 400 Bad Request 응답 확인
        3. 비밀번호 불일치 에러 메시지 확인
        """
        # 비밀번호 불일치 데이터
        mismatch_data = self.test_user_data.copy()
        mismatch_data["password2"] = "DifferentPass123!"

        response = self.client.post(self.register_url, data=mismatch_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn("password", response_data)
        self.assertIn("비밀번호가 일치하지 않습니다", str(response_data["password"]))

    def test_user_registration_weak_password(self):
        """
        약한 비밀번호로 회원가입 실패 테스트

        테스트 내용:
        1. 너무 간단한 비밀번호 사용
        2. Django 비밀번호 검증 실패 확인
        """
        weak_password_data = self.test_user_data.copy()
        weak_password_data["password"] = "1234"
        weak_password_data["password2"] = "1234"

        response = self.client.post(self.register_url, data=weak_password_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.json())

    # ========== 로그인 테스트 ==========

    def test_user_login_success(self):
        """
        정상적인 로그인 테스트

        테스트 내용:
        1. 올바른 인증정보로 로그인
        2. JWT 토큰 발급 확인
        3. 마지막 로그인 시간 업데이트 확인
        """
        login_data = {"username": "existing_user", "password": "ExistingPass123!"}

        # 로그인 전 마지막 로그인 시간 저장
        old_last_login = self.existing_user.last_login

        response = self.client.post(self.login_url, data=login_data, format="json")

        # 성공 응답 확인
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()

        # JWT 토큰 발급 확인
        self.assertIn("access", response_data)
        self.assertIn("refresh", response_data)

        # 사용자 정보 확인
        self.assertIn("user", response_data)
        self.assertEqual(response_data["user"]["username"], "existing_user")

        # 마지막 로그인 시간이 업데이트되었는지 확인
        self.existing_user.refresh_from_db  # DB에서 최신 정보 가져오기
        if old_last_login:  # None이 아닌 경우만 비교
            self.assertGreater(self.existing_user.last_login, old_last_login)

    def test_user_login_wrong_password(self):
        """
        잘못된 비밀번호로 로그인 실패 테스트
        """
        login_data = {"username": "existing_user", "password": "WrongPassword123!"}

        response = self.client.post(self.login_url, data=login_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn("아이디 또는 비밀번호가 올바르지 않습니다.", str(response_data))

    def test_user_login_nonexistent_user(self):
        """
        존재하지 않는 사용자로 로그인 실패 테스트
        """
        login_data = {"username": "nonexistent_user", "password": "SomePassword123!"}

        response = self.client.post(self.login_url, data=login_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_login_withdrawn_user(self):
        """
        탈퇴한 회원으로 로그인 시도 테스트
        """
        # 사용자를 탈퇴 상태로 변경
        withdrawn_user = User.objects.create_user(
            username="withdrawn_user",
            email="withdrawn@example.com",
            password="WithdrawnPass123!",
        )
        withdrawn_user.is_withdrawn = True
        withdrawn_user.withdrawn_at = timezone.now()
        withdrawn_user.save()

        login_data = {"username": "withdrawn_user", "password": "WithdrawnPass123!"}

        response = self.client.post(self.login_url, data=login_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("탈퇴한 회원입니다.", str(response.json()))

    # ========== 토큰 관련 테스트 ==========

    def test_token_refresh(self):
        """
        토큰 갱신 테스트

        테스트 내용:
        1. Refresh Token으로 새로운 Access Token 발급
        2. 정상적으로 갱신되는지 확인
        """
        # 먼저 로그인하여 토큰 발급
        login_data = {"username": "existing_user", "password": "ExistingPass123!"}
        login_response = self.client.post(self.login_url, login_data)
        refresh_token = login_response.json()["refresh"]

        # 토큰 갱신 요청
        refresh_data = {"refresh": refresh_token}
        response = self.client.post(self.refresh_url, data=refresh_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()

        # 새로운 Access Token이 발급되었는지 확인
        self.assertIn("access", response_data)
        self.assertIsNotNone(response_data["access"])

        # ROTATE_REFRESH_TOKENS가 True이면 새로운 Refresh Token도 발급
        if "refresh" in response_data:
            self.assertIsNotNone(response_data["refresh"])

    def test_token_refresh_with_invalid_token(self):
        """
        잘못된 Refresh Token으로 갱신 실패 테스트
        """
        invalid_refresh_data = {"refresh": "invalid_token_string"}

        response = self.client.post(self.refresh_url, data=invalid_refresh_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ========== 로그아웃 테스트 ==========

    def test_user_logout_success(self):
        """
        정상적인 로그아웃 테스트

        테스트 내용:
        1. 로그인 후 로그아웃
        2. Refresh Token이 블랙리스트에 추가되는지 확인
        3. 블랙리스트된 토큰으로 접근 불가 확인
        """
        # 로그인
        login_data = {"username": "existing_user", "password": "ExistingPass123!"}
        login_response = self.client.post(self.login_url, login_data)
        tokens = login_response.json()

        # 인증 헤더 설정
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')

        # 로그아웃 요청
        logout_data = {"refresh": tokens["refresh"]}
        response = self.client.post(self.logout_url, data=logout_data, foramt="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("로그아웃 되었습니다", response.json()["message"])

        # 블랙리스트된 refresh token으로 갱신 시도 (실패해야함)
        refresh_response = self.client.post(self.refresh_url, data={"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_logout_without_token(self):
        """
        토큰 없이 로그아웃 시도 테스트
        """
        # 인증 없이 로그아웃 시도
        response = self.client.post(self.logout_url)

        # DRF는 인증되지 않은 경우 401 또는 403을 반환할 수 있음
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

        # 추가 검증: 어떤 상태코드든 성공하면 안 됨
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    # ========== 프로필 관련 테스트 ==========

    def test_get_profile_authenticated(self):
        """
        인증된 사용자의 프로필 조회 테스트
        """
        # 로그인하여 토큰 획득
        self._login_user()

        # 프로필 조회
        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()

        # 프로필 정보 확인
        self.assertEqual(response_data["username"], "existing_user")
        self.assertEqual(response_data["email"], "existing@example.com")

        # 민감한 정보는 포함되지 않아야 함
        self.assertNotIn("password", response_data)

    def test_get_profile_unauthenticated(self):
        """
        인증 없이 프로필 조회 실패 테스트
        """
        response = self.client.get(self.profile_url)

        # DRF는 인증되지 않은 경우 401 또는 403을 반환할 수 있음
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

        # 추가 검증: 어떤 경우든 프로필 데이터는 반환되면 안 됨
        self.assertNotIn("username", response.json() if response.json() else {})

    def test_update_profile(self):
        """
        프로필 수정 테스트 (PATCH)
        """
        self._login_user()

        # 수정할 데이터
        update_data = {
            "first_name": "수정된",
            "last_name": "이름",
            "phone_number": "010-9999-8888",
        }

        response = self.client.patch(self.profile_url, data=update_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # DB에서 확인
        self.existing_user.refresh_from_db()
        self.assertEqual(self.existing_user.first_name, "수정된")
        self.assertEqual(self.existing_user.last_name, "이름")
        self.assertEqual(self.existing_user.phone_number, "010-9999-8888")

    # ========== 비밀번호 변경 테스트 ==========

    def test_password_change_success(self):
        """
        비밀번호 변경 성공 테스트
        """
        self._login_user()

        password_data = {
            "old_password": "ExistingPass123!",
            "new_password": "NewSecurePass456!",
            "new_password2": "NewSecurePass456!",
        }

        response = self.client.post(self.password_change_url, data=password_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 새 비밀번호로 로그인 테스트
        self.client.credentials()  # 인증 헤더 제거

        new_login_data = {"username": "existing_user", "password": "NewSecurePass456!"}

        login_response = self.client.post(self.login_url, new_login_data)
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

    def test_password_change_wrong_old_password(self):
        """
        잘못된 현재 비밀번호로 변경 실패 테스트
        """
        self._login_user()

        password_data = {
            "old_password": "WrongOldPassword!",
            "new_password": "NewSecurePass456!",
            "new_password2": "NewSecurePass456!",
        }

        response = self.client.post(self.password_change_url, data=password_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("현재 비밀번호가 올바르지 않습니다", str(response.json()))

    # ========== 회원 탈퇴 테스트 ==========

    def test_user_withdrawal_success(self):
        """
        회원 탈퇴 성공 테스트
        """
        self._login_user()

        withdrawal_data = {"password": "ExistingPass123!"}

        response = self.client.post(self.withdraw_url, data=withdrawal_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # DB에서 탈퇴 상태 확인
        self.existing_user.refresh_from_db()
        self.assertTrue(self.existing_user.is_withdrawn)
        self.assertIsNotNone(self.existing_user.withdrawn_at)
        self.assertFalse(self.existing_user.is_active)

        # 탈퇴한 계정으로 로그인 시도 (실패해야 함)
        self.client.credentials()  # 인증 헤더 제거

        login_data = {"username": "existing_user", "password": "ExistingPass123!"}

        login_response = self.client.post(self.login_url, login_data)
        self.assertEqual(login_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_withdrawal_wrong_password(self):
        """
        잘못된 비밀번호로 회원 탈퇴 실패 테스트
        """
        self._login_user()

        withdrawal_data = {"password": "WrongPassword!"}

        response = self.client.post(self.withdraw_url, data=withdrawal_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("비밀번호가 올바르지 않습니다", str(response.json()))

    # ========== 헬퍼 메서드 ==========

    def _login_user(self):
        """
        헬퍼 메서드: 테스트용 사용자 로그인

        여러 테스트에서 반복되는 로그인 과정을
        간단하게 처리하기 위한 내부 메서드
        """
        login_data = {"username": "existing_user", "password": "ExistingPass123!"}

        response = self.client.post(self.login_url, login_data)
        tokens = response.json()

        # 인증 헤더 설정
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')

        return tokens


class TokenExpiryTestCase(TestCase):
    """토큰 만료 관련 테스트 (선택적)"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="token_test_user", email="token@test.com", password="TokenTest123!")

    def test_expired_access_token(self):
        """
        만료된 Access Token으로 접근 실패 테스트

        주의: 이 테스트는 설정을 임시로 변경해야 하므로
        실제 환경에서는 신중하게 사용해야 합니다.
        """
        # 매우 짧은 수명의 토큰 생성 (테스트용)
        from rest_framework_simplejwt.tokens import AccessToken

        # 이미 만료된 토큰 생성
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=timedelta(seconds=-1))  # 1초 전에 만료

        # 만료된 토큰으로 프로필 조회 시도
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token)}")

        response = self.client.get(reverse("auth-profile"))

        # DRF는 만료된 토큰에 대해 401 또는 403을 반환할 수 있음
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

        # 추가 검증: 어떤 경우든 성공하면 안 됨
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)
