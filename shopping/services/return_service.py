"""
교환/환불 관련 비즈니스 로직
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

if TYPE_CHECKING:
    from shopping.models.order import Order, OrderItem
    from shopping.models.return_request import Return
    from shopping.models.user import User

logger = logging.getLogger(__name__)


class ReturnService:
    """교환/환불 관련 서비스 클래스"""

    @staticmethod
    def generate_return_number() -> str:
        """
        교환/환불 번호 자동 생성
        형식: RET + YYYYMMDD + 일련번호(3자리)
        예: RET20250115001

        Returns:
            str: 생성된 교환/환불 번호
        """
        from shopping.models.return_request import Return

        today = timezone.now().strftime("%Y%m%d")
        prefix = f"RET{today}"

        # 오늘 날짜의 마지막 번호 조회
        last_return = Return.objects.filter(
            return_number__startswith=prefix
        ).aggregate(Max("return_number"))["return_number__max"]

        if last_return:
            # 마지막 3자리 추출하여 +1
            last_number = int(last_return[-3:])
            new_number = last_number + 1
        else:
            new_number = 1

        return f"{prefix}{new_number:03d}"

    @staticmethod
    def calculate_refund_amount(return_items: list) -> Decimal:
        """
        환불 금액 계산

        Args:
            return_items: ReturnItem 리스트

        Returns:
            Decimal: 총 환불 금액
        """
        total = Decimal("0")
        for item in return_items:
            total += item.product_price * item.quantity
        return total

    @staticmethod
    @transaction.atomic
    def create_return(
        order: Order,
        user: User,
        type: str,
        reason: str,
        reason_detail: str,
        return_items_data: list[dict],
        **kwargs
    ) -> Return:
        """
        교환/환불 신청 생성

        Args:
            order: 원본 주문
            user: 신청자
            type: 타입 (refund/exchange)
            reason: 사유
            reason_detail: 상세 사유
            return_items_data: 반품 항목 리스트
                [
                    {
                        'order_item': OrderItem,
                        'quantity': int,
                        'product_name': str (optional),
                        'product_price': Decimal (optional)
                    }
                ]
            **kwargs: 추가 필드 (refund_account_bank, exchange_product 등)

        Returns:
            Return: 생성된 교환/환불 신청
        """
        from shopping.models.return_request import Return, ReturnItem

        # 1. return_number 생성
        return_number = ReturnService.generate_return_number()

        # 2. Return 객체 생성 (refund_amount는 나중에 계산)
        return_request = Return.objects.create(
            order=order,
            user=user,
            return_number=return_number,
            type=type,
            reason=reason,
            reason_detail=reason_detail,
            refund_amount=Decimal("0"),  # 임시값
            **kwargs
        )

        # 3. ReturnItem 생성
        return_items = []
        for item_data in return_items_data:
            order_item = item_data['order_item']
            quantity = item_data['quantity']
            product_name = item_data.get('product_name', order_item.product_name)
            product_price = item_data.get('product_price', order_item.price)

            return_item = ReturnItem.objects.create(
                return_request=return_request,
                order_item=order_item,
                quantity=quantity,
                product_name=product_name,
                product_price=product_price,
            )
            return_items.append(return_item)

        # 4. refund_amount 계산 및 업데이트 (환불인 경우에만)
        if type == "refund":
            refund_amount = ReturnService.calculate_refund_amount(return_items)
            return_request.refund_amount = refund_amount
            return_request.save(update_fields=["refund_amount"])

        logger.info(
            f"교환/환불 신청 생성: return_number={return_number}, "
            f"order_id={order.id}, user_id={user.id}, type={type}"
        )

        return return_request
