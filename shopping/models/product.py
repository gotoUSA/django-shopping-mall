from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

from mptt.models import MPTTModel, TreeForeignKey


class Category(MPTTModel):
    """
    상품 카테고리 (MPTT를 사용한 계층구조)

    MPTT(Modified Preorder Tree Traversal)를 사용하여
    효율적인 계층 구조 쿼리를 지원합니다.
    """

    name = models.CharField(max_length=100, unique=True, verbose_name="카테고리명")

    slug = models.SlugField(max_length=100, unique=True, help_text="URL에 사용될 짦은 이름 (자동생성됨)")
    parent = TreeForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="상위 카테고리",
    )
    description = models.TextField(blank=True, verbose_name="카테고리 설명")
    is_active = models.BooleanField(default=True, verbose_name="활성화 여부")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(default=True, verbose_name="활성화")

    class MPTTMeta:
        """MPTT 설정"""

        # 정렬 기준 필드 지정
        order_insertion_by = ["name"]

    class Mega:
        verbose_name = "카테고리"
        verbose_name_plural = "카테고리"
        ordering = ["name"]  # 기본 정렬

    def __str__(self):
        # 계층 구조를 보여주는 문자열 표현
        # get_ancestors()는 MPTT가 제공하는 메서드
        ancestors = self.get_ancestors(include_self=False)
        if ancestors:
            ancestors_names = " > ".join([a.name for a in ancestors])
            return f"{ancestors_names} > {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        # slug 자동 생성 (한글 지원)
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    def get_full_path(self):
        """
        최상위부터 현재 카테고리까지의 전체 경로 반환
        예: "전자제품 > 컴퓨터 > 노트북
        """
        ancestors = self.get_ancestors(include_self=True)
        return " > ".join([cat.name for cat in ancestors])

    def get_all_products(self):
        """
        현재 카테고리와 모든 하위 카테고리의 상품을 반환
        """
        categories = self.get_descendants(include_self=True)
        return Product.objects.filter(category__in=categories, is_active=True)

    @property
    def product_count(self):
        """현재 카테고리의 활성 상품 수"""
        return self.products.filter(is_active=True).count()

    @property
    def total_product_count(self):
        """하위 카테고리를 포함한 전체 상품 수"""
        return self.get_all_products().count()


class Product(models.Model):
    """상품 기본 정보"""

    # 기본 정보
    name = models.CharField(max_length=200, verbose_name="상품명", db_index=True)  # 검색 속도 향상
    slug = models.SlugField(max_length=200, unique=True, help_text="URL용 이름 (자동생성)")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="카테고리",
    )

    # 상품 설명
    description = models.TextField(verbose_name="상품 설명", help_text="상품의 자세한 설명을 입력하세요.")
    short_description = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="간단 설명",
        help_text="목록에서 보여질 짧은 설명",
    )

    # 가격 정보
    price = models.DecimalField(
        max_digits=10,  # 최대 10자리
        decimal_places=0,
        validators=[MinValueValidator(0)],
        verbose_name="판매가",
    )
    compare_price = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="할인 전 가격",
        help_text="할인 전 가격 (선택사항)",
    )

    # 재고 관리
    stock = models.PositiveIntegerField(default=0, verbose_name="재고 수량")
    is_available = models.BooleanField(default=True, verbose_name="판매 가능 여부")

    # 상품 옵션
    sku = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="재고관리코드(SKU)",
        help_text="상품 고유 관리 번호",
    )

    # 추가 정보
    brand = models.CharField(max_length=100, blank=True, verbose_name="브랜드")
    tags = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="태그",
        help_text="쉼표로 구분하여 입력 (예: 신상품, 베스트 , 세일)",
    )

    # 판매자 정보
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="판매자",
        null=True,
        blank=True,
    )

    # 통계 정보
    view_count = models.PositiveIntegerField(default=0, verbose_name="조회수")
    sold_count = models.PositiveIntegerField(default=0, verbose_name="판매량")

    # 시간 정보
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 상품 활성화 상태 추가
    is_active = models.BooleanField(default=True, verbose_name="판매중", help_text="체크 해제시 상품이 숨겨집니다.")

    class Meta:
        verbose_name = "상품"
        verbose_name_plural = "상품"
        ordering = ["-created_at"]  # 최신순 정렬
        indexes = [
            models.Index(fields=["name", "category"]),  # 복합 인덱스
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    @property
    def is_on_sale(self):
        """할인 중인지 확인"""
        return self.compare_price and self.compare_price > self.price

    @property
    def discount_percentage(self):
        """할인율 계산"""
        if self.is_on_sale:
            return int((1 - self.price / self.compare_price) * 100)
        return 0

    @property
    def is_in_stock(self):
        """재고 있는지 확인"""
        return self.stock > 0 and self.is_available

    def can_purchase(self, quantity):
        """구매 가능한지 확인"""
        return self.is_in_stock and self.stock >= quantity

    def decrease_stock(self, quantity):
        """재고 차감"""
        if self.can_purchase(quantity):
            self.stock -= quantity
            self.sold_count += quantity
            self.save()
            return True
        return False

    # 찜하기 관련 메서드
    def get_wishlist_count(self):
        """이 상품을 찜한 사용자 수 반환"""
        return self.wished_by_users.count()

    def is_wished_by(self, user):
        """특정 사용자가 이 상품을 찜했는지 확인"""
        if not user or not user.is_authenticated:
            return False
        return self.wished_by_users.filter(id=user.id).exists()

    def get_wishlist_users(self):
        """이 상품을 찜한 사용자 목록 반환"""
        return self.wished_by_users.all()

    # ProductListSerializer나 ProductDetailSerializer에서 사용할 수 있는
    # 추가 property
    @property
    def wishlist_count(self):
        """찜 개수를 property로 제공"""
        return self.get_wishlist_count()

    # Admin이나 템플릿에서 표시용
    def wishlist_count_display(self):
        """찜 개수를 포맷팅해서 반환"""
        count = self.get_wishlist_count()
        if count == 0:
            return "찜 없음"
        elif count < 10:
            return f"{count}명이 찜"
        elif count < 100:
            return f"{count}명이 찜"
        elif count < 1000:
            return f"{count}명이 찜"
        else:
            return f"{count:,}명이 찜"  # 천 단위 콤마


class ProductImage(models.Model):
    """상품 이미지 (여러개 가능)"""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images", verbose_name="상품")
    image = models.ImageField(upload_to="product/%Y/%m/%d", verbose_name="이미지")
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="대체 텍스트",
        help_text="이미지 설명 (SEO용)",
    )
    is_primary = models.BooleanField(default=False, verbose_name="대표 이미지")
    order = models.PositiveIntegerField(default=0, verbose_name="표시 순서")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "상품 이미지"
        verbose_name_plural = "상품 이미지"
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"{self.product.name} - 이미지 {self.order}"

    def save(self, *args, **kwargs):
        # 대표 이미지는 1개만
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class ProductReview(models.Model):
    """상품 리뷰 (선택사항)"""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews", verbose_name="상품")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="작성자")
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="평점")
    comment = models.TextField(verbose_name="리뷰 내용")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "상품 리뷰"
        verbose_name_plural = "상품 리뷰"
        ordering = ["-created_at"]
        # 한 상품에 한 사용자는 하나의 리뷰만 가능
        unique_together = ["product", "user"]

    def __str__(self):
        return f"{self.product.name} - {self.user.username}의 리뷰"
