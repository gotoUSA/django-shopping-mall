from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils import timezone


class Cart(models.Model):
    """
    장바구니 모델
    각 사용자는 하나의 활성 장바구니를 가집니다.
    주문 완료 시 새로운 장바구니가 생성됩니다.
    """

    # 사용자 참조
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carts",
        verbose_name="사용자",
    )

    # 세션 키 (비회원 장바구니를 위함)
    session_key = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="세션 키",
        help_text="비회원 장바구니를 위한 세션 키",
    )

    # 상태
    is_active = models.BooleanField(
        default=True,
        verbose_name="활성 상태",
        help_text="현재 사용중인 장바구니인지 여부",
    )

    # 시간 정보
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일시")

    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일시")

    class Meta:
        db_table = "shopping_carts"
        verbose_name = "장바구니"
        verbose_name_plural = "장바구니 목록"
        ordering = ["-updated_at"]
        # 사용자당 활성 장바구니는 한개만
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True),
                name="unique_active_cart_per_user",
            )
        ]

    def __str__(self):
        return f'{self.user.username}의 장바구니 ({"활성" if self.is_active else "비활성"})'

    @property
    def total_amount(self):
        """장바구니 총 금액 계산"""
        total = Decimal("0")
        for item in self.items.all():
            total += item.subtotal
        return total

    @property
    def total_quantity(self):
        """장바구니 총 수량"""
        return sum(item.quantity for item in self.items.all())

    def clear(self):
        """장바구니 비우기"""
        self.items.all().delete()

    def deactivate(self):
        """장바구니 비활성화 (주문 완료 시)"""
        self.is_active = False
        self.save(update_fields=["is_active"])

    @classmethod
    def get_or_create_active_cart(cls, user):
        """사용자의 활성 장바구니 가져오기 또는 생성"""
        cart, created = cls.objects.get_or_create(
            user=user, is_active=True, defaults={"user": user}
        )
        return cart, created


class CartItem(models.Model):
    """
    장바구니 아이템 모델
    장바구니에 담긴 개별 상품 정보를 저장합니다.
    """

    # 장바구니 참조
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items", verbose_name="장바구니"
    )

    # 상품 참조
    product = models.ForeignKey(
        "Product", on_delete=models.CASCADE, verbose_name="상품"
    )

    # 수량
    quantity = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)], verbose_name="수량"
    )

    # 시간 정보
    added_at = models.DateTimeField(auto_now_add=True, verbose_name="추가일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일시")

    class Meta:
        db_table = "shopping_cart_items"
        verbose_name = "장바구니 아이템"
        verbose_name_plural = "장바구니 아이템 목록"
        ordering = ["-added_at"]
        # 같은 장바구니에 같은 상품은 하나만
        unique_together = ["cart", "product"]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def subtotal(self):
        """소계 계산 (현재 상품 가격 x 수량)"""
        return self.product.price * self.quantity

    def increase_quantity(self, quantity=1):
        """수량 증가"""
        self.quantity += quantity
        self.save(update_fields=["quantity", "updated_at"])

    def decrease_quantity(self, quantity=1):
        """수량 감소"""
        if self.quantity > quantity:
            self.quantity -= quantity
            self.save(update_fields=["quantity", "updated_at"])
        else:
            # 수량이 0이 되면 삭제
            self.delete()

    def update_quantity(self, quantity):
        """수량 직접 설정"""
        if quantity > 0:
            # F() 객체 사용하지 않고 직접 값 설정 (이미 lock이 걸려있다고 가정)
            CartItem.objects.filter(pk=self.pk).update(
                quantity=quantity, updated_at=timezone.now()
            )
            self.refresh_from_db()
        else:
            self.delete()

    def is_available(self):
        """구매 가능 여부 확인"""
        return self.product.is_active and self.product.stock >= self.quantity

    def clean(self):
        """유효성 검사"""
        from django.core.exceptions import ValidationError

        if self.quantity > self.product.stock:
            raise ValidationError(
                {"quantity": f"재고가 부족합니다. 현재 재고: {self.product.stock}개"}
            )

    def save(self, *args, **kwargs):
        """저장 전 유효성 검사"""
        self.full_clean()
        super().save(*args, **kwargs)
