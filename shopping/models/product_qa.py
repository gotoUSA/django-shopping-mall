from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
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
        on_delete=models.PROTECT,
        related_name="questions",
        verbose_name="상품",
        help_text="문의가 있는 상품은 삭제할 수 없습니다",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_questions",
        verbose_name="작성자",
        help_text="탈퇴한 사용자의 문의는 보존됩니다",
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
    is_answered = models.BooleanField(default=False, verbose_name="답변 완료")

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

        # 작성자 본인 (탈퇴한 사용자의 경우 self.user가 None일 수 있음)
        if self.user and self.user == user:
            return True

        # 상품 판매자 (seller가 None일 수 있음)
        if self.product.seller and self.product.seller == user:
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
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_answers",
        verbose_name="답변자",
        help_text="탈퇴한 판매자의 답변은 보존됩니다",
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
        return f"문의 #{self.question_id}에 대한 답변"

    def clean(self) -> None:
        """
        답변 저장 시 검증
        - 답변자가 실제 상품의 판매자인지 확인
        - 관리자는 예외적으로 답변 가능
        """
        super().clean()

        if not self.question_id:
            return  # question이 설정되지 않은 경우 skip

        # seller가 None인 경우 (탈퇴한 사용자) skip
        if not self.seller:
            return

        # 관리자는 모든 문의에 답변 가능
        if self.seller.is_staff or self.seller.is_superuser:
            return

        # 상품 판매자 확인 (seller가 None인 경우도 고려)
        product_seller = self.question.product.seller
        if not product_seller:
            raise ValidationError({
                "question": "판매자가 없는 상품에는 답변할 수 없습니다."
            })

        # 답변자가 상품의 판매자인지 확인
        if self.seller != product_seller:
            raise ValidationError({
                "seller": "답변자는 해당 상품의 판매자여야 합니다."
            })

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        저장 시 자동 처리는 서비스 레이어에서 담당합니다.
        답변 생성: ProductQAService.create_answer() 사용
        """
        super().save(*args, **kwargs)
