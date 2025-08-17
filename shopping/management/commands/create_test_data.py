# shopping/management/commands/create_test_data.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import random
from datetime import datetime, timedelta

from shopping.models import (
    Category,
    Product,
    ProductImage,
    ProductReview,
    Cart,
    CartItem,
    Order,
    OrderItem,
)

User = get_user_model()


class Command(BaseCommand):
    help = "테스트용 데이터를 생성합니다 (카테고리, 상품, 사용자, 리뷰 등)"

    def add_arguments(self, parser):
        """커맨드 옵션 추가"""
        parser.add_argument(
            "--clear",
            action="store_true",
            help="기존 데이터를 모두 삭제하고 새로 생성",
        )
        parser.add_argument(
            "--users",
            type=int,
            default=5,
            help="생성할 테스트 사용자 수 (기본값: 5)",
        )
        parser.add_argument(
            "--reviews",
            action="store_true",
            help="리뷰 데이터도 함께 생성",
        )

    def handle(self, *args, **options):
        """메인 실행 함수"""
        self.stdout.write("🚀 테스트 데이터 생성을 시작합니다...\n")

        # 옵션에 따라 기존 데이터 삭제
        if options["clear"]:
            self.clear_existing_data()

        # 트랜잭션으로 묶어서 실행 (에러 시 롤백)
        with transaction.atomic():
            # 1. 카테고리 생성
            categories = self.create_categories()

            # 2. 사용자 생성
            users = self.create_users(options["users"])

            # 3. 상품 생성
            products = self.create_products(categories, users)

            # 4. 리뷰 생성 (옵션)
            if options["reviews"]:
                self.create_reviews(products, users)

            # 5. 장바구니 샘플 생성
            self.create_sample_carts(users, products)

            # 6. 주문 샘플 생성
            self.create_sample_orders(users, products)

        self.stdout.write(
            self.style.SUCCESS("\n✅ 테스트 데이터 생성이 완료되었습니다!")
        )
        self.print_summary()

    def clear_existing_data(self):
        """기존 데이터 삭제"""
        self.stdout.write("🗑️  기존 데이터를 삭제하는 중...")

        # 주문 관련 데이터 삭제
        OrderItem.objects.all().delete()
        Order.objects.all().delete()

        # 장바구니 데이터 삭제
        CartItem.objects.all().delete()
        Cart.objects.all().delete()

        # 상품 관련 데이터 삭제
        ProductReview.objects.all().delete()
        ProductImage.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()

        # 테스트 사용자 삭제 (admin 제외)
        User.objects.filter(username__startswith="test_").delete()

        self.stdout.write(self.style.WARNING("  기존 데이터 삭제 완료\n"))

    def create_categories(self):
        """카테고리 생성"""
        self.stdout.write("📁 카테고리 생성 중...")

        categories_data = {
            "전자제품": {
                "slug": "electronics",
                "children": {
                    "스마트폰": "smartphones",
                    "노트북": "laptops",
                    "태블릿": "tablets",
                    "액세서리": "accessories",
                },
            },
            "의류": {
                "slug": "clothing",
                "children": {
                    "남성의류": "mens-clothing",
                    "여성의류": "womens-clothing",
                    "아동의류": "kids-clothing",
                    "신발": "shoes",
                },
            },
            "식품": {
                "slug": "food",
                "children": {
                    "신선식품": "fresh-food",
                    "가공식품": "processed-food",
                    "음료": "beverages",
                    "건강식품": "health-food",
                },
            },
        }

        created_categories = {}

        for parent_name, parent_data in categories_data.items():
            # 부모 카테고리 생성
            parent_cat, created = Category.objects.get_or_create(
                name=parent_name,
                defaults={
                    "slug": parent_data["slug"],
                    "description": f"{parent_name} 카테고리입니다.",
                    "is_active": True,
                },
            )
            created_categories[parent_name] = parent_cat

            # 자식 카테고리 생성
            for child_name, child_slug in parent_data["children"].items():
                child_cat, created = Category.objects.get_or_create(
                    name=child_name,
                    defaults={
                        "slug": child_slug,
                        "parent": parent_cat,
                        "description": f"{child_name} 하위 카테고리입니다.",
                        "is_active": True,
                    },
                )
                created_categories[child_name] = child_cat

        self.stdout.write(f"  ✓ {len(created_categories)}개 카테고리 생성 완료")
        return created_categories

    def create_users(self, count):
        """테스트 사용자 생성"""
        self.stdout.write(f"👤 테스트 사용자 {count}명 생성 중...")

        users = []
        membership_levels = ["bronze", "silver", "gold", "vip"]

        for i in range(1, count + 1):
            username = f"test_user{i}"

            # 기존 사용자 확인
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"test{i}@example.com",
                    "first_name": f"테스트{i}",
                    "last_name": "사용자",
                    "phone_number": f"010-{1000+i:04d}-{1000+i:04d}",
                    "postal_code": "12345",
                    "address": f"서울시 강남구 테스트로 {i}",
                    "address_detail": f"{100+i}호",
                    "is_email_verified": True,
                    "is_phone_verified": True,
                    "membership_level": random.choice(membership_levels),
                    "points": random.randint(0, 50000),
                    "agree_marketing_email": random.choice([True, False]),
                    "agree_marketing_sms": random.choice([True, False]),
                },
            )

            if created:
                user.set_password("testpass123!")
                user.save()

            users.append(user)

        # 관리자 계정 생성
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "is_staff": True,
                "is_superuser": True,
                "first_name": "관리자",
                "membership_level": "vip",
            },
        )
        if created:
            admin.set_password("admin123!")
            admin.save()
            self.stdout.write(
                self.style.SUCCESS("  ✓ 관리자 계정 생성 (admin/admin123!)")
            )

        self.stdout.write(f"  ✓ {len(users)}명 사용자 생성 완료")
        return users

    def create_products(self, categories, users):
        """상품 생성"""
        self.stdout.write("📦 상품 생성 중...")

        products = []
        seller = users[0] if users else None  # 첫 번째 사용자를 판매자로

        # 전자제품 상품 데이터
        electronics_products = [
            {
                "category": "스마트폰",
                "products": [
                    ("아이폰 15 Pro", 1500000, 1350000, 50, "IP15PRO"),
                    ("갤럭시 S24 Ultra", 1400000, 1260000, 30, "GS24U"),
                    ("픽셀 8 Pro", 1200000, 1080000, 20, "PX8PRO"),
                    ("샤오미 14", 800000, 720000, 40, "XM14"),
                ],
            },
            {
                "category": "노트북",
                "products": [
                    ("맥북 프로 16인치", 3500000, 3150000, 15, "MBP16"),
                    ("LG 그램 17", 2200000, 1980000, 25, "LGG17"),
                    ("삼성 갤럭시북3 프로", 2400000, 2160000, 20, "GB3PRO"),
                    ("레노버 씽크패드 X1", 2000000, 1800000, 18, "TPX1"),
                ],
            },
            {
                "category": "태블릿",
                "products": [
                    ("아이패드 프로 12.9", 1800000, 1620000, 35, "IPADPRO"),
                    ("갤럭시 탭 S9 Ultra", 1500000, 1350000, 28, "GTS9U"),
                    ("아이패드 에어", 900000, 810000, 45, "IPADAIR"),
                ],
            },
        ]

        # 의류 상품 데이터
        clothing_products = [
            {
                "category": "남성의류",
                "products": [
                    ("프리미엄 면 셔츠", 89000, 71200, 100, "MCOT01"),
                    ("슬림핏 청바지", 79000, None, 80, "MJEAN01"),
                    ("캐주얼 후드티", 59000, 47200, 120, "MHOOD01"),
                    ("비즈니스 정장 세트", 450000, 360000, 25, "MSUIT01"),
                ],
            },
            {
                "category": "여성의류",
                "products": [
                    ("플로럴 원피스", 125000, 100000, 60, "WDRESS01"),
                    ("캐시미어 니트", 180000, 144000, 40, "WKNIT01"),
                    ("하이웨이스트 스커트", 65000, None, 70, "WSKIRT01"),
                    ("트렌치 코트", 280000, 224000, 30, "WCOAT01"),
                ],
            },
            {
                "category": "신발",
                "products": [
                    ("런닝화 에어맥스", 149000, 119200, 90, "SHOE01"),
                    ("클래식 스니커즈", 89000, None, 110, "SHOE02"),
                    ("하이힐 펌프스", 135000, 108000, 50, "SHOE03"),
                    ("캐주얼 로퍼", 98000, 78400, 65, "SHOE04"),
                ],
            },
        ]

        # 식품 상품 데이터
        food_products = [
            {
                "category": "신선식품",
                "products": [
                    ("한우 등심 1kg", 89000, 71200, 30, "BEEF01"),
                    ("제주 감귤 5kg", 25000, 20000, 100, "ORANGE01"),
                    ("유기농 채소 세트", 35000, None, 80, "VEG01"),
                    ("노르웨이 연어 500g", 28000, 22400, 50, "SALMON01"),
                ],
            },
            {
                "category": "가공식품",
                "products": [
                    ("프리미엄 라면 세트", 15000, 12000, 200, "RAMEN01"),
                    ("수제 잼 3종 세트", 25000, None, 150, "JAM01"),
                    ("유기농 그래놀라", 18000, 14400, 120, "CEREAL01"),
                    ("올리브오일 1L", 32000, 25600, 90, "OIL01"),
                ],
            },
            {
                "category": "음료",
                "products": [
                    ("콜드브루 커피 세트", 28000, 22400, 100, "COFFEE01"),
                    ("프리미엄 녹차", 35000, None, 80, "TEA01"),
                    ("수제 과일청 3종", 42000, 33600, 60, "SYRUP01"),
                    ("유기농 주스 세트", 38000, 30400, 70, "JUICE01"),
                ],
            },
        ]

        # 모든 상품 데이터 통합
        all_product_data = [*electronics_products, *clothing_products, *food_products]

        # 상품 생성
        for category_products in all_product_data:
            category = categories.get(category_products["category"])
            if not category:
                continue

            for name, price, compare_price, stock, sku in category_products["products"]:
                # 태그 생성
                tags = []
                if compare_price and compare_price > price:
                    tags.append("세일")
                if stock > 50:
                    tags.append("인기상품")
                if random.choice([True, False]):
                    tags.append("신상품")

                # 브랜드 설정
                if category.parent and category.parent.name == "전자제품":
                    brands = ["애플", "삼성", "LG", "소니", "샤오미"]
                elif category.parent and category.parent.name == "의류":
                    brands = ["나이키", "아디다스", "유니클로", "자라", "H&M"]
                else:
                    brands = ["CJ", "롯데", "농심", "오뚜기", "풀무원"]

                product, created = Product.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "name": name,
                        "category": category,
                        "description": f"{name}의 상세 설명입니다. 최고 품질의 제품으로 고객 만족도가 매우 높습니다.",
                        "short_description": f"{name} - 프리미엄 품질 보장",
                        "price": Decimal(str(price)),
                        "compare_price": (
                            Decimal(str(compare_price)) if compare_price else None
                        ),
                        "stock": stock,
                        "is_available": True,
                        "is_active": True,
                        "brand": random.choice(brands),
                        "tags": ", ".join(tags),
                        "seller": seller,
                        "view_count": random.randint(0, 1000),
                        "sold_count": random.randint(0, 100),
                    },
                )
                products.append(product)

        self.stdout.write(f"  ✓ {len(products)}개 상품 생성 완료")
        return products

    def create_reviews(self, products, users):
        """리뷰 생성"""
        self.stdout.write("⭐ 리뷰 생성 중...")

        review_texts = [
            "정말 만족스러운 제품입니다. 강력 추천합니다!",
            "가격 대비 품질이 훌륭해요. 재구매 의사 있습니다.",
            "배송이 빠르고 포장도 꼼꼼했어요.",
            "생각보다 품질이 좋아서 놀랐습니다.",
            "디자인이 예쁘고 실용적이에요.",
            "기대 이상의 제품입니다. 대만족!",
            "품질은 좋은데 가격이 조금 비싼 것 같아요.",
            "무난한 제품입니다. 나쁘지 않아요.",
            "색상이 사진과 약간 달라요. 그래도 만족합니다.",
            "사용하기 편하고 품질도 좋습니다.",
        ]

        reviews_created = 0

        # 각 상품마다 랜덤하게 리뷰 생성
        for product in random.sample(
            products, min(len(products), 20)
        ):  # 최대 20개 상품에 리뷰
            num_reviews = random.randint(1, min(3, len(users)))  # 상품당 최대 3개 리뷰
            reviewers = random.sample(users, num_reviews)

            for user in reviewers:
                try:
                    review, created = ProductReview.objects.get_or_create(
                        product=product,
                        user=user,
                        defaults={
                            "rating": random.randint(3, 5),  # 3~5점
                            "comment": random.choice(review_texts),
                        },
                    )
                    if created:
                        reviews_created += 1
                except:
                    pass  # 중복 리뷰 무시

        self.stdout.write(f"  ✓ {reviews_created}개 리뷰 생성 완료")

    def create_sample_carts(self, users, products):
        """장바구니 샘플 생성"""
        self.stdout.write("🛒 장바구니 샘플 생성 중...")

        carts_created = 0

        # 일부 사용자에게 장바구니 생성
        for user in random.sample(users, min(3, len(users))):
            cart, created = Cart.get_or_create_active_cart(user)

            if cart:
                # 랜덤하게 상품 추가
                num_items = random.randint(1, 5)
                cart_products = random.sample(products, min(num_items, len(products)))

                for product in cart_products:
                    CartItem.objects.get_or_create(
                        cart=cart,
                        product=product,
                        defaults={"quantity": random.randint(1, 3)},
                    )

                carts_created += 1

        self.stdout.write(f"  ✓ {carts_created}개 장바구니 생성 완료")

    def create_sample_orders(self, users, products):
        """주문 샘플 생성"""
        self.stdout.write("📋 주문 샘플 생성 중...")

        orders_created = 0
        statuses = ["pending", "paid", "preparing", "shipped", "delivered"]
        payment_methods = ["card", "bank_transfer", "kakao_pay"]

        # 일부 사용자에게 주문 생성
        for user in random.sample(users, min(3, len(users))):
            # 1~2개 주문 생성
            num_orders = random.randint(1, 2)

            for _ in range(num_orders):
                # 주문 생성
                order = Order.objects.create(
                    user=user,
                    status=random.choice(statuses),
                    shipping_name=user.get_full_name() or user.username,
                    shipping_phone=user.phone_number or "010-1234-5678",
                    shipping_postal_code=user.postal_code or "12345",
                    shipping_address=user.address or "서울시 강남구 테스트로 1",
                    shipping_address_detail=user.address_detail or "101호",
                    order_memo="부재시 경비실에 맡겨주세요.",
                    payment_method=random.choice(payment_methods),
                )

                # 주문번호 생성
                date_str = timezone.now().strftime("%Y%m%d")
                order.order_number = f"{date_str}{order.pk:06d}"
                order.save()

                # 주문 상품 추가
                num_items = random.randint(1, 3)
                order_products = random.sample(products, min(num_items, len(products)))

                total_amount = Decimal("0")
                for product in order_products:
                    quantity = random.randint(1, 2)
                    order_item = OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        quantity=quantity,
                        price=product.price,
                    )
                    total_amount += order_item.get_subtotal()

                # 총액 업데이트
                order.total_amount = total_amount
                order.save()

                orders_created += 1

        self.stdout.write(f"  ✓ {orders_created}개 주문 생성 완료")

    def print_summary(self):
        """생성된 데이터 요약 출력"""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("📊 생성된 데이터 요약")
        self.stdout.write("=" * 50)

        self.stdout.write(f"카테고리: {Category.objects.count()}개")
        self.stdout.write(f"상품: {Product.objects.count()}개")
        self.stdout.write(
            f'사용자: {User.objects.filter(username__startswith="test_").count()}명'
        )
        self.stdout.write(f"리뷰: {ProductReview.objects.count()}개")
        self.stdout.write(
            f"활성 장바구니: {Cart.objects.filter(is_active=True).count()}개"
        )
        self.stdout.write(f"주문: {Order.objects.count()}건")

        self.stdout.write("\n🔑 테스트 계정 정보:")
        self.stdout.write(
            "  일반 사용자: test_user1 ~ test_user5 (비밀번호: testpass123!)"
        )
        self.stdout.write("  관리자: admin (비밀번호: admin123!)")
        self.stdout.write("=" * 50)
