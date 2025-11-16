from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

if TYPE_CHECKING:
    from shopping.models.product import Product

phone_regex = RegexValidator(
    regex=r"^\d{2,3}-\d{3,4}-\d{4}$",
    message="전화번호는 '010-1234-5678' 형식으로 입력해주세요.",
)


class User(AbstractUser):
    """
    커스텀 User 모델
    AbstractUser를 상속받아 기본 필드들(username, email, password 등)을 모두 포함하고,
    쇼핑몰에 필요한 추가 필드들을 정의합니다.
    """

    # 기본 정보 추가 필드
    phone_number = models.CharField(
        max_length=15,
        validators=[phone_regex],
        blank=True,
        verbose_name="전화번호",
        help_text="010-1234-5678 형식으로 입력",
    )

    birth_date = models.DateField(null=True, blank=True, verbose_name="생년월일")

    # 주소 정보
    postal_code = models.CharField(max_length=10, blank=True, verbose_name="우편번호")

    address = models.CharField(max_length=255, blank=True, verbose_name="기본주소")

    address_detail = models.CharField(max_length=255, blank=True, verbose_name="상세주소")

    # 인증 상태
    is_email_verified = models.BooleanField(default=False, verbose_name="이메일 인증 여부")

    is_phone_verified = models.BooleanField(default=False, verbose_name="휴대폰 인증 여부")

    # 마케팅 동의
    agree_marketing_email = models.BooleanField(default=False, verbose_name="마케팅 이메일 수신 동의")

    agree_marketing_sms = models.BooleanField(default=False, verbose_name="마케팅 sms 수신 동의")

    # 회원 등급 및 포인트 (확장 가능)
    MEMBERSHIP_CHOICES = [
        ("bronze", "브론즈"),
        ("silver", "실버"),
        ("gold", "골드"),
        ("vip", "VIP"),
    ]

    membership_level = models.CharField(
        max_length=10,
        choices=MEMBERSHIP_CHOICES,
        default="bronze",
        verbose_name="회원등급",
    )

    points = models.PositiveIntegerField(default=0, verbose_name="포인트")

    # 판매자 여부
    is_seller = models.BooleanField(
        default=False,
        verbose_name="판매자 여부",
        help_text="체크 시 상품 등록/관리 및 교환/환불 처리 권한 부여",
    )

    # 추가 메타 정보
    last_login_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="마지막 로그인 IP")

    # 탈퇴 관련
    is_withdrawn = models.BooleanField(default=False, verbose_name="탈퇴 여부")

    withdrawn_at = models.DateTimeField(null=True, blank=True, verbose_name="탈퇴 일시")

    # 찜한 상품 (ManyToMany 관계)
    wishlist_products = models.ManyToManyField(
        "Product",  # Product 모델과 연결
        related_name="wished_by_users",  # 역참조 이름
        blank=True,  # 찜한 상품이 없어도 됨
        verbose_name="찜한 상품",
        db_table="shopping_wishlist",  # 중간 테이블 이름 지정
    )

    class Meta:
        db_table = "shopping_users"
        verbose_name = "사용자"
        verbose_name_plural = "사용자 목록"

    def __str__(self) -> str:
        return f'{self.username} ({self.get_full_name() or "이름없음"})'

    def get_full_address(self) -> str:
        """전체 주소를 반환하는 메서드"""
        if self.address:
            return f"{self.address} {self.address_detail}".strip()
        return ""

    def get_earn_rate(self) -> int:
        """
        회원 등급별 포인트 적립률 반환

        적립률:
        - bronze: 1%
        - silver: 2%
        - gold: 3%
        - vip: 5%

        Returns:
            int: 포인트 적립률 (백분율)
        """
        earn_rates = {
            "bronze": 1,
            "silver": 2,
            "gold": 3,
            "vip": 5,
        }
        return earn_rates.get(self.membership_level, 1)  # 기본값 1%

    @property
    def is_vip(self) -> bool:
        """VIP 회원인지 확인하는 속성"""
        return self.membership_level == "vip"

    # 찜하기 관련 메서드 추가
    def add_to_wishlist(self, product: Product) -> bool:
        """상품을 찜 목록에 추가"""
        self.wishlist_products.add(product)
        return True

    def is_in_wishlist(self, product: Product) -> bool:
        """상품이 찜 목록에 있는지 확인"""
        return self.wishlist_products.filter(id=product.id).exists()

    def get_wishlist_count(self) -> int:
        """찜한 상품 개수 반환"""
        return self.wishlist_products.count()

    def clear_wishlist(self) -> bool:
        """찜 목록 전체 삭제"""
        self.wishlist_products.clear()
        return True

    def remove_from_wishlist(self, product: Product) -> bool:
        """상품을 찜 목록에서 제거"""
        self.wishlist_products.remove(product)
        return True
