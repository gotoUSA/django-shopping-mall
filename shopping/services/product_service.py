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

        Args:
            product_image: 대표로 설정할 상품 이미지
        """
        if not product_image.is_primary:
            return

        # 같은 상품의 다른 대표 이미지 해제 (동시성 제어)
        from shopping.models.product import ProductImage

        ProductImage.objects.select_for_update().filter(
            product=product_image.product,
            is_primary=True
        ).exclude(pk=product_image.pk).update(is_primary=False)

        logger.info(
            f"대표 이미지 설정: product_id={product_image.product_id}, "
            f"image_id={product_image.pk}"
        )
