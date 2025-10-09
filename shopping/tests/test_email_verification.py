from django.test import TestCase
from django.urls import reverse
from django.core import mail
from rest_framework import status
from rest_framework.test import APIClient
from shopping.models.user import User
from shopping.models.email_verification import EmailVerificationToken
from django.utils import timezone
from datetime import timedelta
import re


class EmailVerificationModelTest(TestCase):
    """이메일 인증 토큰 모델 테스트"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPass123!",
            first_name="테스트",
            last_name="유저",
        )

    def test_create_verification_token(self):
        """인증 토큰 생성 테스트"""
        token = EmailVerificationToken.objects.create(user=self.user)

        # UUID 토큰이 생성되었는지 확인
        self.assertIsNotNone(token.token)
        self.assertEqual(len(str(token.token)), 36)  # UUID 형식

        # 6자리 인증 코드 확인 (영문+숫자)
        self.assertIsNotNone(token.verification_code)
        self.assertEqual(len(token.verification_code), 6)
        self.assertTrue(bool(re.fullmatch(r"[A-Z0-9]{6}", token.verification_code)))

        # 기본값 확인
        self.assertFalse(token.is_used)
        self.assertIsNotNone(token.created_at)

    def test_token_expiry_check(self):
        """토큰 만료 체크 테스트"""
        token1 = EmailVerificationToken.objects.create(user=self.user)
        token2 = EmailVerificationToken.objects.create(user=self.user)

        # UUID는 고유해야함
        self.assertNotEqual(token1.token, token2.token)
        # 인증코드도 대부분 달라야함 (같을 확률은 매우 낮음)
        # 테스트 안정성을 위해 이부분은 나중에

    def test_token_expiry_check(self):
        """토큰 만료 체크 테스트"""
        # 24시간 전에 생성된 토큰
        old_token = EmailVerificationToken.objects.create(user=self.user)
        old_token.created_at = timezone.now() - timedelta(hours=25)
        old_token.save()

        # 만료 확인
        self.assertTrue(old_token.is_expired())

        # 방금 생성된 토큰
        new_token = EmailVerificationToken.objects.create(user=self.user)
        self.assertFalse(new_token.is_expired())

        # 23시간 전 토큰 (아직 유효)
        valid_token = EmailVerificationToken.objects.create(user=self.user)
        valid_token.created_at = timezone.now() - timedelta(hours=23)
        valid_token.save()
        self.assertFalse(valid_token.is_expired())


class EmailVerificationAPITest(TestCase):
    """이메일 인증 API 테스트"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPass123!",
            first_name="테스트",
            last_name="유저",
        )

        # URL 정의
        self.send_url = reverse("email-verification-send")
        self.verify_url = reverse("email-verification-verify")
        self.resend_url = reverse("email-verification-resend")

    def test_send_verification_email_authenticated(self):
        """로그인한 사용자의 인증 이메일 발송 테스트"""
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.send_url)

        # 응답 확인
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)
        self.assertIn("인증 이메일", response.data["message"])

        # 토큰 생성 확인
        token_exists = EmailVerificationToken.objects.filter(
            user=self.user, is_used=False
        ).exists()
        self.assertTrue(token_exists)

        # 이메일 발송 확인 (테스트 환경에서는 실제 발송 안함)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("이메일 인증", mail.outbox[0].subject)

    def test_send_verification_email_unauthenticated(self):
        """비로그인 사용자는 발송 불가 테스트"""
        response = self.client.post(self.send_url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_send_verification_email_already_verified(self):
        """이미 인증된 사용자 테스트"""
        self.user.is_email_verified = True
        self.user.save()

        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.send_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # ErrorDetail 처리
        error_str = (
            str(response.data["error"][0])
            if isinstance(response.data["error"], list)
            else str(response.data["error"])
        )
        self.assertIn("이미 이메일 인증이 완료되었습니다", error_str)

    def test_verify_email_with_uuid_token(self):
        """UUID 토큰으로 이메일 인증 테스트"""
        # 토큰 생성
        token = EmailVerificationToken.objects.create(user=self.user)

        # 인증 요청
        response = self.client.get(self.verify_url, {"token": str(token.token)})

        # 응답 확인
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("이메일 인증이 완료되었습니다", response.data["message"])

        # 사용자 인증 상태 확인
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)

        # 토큰 사용 처리 확인
        token.refresh_from_db()
        self.assertTrue(token.is_used)

    def test_verify_email_with_code(self):
        """6자리 코드로 이메일 인증 테스트"""
        # 토큰 생성
        token = EmailVerificationToken.objects.create(user=self.user)

        # 로그인 필요
        self.client.force_authenticate(user=self.user)

        # 인증 요청
        response = self.client.post(self.verify_url, {"code": token.verification_code})

        # 응답 확인
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("이메일 인증이 완료되었습니다", response.data.get("message", ""))

        # 사용자 인증 상태 확인
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)

    def test_verify_email_with_invalid_token(self):
        """잘못된 토큰으로 인증 시도 테스트"""
        response = self.client.get(
            self.verify_url, {"token": "invalid-token-12345"}
        )  # UUID 형식이 아닌 토큰

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("유효하지 않은 토큰입니다", response.data["error"])

    def test_verify_email_with_expired_token(self):
        """만료된 토큰으로 인증 시도 테스트"""
        # 만료된 토큰 생성
        token = EmailVerificationToken.objects.create(user=self.user)
        token.created_at = timezone.now() - timedelta(hours=25)
        token.save()

        response = self.client.get(self.verify_url, {"token": str(token.token)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("토큰이 만료되었습니다", response.data.get("error", ""))

    def test_verify_email_with_used_token(self):
        """이미 사용된 토큰으로 인증 시도 테스트"""
        token = EmailVerificationToken.objects.create(user=self.user)
        token.is_used = True
        token.save()

        response = self.client.get(self.verify_url, {"token": str(token.token)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("이미 사용된 토큰입니다", response.data.get("error", ""))

    def test_resend_verification_email(self):
        """인증 이메일 재발송 테스트"""
        self.client.force_authenticate(user=self.user)

        # 첫 번째 발송
        response1 = self.client.post(self.resend_url)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)

        # 즉시 재발송 시도 (1분 제한)
        response2 = self.client.post(self.resend_url)
        self.assertEqual(response2.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        # ErrorDetail을 문자열로 변환
        error_str = (
            str(response2.data["error"][0])
            if isinstance(response2.data["error"], list)
            else str(response2.data["error"])
        )
        self.assertIn("1분", error_str)

        # 이메일은 1개만 발송되어야 함
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_after_one_minute(self):
        """1분 후 재발송 가능 테스트"""
        self.client.force_authenticate(user=self.user)

        # 첫 번째 토큰 생성
        token1 = EmailVerificationToken.objects.create(user=self.user)
        token1.created_at = timezone.now() - timedelta(minutes=2)
        token1.save()

        # 재발송
        response = self.client.post(self.resend_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 이전 토큰은 무효화되어야 함
        token1.refresh_from_db()
        self.assertTrue(token1.is_used)

        # 새 토큰이 생성되어야 함
        new_token_exists = (
            EmailVerificationToken.objects.filter(user=self.user, is_used=False)
            .exclude(id=token1.id)
            .exists()
        )
        self.assertTrue(new_token_exists)
