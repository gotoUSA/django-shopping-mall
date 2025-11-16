"""
상품 문의/답변 관련 비즈니스 로직
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from shopping.models.product_qa import ProductAnswer, ProductQuestion
    from shopping.models.user import User

logger = logging.getLogger(__name__)


class ProductQAService:
    """상품 문의/답변 관련 서비스 클래스"""

    @staticmethod
    @transaction.atomic
    def create_answer(
        question: ProductQuestion,
        seller: User,
        content: str
    ) -> ProductAnswer:
        """
        상품 문의에 답변 생성

        답변 생성 시 자동 처리:
        1. 답변 저장
        2. 문의를 답변 완료 상태로 변경
        3. 질문자에게 알림 발송

        Args:
            question: 문의
            seller: 답변자 (판매자)
            content: 답변 내용

        Returns:
            ProductAnswer: 생성된 답변
        """
        from shopping.models.notification import Notification
        from shopping.models.product_qa import ProductAnswer

        # 1. 답변 생성
        answer = ProductAnswer.objects.create(
            question=question,
            seller=seller,
            content=content,
        )

        # 2. 문의를 답변 완료로 변경
        question.is_answered = True
        question.save(update_fields=["is_answered"])

        # 3. 알림 생성
        Notification.objects.create(
            user=question.user,
            notification_type="qa_answer",
            title="상품 문의에 답변이 달렸습니다",
            message=f'"{question.title}" 문의에 판매자가 답변했습니다.',
            link=f"/products/{question.product.id}/questions/{question.id}",
        )

        logger.info(
            f"상품 문의 답변 생성: question_id={question.id}, "
            f"seller_id={seller.id}, answer_id={answer.id}"
        )

        return answer
