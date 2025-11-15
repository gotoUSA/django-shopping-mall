"""배송 서비스 레이어"""

from decimal import Decimal
from typing import TypedDict


class ShippingFeeResult(TypedDict):
    """배송비 계산 결과"""

    shipping_fee: Decimal
    additional_fee: Decimal
    is_free_shipping: bool


class ShippingService:
    """배송 관련 비즈니스 로직을 처리하는 서비스"""

    # 배송비 설정 (향후 settings.py나 Config 모델로 이동 가능)
    FREE_SHIPPING_THRESHOLD = Decimal("30000")  # 무료배송 기준 금액
    DEFAULT_SHIPPING_FEE = Decimal("3000")  # 기본 배송비
    REMOTE_AREA_FEE = Decimal("3000")  # 도서산간 추가 배송비
    REMOTE_AREA_POSTAL_CODES = ["63", "59", "52"]  # 제주, 울릉도 등

    @classmethod
    def calculate_fee(cls, total_amount: Decimal, postal_code: str = "") -> ShippingFeeResult:
        """
        배송비 계산

        Args:
            total_amount: 상품 총액 (배송비 제외)
            postal_code: 우편번호

        Returns:
            ShippingFeeResult: 기본 배송비, 추가 배송비, 무료배송 여부
        """
        is_remote = cls.is_remote_area(postal_code)

        # 무료배송 기준 금액 이상인 경우
        if total_amount >= cls.FREE_SHIPPING_THRESHOLD:
            return {
                "shipping_fee": Decimal("0"),
                "additional_fee": cls.REMOTE_AREA_FEE if is_remote else Decimal("0"),
                "is_free_shipping": True,
            }

        # 일반 배송비
        return {
            "shipping_fee": cls.DEFAULT_SHIPPING_FEE,
            "additional_fee": cls.REMOTE_AREA_FEE if is_remote else Decimal("0"),
            "is_free_shipping": False,
        }

    @classmethod
    def is_remote_area(cls, postal_code: str) -> bool:
        """
        도서산간 지역 여부 판별

        Args:
            postal_code: 우편번호

        Returns:
            bool: 도서산간 지역 여부
        """
        if not postal_code:
            return False
        return any(postal_code.startswith(code) for code in cls.REMOTE_AREA_POSTAL_CODES)
