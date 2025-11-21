"""
상품 관련 비즈니스 로직
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from shopping.models.product import ProductImage

logger = logging.getLogger(__name__)


class ProductService:
    """상품 관련 서비스 클래스"""

    @staticmethod
    @transaction.atomic
    def set_primary_image(product_image: ProductImage) -> None:
        """
        상품의 대표 이미지 설정

        기존 대표 이미지를 해제하고 새 이미지를 대표로 설정합니다.
        트랜잭션 내에서 동시성을 제어하며 완전한 저장까지 수행합니다.

        동시성 안전성:
            - 같은 product의 모든 이미지에 잠금을 걸어 race condition 방지
            - 모든 이미지를 False로 초기화 후 타겟만 True로 설정하여 원자성 보장

        Args:
            product_image: 대표로 설정할 상품 이미지 (is_primary=True로 설정된 상태여야 함)
        """
        # 메모리 상태로 의도 확인 (호출자가 is_primary=True로 설정했는지)
        if not product_image.is_primary:
            return

        from shopping.models.product import ProductImage

        # 같은 상품의 모든 이미지에 잠금 획득 후 일괄 False 처리 (동시성 제어)
        # is_primary=True 필터가 아닌 product 전체에 잠금을 걸어야
        # 초기 상태가 모두 False인 경우에도 race condition 방지 가능
        ProductImage.objects.select_for_update().filter(
            product=product_image.product
        ).update(is_primary=False)

        # 타겟 이미지만 True로 설정 (DB 직접 업데이트로 메모리 불일치 방지)
        ProductImage.objects.filter(pk=product_image.pk).update(is_primary=True)

        logger.info(
            f"대표 이미지 설정: product_id={product_image.product_id}, "
            f"image_id={product_image.pk}"
        )
