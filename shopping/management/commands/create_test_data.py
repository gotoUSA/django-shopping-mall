# shopping/management/commands/create_test_data.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import random
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

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

# 환경변수 로드
load_dotenv()

User = get_user_model()


class Command(BaseCommand):
    help = "테스트용 데이터를 생성합니다 (카테고리, 상품, 사용자, 리뷰 등)"

    # 프리셋 정의
    PRESETS = {
        "minimal": {
            "categories": 2,  # 메인 카테고리 수
            "products_per_category": 5,  # 카테고리당 상품 수
            "users": 2,
            "reviews": False,
            "carts": 1,
            "orders": 1,
            "description": "최소한의 데이터 (개발 테스트용)",
        },
        "basic": {
            "categories": 3,
            "products_per_category": 12,
            "users": 5,
            "reviews": True,
            "carts": 3,
            "orders": 3,
            "description": "기본 데이터 (일반 테스트용)",
        },
        "full": {
            "categories": 5,
            "products_per_category": 20,
            "users": 20,
            "reviews": True,
            "carts": 10,
            "orders": 15,
            "description": "전체 데이터 (성능 테스트용)",
        },
    }

    def add_arguments(self, parser):
        """커맨드 옵션 추가"""
        parser.add_argument(
            "--preset",
            type=str,
            choices=["minimal", "basic", "full"],
            help="데이터 생성 프리셋 선택 (환경변수 TEST_DATA_PRESET 우선)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="기존 데이터를 모두 삭제하고 새로 생성",
        )
        parser.add_argument(
            "--users",
            type=int,
            help="생성할 테스트 사용자 수 (프리셋 설정 무시)",
        )
        parser.add_argument(
            "--reviews",
            action="store_true",
            help="리뷰 데이터도 함께 생성 (프리셋 설정 무시)",
        )
        parser.add_argument(
            "--no-reviews",
            action="store_true",
            help="리뷰 데이터 생성 안함 (프리셋 설정 무시)",
        )
        parser.add_argument(
            "--show-presets",
            action="store_true",
            help="사용 가능한 프리셋 정보 표시",
        )

    def handle(self, *args, **options):
        """메인 실행 함수"""

        # 프리셋 정보만 표시하고 종료
        if options["show_presets"]:
            self.show_presets()
            return

        # 프리셋 결정 (환경변수 > 커맨드 옵션 > 기본값)
        preset_name = os.environ.get("TEST_DATA_PRESET", options.get("preset", "basic"))

        if preset_name not in self.PRESETS:
            self.stdout.write(self.style.ERROR(f"❌ 잘못된 프리셋: {preset_name}"))
            self.stdout.write("사용 가능한 프리셋: minimal, basic, full")
            return

        preset = self.PRESETS[preset_name]

        # 커맨드 옵션으로 프리셋 설정 오버라이드
        if options.get("users"):
            preset["users"] = options["users"]
        if options.get("reviews"):
            preset["reviews"] = True
        if options.get("no_reviews"):
            preset["reviews"] = False

        # 환경변수에서 비밀번호 읽기
        self.test_user_password = os.environ.get("TEST_USER_PASSWORD", "testpass123!")
        self.test_admin_password = os.environ.get("TEST_ADMIN_PASSWORD", "admin123!")

        self.stdout.write("🚀 테스트 데이터 생성을 시작합니다...")
        self.stdout.write(
            self.style.SUCCESS(f"📋 프리셋: {preset_name} - {preset['description']}")
        )
        self.stdout.write(f"   - 카테고리: {preset['categories']}개 (메인)")
        self.stdout.write(
            f"   - 상품: 약 {preset['categories'] * preset['products_per_category']}개"
        )
        self.stdout.write(f"   - 사용자: {preset['users']}명")
        self.stdout.write(f"   - 리뷰: {'생성' if preset['reviews'] else '생성 안함'}")
        self.stdout.write("")

        # 옵션에 따라 기존 데이터 삭제
        if options["clear"]:
            self.clear_existing_data()

        # 트랜잭션으로 묶어서 실행 (에러 시 롤백)
        with transaction.atomic():
            # 1. 카테고리 생성
            categories = self.create_categories(preset)

            # 2. 사용자 생성
            users = self.create_users(preset["users"])

            # 3. 상품 생성
            products = self.create_products(categories, users, preset)

            # 4. 리뷰 생성
            if preset["reviews"]:
                self.create_reviews(products, users, preset)

            # 5. 장바구니 샘플 생성
            self.create_sample_carts(users, products, preset)

            # 6. 주문 샘플 생성
            self.create_sample_orders(users, products, preset)

        self.stdout.write(
            self.style.SUCCESS("\n✅ 테스트 데이터 생성이 완료되었습니다!")
        )
        self.print_summary()
        self.print_test_accounts()

    def show_presets(self):
        """프리셋 정보 표시"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("📋 사용 가능한 프리셋")
        self.stdout.write("=" * 60)

        for name, preset in self.PRESETS.items():
            self.stdout.write(f"\n🏷️  {name}: {preset['description']}")
            self.stdout.write(f"   - 메인 카테고리: {preset['categories']}개")
            self.stdout.write(
                f"   - 상품: 약 {preset['categories'] * preset['products_per_category']}개"
            )
            self.stdout.write(f"   - 사용자: {preset['users']}명")
            self.stdout.write(
                f"   - 리뷰: {'생성' if preset['reviews'] else '생성 안함'}"
            )
            self.stdout.write(f"   - 장바구니: {preset['carts']}개")
            self.stdout.write(f"   - 주문: {preset['orders']}건")

        self.stdout.write("\n사용법:")
        self.stdout.write("  python manage.py create_test_data --preset=minimal")
        self.stdout.write("  또는 .env 파일에 TEST_DATA_PRESET=minimal 설정")
        self.stdout.write("=" * 60)

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

    def create_categories(self, preset):
        """카테고리 생성"""
        self.stdout.write("📁 카테고리 생성 중...")

        all_categories_data = {
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
            "가전제품": {
                "slug": "appliances",
                "children": {
                    "주방가전": "kitchen-appliances",
                    "생활가전": "home-appliances",
                    "계절가전": "seasonal-appliances",
                    "미용가전": "beauty-appliances",
                },
            },
            "스포츠": {
                "slug": "sports",
                "children": {
                    "운동복": "sportswear",
                    "운동기구": "exercise-equipment",
                    "아웃도어": "outdoor",
                    "구기종목": "ball-sports",
                },
            },
        }

        # 프리셋에 따라 생성할 카테고리 선택
        categories_to_create = dict(
            list(all_categories_data.items())[: preset["categories"]]
        )

        created_categories = {}

        for parent_name, parent_data in categories_to_create.items():
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
                user.set_password(self.test_user_password)
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
            admin.set_password(self.test_admin_password)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"  ✓ 관리자 계정 생성 (admin)"))

        self.stdout.write(f"  ✓ {len(users)}명 사용자 생성 완료")
        return users

    def create_products(self, categories, users, preset):
        """상품 생성"""
        self.stdout.write("📦 상품 생성 중...")

        products = []
        seller = users[0] if users else None  # 첫 번째 사용자를 판매자로

        # 카테고리별 상품 데이터 정의
        product_templates = {
            "스마트폰": [
                ("아이폰 15 Pro", 1500000, 1350000, 50, "IP15PRO"),
                ("갤럭시 S24 Ultra", 1400000, 1260000, 30, "GS24U"),
                ("픽셀 8 Pro", 1200000, 1080000, 20, "PX8PRO"),
                ("샤오미 14", 800000, 720000, 40, "XM14"),
                ("원플러스 12", 900000, None, 35, "OP12"),
            ],
            "노트북": [
                ("맥북 프로 16인치", 3500000, 3150000, 15, "MBP16"),
                ("LG 그램 17", 2200000, 1980000, 25, "LGG17"),
                ("삼성 갤럭시북3 프로", 2400000, 2160000, 20, "GB3PRO"),
                ("레노버 씽크패드 X1", 2000000, 1800000, 18, "TPX1"),
                ("ASUS 젠북", 1800000, None, 22, "ASUS01"),
            ],
            "태블릿": [
                ("아이패드 프로 12.9", 1800000, 1620000, 35, "IPADPRO"),
                ("갤럭시 탭 S9 Ultra", 1500000, 1350000, 28, "GTS9U"),
                ("아이패드 에어", 900000, 810000, 45, "IPADAIR"),
                ("샤오미 패드 6", 500000, None, 60, "MIPAD6"),
            ],
            "남성의류": [
                ("프리미엄 면 셔츠", 89000, 71200, 100, "MCOT01"),
                ("슬림핏 청바지", 79000, None, 80, "MJEAN01"),
                ("캐주얼 후드티", 59000, 47200, 120, "MHOOD01"),
                ("비즈니스 정장 세트", 450000, 360000, 25, "MSUIT01"),
                ("스포츠 자켓", 120000, 96000, 40, "MJACK01"),
            ],
            "여성의류": [
                ("플로럴 원피스", 125000, 100000, 60, "WDRESS01"),
                ("캐시미어 니트", 180000, 144000, 40, "WKNIT01"),
                ("하이웨이스트 스커트", 65000, None, 70, "WSKIRT01"),
                ("트렌치 코트", 280000, 224000, 30, "WCOAT01"),
                ("실크 블라우스", 95000, 76000, 50, "WBLOUSE01"),
            ],
            "신선식품": [
                ("한우 등심 1kg", 89000, 71200, 30, "BEEF01"),
                ("제주 감귤 5kg", 25000, 20000, 100, "ORANGE01"),
                ("유기농 채소 세트", 35000, None, 80, "VEG01"),
                ("노르웨이 연어 500g", 28000, 22400, 50, "SALMON01"),
                ("친환경 계란 30구", 15000, None, 200, "EGG01"),
            ],
            # minimal preset용 기본 상품
            "default": [
                ("베스트셀러 상품", 50000, 45000, 100, "BEST01"),
                ("인기 상품", 30000, None, 80, "POP01"),
                ("신제품", 70000, 63000, 50, "NEW01"),
                ("특가 상품", 20000, 16000, 150, "SALE01"),
                ("프리미엄 상품", 100000, None, 30, "PREM01"),
            ],
        }

        sku_counter = 1
        for category_name, category in categories.items():
            # 부모 카테고리는 건너뛰기
            if not category.parent:
                continue

            # 해당 카테고리의 상품 템플릿 선택
            templates = product_templates.get(
                category_name, product_templates["default"]
            )

            # 프리셋에 따라 생성할 상품 수 결정
            products_to_create = min(
                len(templates), preset["products_per_category"] // 3
            )

            for i in range(products_to_create):
                template = templates[i % len(templates)]
                name, price, compare_price, stock, base_sku = template

                # SKU 유니크하게 생성
                sku = f"{base_sku}_{sku_counter}"
                sku_counter += 1

                # 태그 생성
                tags = []
                if compare_price and compare_price < price:
                    tags.append("세일")
                if stock > 50:
                    tags.append("인기상품")
                if random.choice([True, False]):
                    tags.append("신상품")

                # 브랜드 설정
                if category.parent.name == "전자제품":
                    brands = ["애플", "삼성", "LG", "소니", "샤오미"]
                elif category.parent.name == "의류":
                    brands = ["나이키", "아디다스", "유니클로", "자라", "H&M"]
                elif category.parent.name == "가전제품":
                    brands = ["삼성", "LG", "다이슨", "필립스", "쿠쿠"]
                elif category.parent.name == "스포츠":
                    brands = ["나이키", "아디다스", "언더아머", "뉴발란스", "푸마"]
                else:
                    brands = ["CJ", "롯데", "농심", "오뚜기", "풀무원"]

                product, created = Product.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "name": f"{name} ({category_name})",
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

    def create_reviews(self, products, users, preset):
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

        # 프리셋에 따라 리뷰를 생성할 상품 수 결정
        if preset["categories"] == 2:  # minimal
            products_with_reviews = min(len(products), 5)
        elif preset["categories"] == 3:  # basic
            products_with_reviews = min(len(products), 20)
        else:  # full
            products_with_reviews = min(len(products), 50)

        # 각 상품마다 랜덤하게 리뷰 생성
        for product in random.sample(products, products_with_reviews):
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

    def create_sample_carts(self, users, products, preset):
        """장바구니 샘플 생성"""
        self.stdout.write("🛒 장바구니 샘플 생성 중...")

        carts_created = 0

        # 프리셋에 따라 장바구니 생성 수 결정
        num_carts = min(preset["carts"], len(users))

        # 일부 사용자에게 장바구니 생성
        for user in random.sample(users, num_carts):
            cart, created = Cart.get_or_create_active_cart(user)

            if cart:
                # 랜덤하게 상품 추가
                num_items = random.randint(1, min(5, len(products)))
                cart_products = random.sample(products, num_items)

                for product in cart_products:
                    CartItem.objects.get_or_create(
                        cart=cart,
                        product=product,
                        defaults={"quantity": random.randint(1, 3)},
                    )

                carts_created += 1

        self.stdout.write(f"  ✓ {carts_created}개 장바구니 생성 완료")

    def create_sample_orders(self, users, products, preset):
        """주문 샘플 생성"""
        self.stdout.write("📋 주문 샘플 생성 중...")

        orders_created = 0
        statuses = ["pending", "paid", "preparing", "shipped", "delivered"]
        payment_methods = ["card", "bank_transfer", "kakao_pay"]

        # 프리셋에 따라 주문 생성 수 결정
        num_users_with_orders = min(preset["orders"] // 2 + 1, len(users))

        # 일부 사용자에게 주문 생성
        for user in random.sample(users, num_users_with_orders):
            # 사용자당 주문 수
            if preset["categories"] == 2:  # minimal
                num_orders = 1
            elif preset["categories"] == 3:  # basic
                num_orders = random.randint(1, 2)
            else:  # full
                num_orders = random.randint(1, 3)

            for _ in range(num_orders):
                if orders_created >= preset["orders"]:
                    break

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
                num_items = random.randint(1, min(3, len(products)))
                order_products = random.sample(products, num_items)

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
        self.stdout.write("=" * 50)

    def print_test_accounts(self):
        """테스트 계정 정보 출력"""
        self.stdout.write("\n🔑 테스트 계정 정보:")

        # 환경변수 설정 여부 확인
        if os.environ.get("TEST_USER_PASSWORD"):
            user_pwd_info = "환경변수 TEST_USER_PASSWORD 참조"
        else:
            user_pwd_info = f"비밀번호: {self.test_user_password}"

        if os.environ.get("TEST_ADMIN_PASSWORD"):
            admin_pwd_info = "환경변수 TEST_ADMIN_PASSWORD 참조"
        else:
            admin_pwd_info = f"비밀번호: {self.test_admin_password}"

        num_users = User.objects.filter(username__startswith="test_").count()
        if num_users > 0:
            self.stdout.write(f"  일반 사용자: test_user1 ~ test_user{num_users}")
            self.stdout.write(f"  {user_pwd_info}")

        if User.objects.filter(username="admin").exists():
            self.stdout.write(f"  관리자: admin")
            self.stdout.write(f"  {admin_pwd_info}")

        self.stdout.write("\n💡 팁: .env 파일에서 TEST_USER_PASSWORD와")
        self.stdout.write(
            "  TEST_ADMIN_PASSWORD를 설정하여 비밀번호를 변경할 수 있습니다."
        )
        self.stdout.write("=" * 50)
