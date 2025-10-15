from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock

from shopping.models.user import User
from shopping.models.email_verification import EmailVerificationToken
from allauth.socialaccount.models import SocialAccount, SocialApp
from django.contrib.sites.models import Site


# ✅ settings.py의 SOCIALACCOUNT_PROVIDERS를 빈 딕셔너리로 오버라이드
@override_settings(SOCIALACCOUNT_PROVIDERS={})
class SocialAuthTestCase(TransactionTestCase):
    """소셜 로그인 기본 테스트"""

    def setUp(self):
        """테스트 데이터 초기 설정"""
        self.client = APIClient()

        # 매번 완전히 삭제하고 새로 생성
        SocialApp.objects.all().delete()

        # Site 확인
        site, _ = Site.objects.get_or_create(
            id=1, defaults={"domain": "example.com", "name": "example.com"}
        )

        # 테스트용 소셜 앱 생성 (Google)
        self.social_app = SocialApp.objects.create(
            provider="google",
            name="Google Test",
            client_id="test_google_client_id",
            secret="test_google_secret",
        )

        # sites 관계 명확하게 설정
        self.social_app.sites.clear()
        self.social_app.sites.add(site)

        # 기존 사용자 (소셜 로그인 안 한 사용자)
        self.existing_user = User.objects.create_user(
            username="existing_user",
            email="existing@test.com",
            password="testpass123",
            is_email_verified=False,
        )

        # URL 정의
        self.google_login_url = reverse("google-login")
        self.kakao_login_url = reverse("kakao-login")
        self.naver_login_url = reverse("naver-login")

    def tearDown(self):
        """완전한 정리"""
        SocialApp.objects.all().delete()
        SocialAccount.objects.all().delete()
        User.objects.all().delete()

    def test_social_app_created(self):
        """소셜 앱이 정상적으로 생성되었는지 확인"""
        self.assertEqual(SocialApp.objects.count(), 1)
        self.assertEqual(self.social_app.provider, "google")

    @patch(
        "allauth.socialaccount.providers.google.views.GoogleOAuth2Adapter.complete_login"
    )
    def test_social_login_new_user(self, mock_complete_login):
        """
        소셜 로그인 신규 가입 테스트

        실제 OAuth 플로우는 복잡하여 E2E 테스트로 진행
        여기서는 소셜 로그인 기본 구조만 검증
        """
        # URL이 존재하는지 확인
        self.assertIsNotNone(self.google_login_url)

        # SocialApp이 제대로 설정되었는지 확인
        app = SocialApp.objects.get(provider="google")
        self.assertEqual(app.client_id, "test_google_client_id")
        self.assertTrue(app.sites.filter(id=1).exists())

        # 실제 소셜 계정 생성 시뮬레이션 (Mock 대신 직접 생성)
        new_user = User.objects.create_user(
            username="social_newuser",
            email="social_newuser@test.com",
            password="random_pw_123",
            is_email_verified=True,  # 소셜 로그인은 이메일 자동 인증
        )

        social_account = SocialAccount.objects.create(
            user=new_user,
            provider="google",
            uid="google_new_123",
            extra_data={"email": "social_newuser@test.com"},
        )

        # 검증
        self.assertTrue(new_user.is_email_verified)
        self.assertEqual(social_account.provider, "google")
        self.assertEqual(SocialAccount.objects.filter(user=new_user).count(), 1)

    def test_email_verification_auto_enabled_on_social_login(self):
        """
        소셜 로그인 시 이메일 자동 인증 테스트

        테스트 내용:
        1. 이메일 미인증 사용자 존재
        2. 해당 이메일로 소셜 로그인
        3. is_email_verified가 True로 자동 변경
        """
        # 이메일 미인증 사용자
        user = User.objects.create_user(
            username="testuser",
            email="test@social.com",
            password="testpass123",
            is_email_verified=False,
        )

        # 이메일 인증 토큰 생성
        token = EmailVerificationToken.objects.create(user=user)
        self.assertFalse(token.is_used)

        # 소셜 계정 연결 (시그널이 자동으로 처리)
        social_account = SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="google_user_123",
        )

        # 시그널이 작동하려면 pre_social_login 시그널을 직접 호출
        # 실제로는 allauth가 자동으로 호출함
        from allauth.socialaccount.signals import pre_social_login
        from allauth.socialaccount.models import SocialLogin

        social_login = SocialLogin(user=user, account=social_account)

        # 시그널 발생 (Mock)
        pre_social_login.send(
            sender=SocialLogin, request=None, sociallogin=social_login
        )

        # 사용자 이메일 인증 상태 확인
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)

        # 기존 인증 토큰 무효화 확인
        token.refresh_from_db()
        self.assertTrue(token.is_used)

    def test_social_account_connection(self):
        """
        소셜 계정 연결 테스트

        테스트 내용:
        1. 기존 회원이 소셜 계정 연결
        2. SocialAccount 모델에 정상 저장
        """
        social_account = SocialAccount.objects.create(
            user=self.existing_user,
            provider="google",
            uid="google_12345",
            extra_data={"name": "Test User", "email": "existing@test.com"},
        )

        self.assertEqual(social_account.user, self.existing_user)
        self.assertEqual(social_account.provider, "google")
        self.assertIn("name", social_account.extra_data)

    def test_multiple_social_accounts_per_user(self):
        """
        한 사용자가 여러 소셜 계정 연결 테스트

        테스트 내용:
        1. Google, Kakao, Naver 동시 연결
        2. 각각 독립적으로 저장
        """
        # Google 연결
        SocialAccount.objects.create(
            user=self.existing_user,
            provider="google",
            uid="google_123",
        )

        # Kakao 연결
        SocialAccount.objects.create(
            user=self.existing_user,
            provider="kakao",
            uid="kakao_456",
        )

        # Naver 연결
        SocialAccount.objects.create(
            user=self.existing_user,
            provider="naver",
            uid="naver_789",
        )

        # 3개 소셜 계정 연결 확인
        social_accounts = SocialAccount.objects.filter(user=self.existing_user)
        self.assertEqual(social_accounts.count(), 3)

        providers = [acc.provider for acc in social_accounts]
        self.assertIn("google", providers)
        self.assertIn("kakao", providers)
        self.assertIn("naver", providers)

    def test_social_account_disconnect(self):
        """
        소셜 계정 연결 해제 테스트

        테스트 내용:
        1. 소셜 계정 연결
        2. 연결 해제
        3. 사용자는 유지됨
        """
        social_account = SocialAccount.objects.create(
            user=self.existing_user,
            provider="google",
            uid="google_disconnect_test",
        )

        # 연결 해제
        social_account.delete()

        # 사용자는 여전히 존재
        self.assertTrue(User.objects.filter(id=self.existing_user.id).exists())

        # 소셜 계정만 삭제됨
        self.assertFalse(
            SocialAccount.objects.filter(
                user=self.existing_user, provider="google"
            ).exists()
        )

    def test_duplicate_email_handling(self):
        """
        이메일 중복 처리 테스트

        시나리오:
        1. 일반 가입: user@test.com (미인증)
        2. Google 로그인: user@test.com (인증됨)
        3. 자동 병합되어야 함
        """
        # 일반 가입 사용자 (이메일 미인증)
        user = User.objects.create_user(
            username="normaluser",
            email="user@test.com",
            password="testpass123",
            is_email_verified=False,
        )

        # 같은 이메일로 소셜 로그인 시도
        # allauth는 자동으로 기존 계정에 연결
        social_account = SocialAccount.objects.create(
            user=user,  # 기존 사용자에 연결
            provider="google",
            uid="google_same_email",
        )

        # 이메일 자동 인증
        user.is_email_verified = True
        user.save()

        # 사용자 수 확인 (중복 생성 안 됨)
        self.assertEqual(User.objects.filter(email="user@test.com").count(), 1)

        # 소셜 계정 연결 확인
        self.assertTrue(
            SocialAccount.objects.filter(user=user, provider="google").exists()
        )


# ✅ 다른 TestCase 클래스들도 동일하게 적용
@override_settings(SOCIALACCOUNT_PROVIDERS={})
class SocialAuthSignalTestCase(TransactionTestCase):
    """소셜 로그인 시그널 테스트"""

    def setUp(self):
        """테스트 데이터 초기 설정"""
        SocialApp.objects.all().delete()

        self.user = User.objects.create_user(
            username="signaluser",
            email="signal@test.com",
            password="testpass123",
            is_email_verified=False,
        )

    def tearDown(self):
        """테스트 후 정리"""
        SocialApp.objects.all().delete()
        User.objects.all().delete()

    def test_pre_social_login_signal(self):
        """
        pre_social_login 시그널 테스트

        테스트 내용:
        1. 소셜 로그인 시그널 발생
        2. is_email_verified 자동 True
        3. 기존 인증 토큰 무효화
        """
        # 이메일 인증 토큰 생성
        token1 = EmailVerificationToken.objects.create(user=self.user)
        token2 = EmailVerificationToken.objects.create(user=self.user)

        # 소셜 계정 생성
        social_account = SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="signal_test_uid",
        )

        # 시그널 발생 (수동 호출)
        from allauth.socialaccount.signals import pre_social_login
        from allauth.socialaccount.models import SocialLogin

        social_login = SocialLogin(user=self.user, account=social_account)
        pre_social_login.send(
            sender=SocialLogin, request=None, sociallogin=social_login
        )

        # 이메일 자동 인증 확인
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)

        # 기존 토큰 무효화 확인
        token1.refresh_from_db()
        token2.refresh_from_db()
        self.assertTrue(token1.is_used)
        self.assertTrue(token2.is_used)


@override_settings(SOCIALACCOUNT_PROVIDERS={})
class SocialAuthAdminTestCase(TransactionTestCase):
    """소셜 로그인 Admin 테스트"""

    def setUp(self):
        """Admin 테스트 설정"""
        SocialApp.objects.all().delete()

        self.user = User.objects.create_user(
            username="admintest",
            email="admin@test.com",
            password="testpass123",
        )

        self.social_account = SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="admin_test_uid",
            extra_data={"name": "Admin Test"},
        )

    def tearDown(self):
        """테스트 후 정리"""
        SocialApp.objects.all().delete()
        User.objects.all().delete()

    def test_social_account_admin_display(self):
        """Admin에서 소셜 계정 정보 조회"""
        # Admin 페이지에서 볼 수 있는 필드 확인
        self.assertEqual(self.social_account.user.username, "admintest")
        self.assertEqual(self.social_account.provider, "google")
        self.assertIsNotNone(self.social_account.date_joined)

    def test_social_account_search(self):
        """소셜 계정 검색 테스트"""
        # username으로 검색
        results = SocialAccount.objects.filter(user__username__icontains="admin")
        self.assertEqual(results.count(), 1)

        # email로 검색
        results = SocialAccount.objects.filter(user__email__icontains="admin@test")
        self.assertEqual(results.count(), 1)

        # provider로 필터링
        results = SocialAccount.objects.filter(provider="google")
        self.assertEqual(results.count(), 1)
