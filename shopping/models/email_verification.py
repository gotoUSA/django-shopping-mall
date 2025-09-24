import uuid
import random
import string
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class EmailVerificationToken(models.Model):
    """이메일 인증 토큰 모델"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_tokens",
        verbose_name="사용자",
    )

    # UUID 토큰 (링크용)
    token = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, verbose_name="인증 토큰"
    )

    # 6자리 인증 코드 (직접 입력용)
    verification_code = models.CharField(
        max_length=6, editable=False, verbose_name="인증 코드"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일시")

    is_used = models.BooleanField(default=False, verbose_name="사용 여부")

    used_at = models.DateTimeField(null=True, blank=True, verbose_name="사용일시")

    class Meta:
        db_table = "email_verification_tokens"
        verbose_name = "이메일 인증 토큰"
        verbose_name_plural = "이메일 인증 토큰"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["verification_code", "user"]),
            models.Index(fields=["created_at"]),
        ]

    def save(self, *args, **kwargs):
        """저장시 6자리 코드 자동 생성"""
        if not self.verification_code:
            self.verification_code = self.generate_verification_code()
        super().save(*args, **kwargs)

    def generate_verification_code(self):
        """6자리 영문+숫자 코드 생성"""
        characters = string.ascii_uppercase + string.digits
        code = "".join(random.choices(characters, k=6))

        # 중복 체크 (같은 사용자의 유효한 코드)
        while EmailVerificationToken.objects.filter(
            user=self.user, verification_code=code, is_used=False
        ).exists():
            code = "".join(random.choices(characters, k=6))

        return code

    def is_expired(self):
        """토큰 만료 여부 확인 (24시간)"""
        expiry_time = self.created_at + timedelta(hours=24)
        return timezone.now() > expiry_time

    def mark_as_used(self):
        """토큰을 사용됨으로 표시"""
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])

    def can_resend(self):
        """재발송 가능 여부 (1분 제한)"""
        time_limit = self.created_at + timedelta(minutes=1)
        return timezone.now() > time_limit

    def __str__(self):
        return f"{self.user.email} - {self.verification_code} ({'사용됨' if self.is_used else '미사용'})"


class EmailLog(models.Model):
    """이메일 발송 로그 (모니터링용)"""

    EMAIL_TYPE_CHOICES = [
        ("verification", "이메일 인증"),
        ("password_reset", "비밀번호 재설정"),
        ("order_confirm", "주문 확인"),
        ("marketing", "마케팅"),
    ]

    STATUS_CHOICES = [
        ("pending", "대기중"),
        ("sent", "발송완료"),
        ("failed", "발송실패"),
        ("opened", "열람됨"),
        ("clicked", "클릭됨"),
        ("verified", "인증완료"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="email_logs",
        verbose_name="사용자",
    )

    email_type = models.CharField(
        max_length=20, choices=EMAIL_TYPE_CHOICES, verbose_name="이메일 유형"
    )

    recipient_email = models.EmailField(verbose_name="수신자 이메일")

    subject = models.CharField(max_length=255, verbose_name="제목")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="상태"
    )

    token = models.ForeignKey(
        EmailVerificationToken,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
        verbose_name="인증 토큰",
    )

    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="발송일시")

    opened_at = models.DateTimeField(null=True, blank=True, verbose_name="열람일시")

    clicked_at = models.DateTimeField(null=True, blank=True, verbose_name="클릭일시")

    verified_at = models.DateTimeField(
        null=True, blank=True, verbose_name="인증완료일시"
    )

    error_message = models.TextField(blank=True, verbose_name="에러 메시지")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일시")

    class Meta:
        db_table = "email_logs"
        verbose_name = "이메일 로그"
        verbose_name_plural = "이메일 로그"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "email_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def mark_as_sent(self):
        """발송 완료 처리"""
        self.status = "sent"
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at"])

    def mark_as_failed(self, error_message=""):
        """발송 실패 처리"""
        self.status = "failed"
        self.error_message = error_message
        self.save(update_fields=["status", "error_message"])

    def mark_as_verified(self):
        """인증 완료 처리"""
        self.status = "verified"
        self.verified_at = timezone.now()
        self.save(update_fields=["status", "verified_at"])

    def __str__(self):
        return f"{self.email_type} - {self.recipient_email} ({self.status})"
