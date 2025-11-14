from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from shopping.models.user import User


class ProductQuestion(models.Model):
    """
    상품 문의 모델

    사용자가 상품에 대해 질문을 남기는 모델입니다.
    비밀글 기능을 지원하며, 로그인한 사용자만 작성 가능합니다.
    """

    # 기본 정보
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="상품",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_questions",
        verbose_name="작성자",
    )

    # 질문 내용
    title = models.CharField(max_length=200, verbose_name="제목")

    content = models.TextField(verbose_name="문의 내용")

    # 비밀글 여부
    is_secret = models.BooleanField(
        default=False,
        verbose_name="비밀글",
        help_text="체크 시 작성자와 판매자만 볼 수 있습니다",
    )

    # 답변 여부
    is_answered = models.BooleanField(default=False, verbose_name="답변 완료", db_index=True)

    # 시간 정보
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="작성일")

    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "상품 문의"
        verbose_name_plural = "상품 문의"
        indexes = [
            models.Index(fields=["product", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["is_answered"]),
        ]

    def __str__(self) -> str:
        secret_mark = "[비밀]" if self.is_secret else ""
        return f"{secret_mark} {self.title}"

    def can_view(self, user: User | None) -> bool:
        """
        해당 사용자가 이 문의를 볼 수 있는지 확인

        - 비밀글이 아니면: 누구나 볼 수 있음
        - 비밀글이면: 작성자 또는 판매자만 볼 수 있음
        """
        if not self.is_secret:
            return True

        if not user or not user.is_authenticated:
            return False

        # 작성자 본인
        if self.user == user:
            return True

        # 상품 판매자
        if self.product.seller == user:
            return True

        # 관리자
        if user.is_staff:
            return True

        return False


class ProductAnswer(models.Model):
    """
    상품 문의 답변 모델

    판매자가 문의에 답변을 남기는 모델입니다.
    답변이 등록되면 질문자에게 알림이 전송됩니다.
    """

    # 문의 (1:1 관계)
    question = models.OneToOneField(
        ProductQuestion,
        on_delete=models.CASCADE,
        related_name="answer",
        verbose_name="문의",
    )

    # 답변자 (판매자)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_answers",
        verbose_name="답변자",
    )

    # 답변 내용
    content = models.TextField(verbose_name="답변 내용")

    # 시간 정보
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="답변일")

    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    class Meta:
        verbose_name = "문의 답변"
        verbose_name_plural = "문의 답변"

    def __str__(self) -> str:
        return f"{self.question.title}에 대한 답변"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        답변 저장 시 자동 처리:
        1. 문의를 답변 완료 상태로 변경
        2. 질문자에게 알림 발송
        """
        is_new = self.pk is None

        super().save(*args, **kwargs)

        # 새 답변인 경우에만 처리
        if is_new:
            # 문의를 답변 완료로 변경
            self.question.is_answered = True
            self.question.save(update_fields=["is_answered"])

            # 알림 생성
            from .notification import Notification

            Notification.objects.create(
                user=self.question.user,
                notification_type="qa_answer",
                title="상품 문의에 답변이 달렸습니다",
                message=f'"{self.question.title}" 문의에 판매자가 답변했습니다.',
                link=f"/products/{self.question.product.id}/questions/{self.question.id}",
            )
