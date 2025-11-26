from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from shopping.models.email_verification import EmailLog, EmailVerificationToken
from shopping.models.user import User
from shopping.tasks.cleanup_tasks import (
    cleanup_expired_tokens_task,
    cleanup_old_email_logs_task,
    cleanup_used_tokens_task,
    delete_unverified_users_task,
)


class DeleteUnverifiedUsersTaskTest(TestCase):
    """미인증 계정 삭제 태스크 테스트"""

    def setUp(self):
        """테스트 데이터 준비"""
        # 8일 전 미인증 사용자 (삭제 대상)
        self.old_unverified_user = User.objects.create_user(
            username="old_unverified",
            email="old@example.com",
            password="testpass123!",
            is_email_verified=False,
        )
        self.old_unverified_user.date_joined = timezone.now() - timedelta(days=8)
        self.old_unverified_user.save()

        # 5일 전 미인증 사용자 (유지 대상 - 7일 미만)
        self.recent_unverified_user = User.objects.create_user(
            username="recent_unverified",
            email="recent@example.com",
            password="testpass123!",
            is_email_verified=False,
        )
        self.recent_unverified_user.date_joined = timezone.now() - timedelta(days=5)
        self.recent_unverified_user.save()

        # 10일 전 인증된 사용자 (유지 대상 - 인증됨)
        self.verified_user = User.objects.create_user(
            username="verified",
            email="verified@example.com",
            password="testpass123!",
            is_email_verified=True,
        )
        self.verified_user.date_joined = timezone.now() - timedelta(days=10)
        self.verified_user.save()

    def test_delete_unverified_users_default(self):
        """기본 설정(7일)으로 미인증 계정 삭제 테스트"""
        # 삭제 전 사용자 수
        total_before = User.objects.count()
        self.assertEqual(total_before, 3)

        # 태스크 실행
        result = delete_unverified_users_task()

        # 결과 검증
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 1)

        # 8일 전 미인증 사용자만 삭제되었는지 확인
        self.assertFalse(User.objects.filter(email="old@example.com").exists())

        # 나머지는 유지되었는지 확인
        self.assertTrue(User.objects.filter(email="recent@example.com").exists())
        self.assertTrue(User.objects.filter(email="verified@example.com").exists())

        # 최종 사용자 수
        total_after = User.objects.count()
        self.assertEqual(total_after, 2)

    def test_delet_unverified_users_custom_days(self):
        """커스텀 일수(5일)로 삭제 테스트"""
        # 5일로 설정하면 8일 전 사용자도 삭제됨
        result = delete_unverified_users_task(days=5)

        # 8일 전 미인증 사용자 삭제 확인
        self.assertEqual(result["deleted_count"], 2)
        self.assertFalse(User.objects.filter(email="old@example.com").exists())
        self.assertFalse(User.objects.filter(email="recent@example.com").exists())

    def test_delete_unverified_users_with_order(self):
        """주문이 있는 미인증 사용자는 유지 테스트"""
        # 주문 모델을 임포트하고 주문 생성
        # (실제로는 Order 모델이 있어야 함)
        # 이 테스트는 Order 모델이 구현되면 활성화

    def test_delete_unverified_users_none_to_delete(self):
        """삭제할 계정이 없는 경우 테스트"""
        # 모든 사용자를 인증 처리
        User.objects.filter(is_email_verified=False).update(is_email_verified=True)

        # 태스크 실행
        result = delete_unverified_users_task()

        # 결과 검증
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 0)


class CleanupOldEmailLogsTaskTest(TestCase):
    """오래된 이메일 로그 정리 태스크 테스트"""

    def setUp(self):
        """테스트 데이터 준비"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123!",
        )

        # 100일 전 발송 완료 로그 (삭제 대상)
        self.old_sent_log = EmailLog.objects.create(
            user=self.user,
            email_type="verification",
            recipient_email=self.user.email,
            subject="테스트 이메일",
            status="sent",
        )
        self.old_sent_log.created_at = timezone.now() - timedelta(days=100)
        self.old_sent_log.save()

        # 100일 전 인증 완료 로그 (삭제 대상)
        self.old_verified_log = EmailLog.objects.create(
            user=self.user,
            email_type="verification",
            recipient_email=self.user.email,
            subject="테스트 이메일 2",
            status="verified",
        )
        self.old_verified_log.created_at = timezone.now() - timedelta(days=100)
        self.old_verified_log.save()

        # 100일 전 대기중 로그 (유지 대상 - pending)
        self.old_pending_log = EmailLog.objects.create(
            user=self.user,
            email_type="verification",
            recipient_email=self.user.email,
            subject="테스트 이메일 3",
            status="pending",
        )
        self.old_pending_log.created_at = timezone.now() - timedelta(days=100)
        self.old_pending_log.save()

        # 50일 전 발송 완료 로그 (유지 대상 - 90일 미만)
        self.recent_sent_log = EmailLog.objects.create(
            user=self.user,
            email_type="verification",
            recipient_email=self.user.email,
            subject="테스트 이메일 4",
            status="sent",
        )
        self.recent_sent_log.created_at = timezone.now() - timedelta(days=50)
        self.recent_sent_log.save()

    def test_cleanup_old_email_logs_default(self):
        """기본 설정(90일)으로 오래된 로그 삭제 테스트"""
        # 삭제 전 로그 수
        total_before = EmailLog.objects.count()
        self.assertEqual(total_before, 4)

        # 태스크 실행
        result = cleanup_old_email_logs_task()

        # 결과 검증
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 2)  # sent, verified 2개

        # sent, verified 상태의 오래된 로그만 삭제되었는지 확인
        self.assertFalse(EmailLog.objects.filter(id=self.old_sent_log.id).exists())
        self.assertFalse(EmailLog.objects.filter(id=self.old_verified_log.id).exists())

        # pending과 최근 로그는 유지되었는지 확인
        self.assertTrue(EmailLog.objects.filter(id=self.old_pending_log.id).exists())
        self.assertTrue(EmailLog.objects.filter(id=self.recent_sent_log.id).exists())

        # 최종 로그 수
        total_after = EmailLog.objects.count()
        self.assertEqual(total_after, 2)

    def test_cleanup_old_email_logs_custom_days(self):
        """커스텀 일수(60일)로 삭제 테스트"""
        result = cleanup_old_email_logs_task(days=60)

        # 100일 전 sent, verified 2개 삭제
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 2)


class CleanupUsedTokensTaskTest(TestCase):
    """사용된 도큰 정리 태스크 테스트"""

    def setUp(self):
        """테스트 데이터 준비"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123!",
        )

        # 40일 전 사용된 토큰 (삭제 대상)
        self.old_used_token = EmailVerificationToken.objects.create(user=self.user)
        self.old_used_token.is_used = True
        self.old_used_token.used_at = timezone.now() - timedelta(days=40)
        self.old_used_token.save()

        # 20일 전 사용된 토큰 (유지 대상 - 30일 미만)
        self.recent_used_token = EmailVerificationToken.objects.create(user=self.user)
        self.recent_used_token.is_used = True
        self.recent_used_token.used_at = timezone.now() - timedelta(days=20)
        self.recent_used_token.save()

        # 미사용 토큰 (유지 대상)
        self.unused_token = EmailVerificationToken.objects.create(user=self.user)

    def test_cleanup_used_tokens_default(self):
        """기본 설정(30일)으로 사용된 토큰 삭제 테스트"""
        # 삭제 전 토큰 수
        total_before = EmailVerificationToken.objects.count()
        self.assertEqual(total_before, 3)

        # 태스크 실행
        result = cleanup_used_tokens_task()

        # 결과 검증
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 1)

        # 40일 전 사용된 토큰만 삭제되었는지 확인
        self.assertFalse(EmailVerificationToken.objects.filter(id=self.old_used_token.id).exists())

        # 나머지는 유지되었는지 확인
        self.assertTrue(EmailVerificationToken.objects.filter(id=self.recent_used_token.id).exists())
        self.assertTrue(EmailVerificationToken.objects.filter(id=self.unused_token.id).exists())

        # 최종 토큰 수
        total_after = EmailVerificationToken.objects.count()
        self.assertEqual(total_after, 2)


class CleanupExpiredTokensTaskTest(TestCase):
    """만료된 토큰 정리 태스크 테스트"""

    def setUp(self):
        """테스트 데이터 준비"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123!",
        )

        # 25시간 전 생성된 미사용 토큰 (삭제 대상 - 만료됨)
        self.expired_token = EmailVerificationToken.objects.create(user=self.user)
        self.expired_token.created_at = timezone.now() - timedelta(hours=25)
        self.expired_token.save()

        # 20시간 전 생성된 미사용 토큰 (유지 대상 - 아직 유효)
        self.valid_token = EmailVerificationToken.objects.create(user=self.user)
        self.valid_token.created_at = timezone.now() - timedelta(hours=20)
        self.valid_token.save()

        # 30시간 전 생성되었지만 사용된 토큰 (유지 대상)
        # 먼저 생성
        self.used_token = EmailVerificationToken.objects.create(user=self.user)

        # 그 다음 속성 설정
        self.used_token.created_at = timezone.now() - timedelta(hours=30)
        self.used_token.is_used = True
        self.used_token.used_at = timezone.now() - timedelta(hours=29)
        self.used_token.save()

    def test_cleanup_expired_tokens(self):
        """만료된 미사용 토큰 삭제 테스트"""
        # 삭제 전 토큰 수
        total_before = EmailVerificationToken.objects.count()
        self.assertEqual(total_before, 3)

        # 태스크 실행
        result = cleanup_expired_tokens_task()

        # 결과 검증
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 1)

        # 만료된 미사용 토큰만 삭제되었는지 확인
        self.assertFalse(EmailVerificationToken.objects.filter(id=self.expired_token.id).exists())

        # 유효한 토큰과 사용된 토큰은 유지되었는지 확인
        self.assertTrue(EmailVerificationToken.objects.filter(id=self.valid_token.id).exists())
        self.assertTrue(EmailVerificationToken.objects.filter(id=self.used_token.id).exists())

        # 최종 토큰 수
        total_after = EmailVerificationToken.objects.count()
        self.assertEqual(total_after, 2)


class CleanupTaskIntegrationTest(TestCase):
    """정리 태스크 통합 테스트"""

    def setUp(self):
        """테스트 데이터 준비"""
        # 다양한 상태의 데이터 생성
        self.create_test_data()

    def create_test_data(self):
        """복잡한 테스트 데이터 생성"""
        # 오래된 미인증 사용자 (삭제 대상)
        old_user = User.objects.create_user(
            username="old_user",
            email="old@example.com",
            password="testpass123!",
            is_email_verified=False,
        )
        old_user.date_joined = timezone.now() - timedelta(days=10)
        old_user.save()

        # 토큰 생성
        token = EmailVerificationToken.objects.create(user=old_user)
        token.created_at = timezone.now() - timedelta(days=10)
        token.save()

        # 이메일 로그 생성
        log = EmailLog.objects.create(
            user=old_user,
            token=token,
            email_type="verification",
            recipient_email=old_user.email,
            subject="테스트",
            status="sent",
        )
        log.created_at = timezone.now() - timedelta(days=10)
        log.save()

    def test_full_cleanup_workflow(self):
        """전체 정리 워크플로우 테스트"""
        # 1. 초기 데이터 수
        users_before = User.objects.count()
        EmailVerificationToken.objects.count()
        EmailLog.objects.count()

        # 2. 미인증 계정 삭제(CASCADE로 토큰, 로그도 삭제)
        delete_result = delete_unverified_users_task(days=7)

        # 3. 결과 확인
        self.assertTrue(delete_result["success"])

        # 사용자 삭제되면 연관 데이터도 삭제됨 (CASCADE)
        users_after = User.objects.count()
        self.assertLess(users_after, users_before)
