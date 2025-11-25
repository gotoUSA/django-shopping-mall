"""로드 테스트용 데이터 생성

1000명의 사용자와 100개의 상품을 미리 생성합니다.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from shopping.tests.factories import UserFactory, ProductFactory


def setup_test_data():
    """테스트 데이터 생성"""
    print("테스트 사용자 생성 중...")
    users = []
    for i in range(1000):
        user = UserFactory(
            username=f'load_test_user_{i}',
            email=f'load_test_{i}@example.com',
            is_email_verified=True
        )
        user.set_password('testpass123')
        user.save()
        users.append(user)

        if (i + 1) % 100 == 0:
            print(f"{i + 1}/1000 사용자 생성 완료")

    print("\n테스트 상품 생성 중...")
    products = []
    for i in range(100):
        product = ProductFactory(
            name=f'성능테스트 상품 {i}',
            price=10000 + (i * 1000),
            stock=1000,
            is_active=True
        )
        products.append(product)

    print(f"100개 상품 생성 완료")
    print(f"\n총 {len(users)}명 사용자, {len(products)}개 상품 생성 완료")


if __name__ == '__main__':
    setup_test_data()
