from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from shopping.models.user import User


class PasswordResetToken(models.Model):
    """비밀번호 재설정 토큰 모델"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
        verbose_name="사용자",
    )

    # UUID 토큰 (이메일 링크용)
    token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        verbose_name="재설정 토큰",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    is_used = models.BooleanField(
        default=False,
        verbose_name="사용 여부",
    )

    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="사용일시",
    )

    class Meta:
        db_table = "password_reset_tokens"
        verbose_name = "비밀번호 재설정 토큰"
        verbose_name_plural = "비밀번호 재설정 토큰"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["user", "is_used"]),
            models.Index(fields=["created_at"]),
        ]

    def is_expired(self, now: datetime | None = None) -> bool:
        """
        토큰 만료 여부 확인 (24시간)

        Args:
            now: 현재 시간 (테스트용, 기본값은 timezone.now())

        Returns:
            bool: 만료되었으면 True, 유효하면 False
        """
        now = now or timezone.now()
        expiry_time = self.created_at + timedelta(hours=24)
        return now > expiry_time

    def mark_as_used(self) -> None:
        """토큰을 사용됨으로 표시"""
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])

    def __str__(self) -> str:
        return f"{self.user.email} - 비밀번호 재설정 ({'사용됨' if self.is_used else '미사용'})"
