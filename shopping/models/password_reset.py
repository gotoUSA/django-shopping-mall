from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

if TYPE_CHECKING:
    from shopping.models.user import User


class PasswordResetToken(models.Model):
    """비밀번호 재설정 토큰 모델

    보안 고려사항:
    - 토큰은 해시값으로 저장되어 DB 침해 시에도 원본 노출 방지
    - 만료 시간은 settings에서 설정 가능 (기본 24시간)
    - 사용된 토큰은 재사용 불가
    - 새 토큰 생성 시 이전 미사용 토큰 자동 무효화 권장
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
        verbose_name="사용자",
        help_text="비밀번호를 재설정할 사용자",
    )

    # 토큰 해시값 (SHA-256) - 보안을 위해 평문 대신 해시 저장
    token_hash = models.CharField(
        max_length=64,  # SHA-256 hex digest length
        unique=True,
        editable=False,
        null=True,       # 기존 row 처리
    blank=True,      # admin/form 허용
        verbose_name="토큰 해시",
        help_text="토큰의 SHA-256 해시값 (보안을 위해 평문 저장하지 않음)",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
        help_text="토큰이 생성된 시각",
    )

    is_used = models.BooleanField(
        default=False,
        verbose_name="사용 여부",
        help_text="토큰 사용 여부 (사용 시 자동으로 True)",
    )

    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="사용일시",
        help_text="토큰이 실제로 사용된 시각",
    )

    class Meta:
        db_table = "password_reset_tokens"
        verbose_name = "비밀번호 재설정 토큰"
        verbose_name_plural = "비밀번호 재설정 토큰"
        ordering = ["-created_at"]
        indexes = [
            # token_hash는 unique=True로 이미 인덱스가 생성되므로 중복 제거
            models.Index(fields=["user", "is_used"]),  # 사용자별 미사용 토큰 조회용
            models.Index(fields=["created_at"]),  # 만료 토큰 정리용
        ]

    def clean(self) -> None:
        """모델 validation

        is_used와 used_at의 일관성 검증:
        - is_used=True인 경우 used_at이 반드시 있어야 함
        - is_used=False인 경우 used_at이 없어야 함
        """
        super().clean()

        if self.is_used and not self.used_at:
            raise ValidationError({
                "used_at": "사용된 토큰은 사용 시각이 필요합니다."
            })

        if not self.is_used and self.used_at:
            raise ValidationError({
                "used_at": "미사용 토큰은 사용 시각이 없어야 합니다."
            })

    @staticmethod
    def _hash_token(token: str | uuid.UUID) -> str:
        """토큰을 SHA-256으로 해싱

        Args:
            token: 원본 토큰 (UUID 또는 문자열)

        Returns:
            str: SHA-256 해시값 (64자 hex)
        """
        token_str = str(token)
        return hashlib.sha256(token_str.encode()).hexdigest()

    @classmethod
    @transaction.atomic
    def generate_token(cls, user: User, invalidate_previous: bool = True) -> str:
        """새로운 비밀번호 재설정 토큰 생성

        Args:
            user: 토큰을 생성할 사용자
            invalidate_previous: 기존 미사용 토큰 무효화 여부 (기본 True)

        Returns:
            str: 원본 토큰 (UUID) - 이메일 링크에 사용

        Note:
            - 반환된 원본 토큰은 DB에 저장되지 않음 (해시값만 저장)
            - 이메일 링크에 포함시킬 때 한 번만 사용 가능
            - invalidate_previous=True 시 이전 미사용 토큰 모두 무효화
            - 트랜잭션으로 race condition 방지
        """
        # 이전 미사용 토큰 무효화
        if invalidate_previous:
            cls.invalidate_previous_tokens(user)

        # 새 토큰 생성
        raw_token = uuid.uuid4()
        token_hash = cls._hash_token(raw_token)

        # DB에 해시값만 저장
        cls.objects.create(user=user, token_hash=token_hash)

        # 원본 토큰 반환 (이메일 링크용)
        return str(raw_token)

    @classmethod
    def invalidate_previous_tokens(cls, user: User) -> int:
        """사용자의 이전 미사용 토큰 모두 무효화

        Args:
            user: 토큰을 무효화할 사용자

        Returns:
            int: 무효화된 토큰 개수
        """
        return cls.objects.filter(
            user=user,
            is_used=False
        ).update(
            is_used=True,
            used_at=timezone.now()
        )

    @classmethod
    def verify_token(cls, user: User, raw_token: str) -> PasswordResetToken | None:
        """토큰 검증 및 조회

        Args:
            user: 토큰 소유자
            raw_token: 원본 토큰 (UUID 문자열)

        Returns:
            PasswordResetToken | None: 유효한 토큰 객체 또는 None

        Note:
            유효 조건:
            - 토큰 해시가 일치
            - 사용되지 않음 (is_used=False)
            - 만료되지 않음
        """
        try:
            token_hash = cls._hash_token(raw_token)
            token = cls.objects.get(
                user=user,
                token_hash=token_hash,
                is_used=False
            )

            # 만료 확인
            if token.is_expired():
                return None

            return token
        except cls.DoesNotExist:
            return None

    def is_expired(self, now: datetime | None = None) -> bool:
        """토큰 만료 여부 확인

        Args:
            now: 현재 시간 (테스트용, 기본값은 timezone.now())

        Returns:
            bool: 만료되었으면 True, 유효하면 False

        Note:
            만료 시간은 settings.PASSWORD_RESET_TIMEOUT (초 단위)
            기본값: 86400초 (24시간)
        """
        now = now or timezone.now()
        timeout_seconds = getattr(settings, "PASSWORD_RESET_TIMEOUT", 86400)
        expiry_time = self.created_at + timedelta(seconds=timeout_seconds)
        return now > expiry_time

    def mark_as_used(self) -> None:
        """토큰을 사용됨으로 표시

        Note:
            - is_used를 True로 설정
            - used_at을 현재 시각으로 설정
            - update_fields로 성능 최적화
        """
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])

    def __str__(self) -> str:
        return f"{self.user.email} - 비밀번호 재설정 ({'사용됨' if self.is_used else '미사용'})"
