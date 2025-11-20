"""
ProductService 테스트
"""
import pytest
from shopping.services import ProductService
from shopping.tests.factories import ProductFactory, ProductImageFactory


@pytest.mark.django_db
class TestProductService:
    """ProductService 기능 테스트"""

    def test_set_primary_image_updates_others(self):
        """
        [정상 케이스] 새로운 대표 이미지 설정 시 기존 대표 이미지는 해제되어야 함
        """
        # Arrange
        product = ProductFactory()
        old_primary = ProductImageFactory(product=product, is_primary=True)
        new_primary = ProductImageFactory(product=product, is_primary=False)

        # Act
        # 새로운 이미지를 대표로 설정 (메모리 상에서 변경 후 서비스 호출)
        new_primary.is_primary = True
        ProductService.set_primary_image(new_primary)

        # Assert
        old_primary.refresh_from_db()
        new_primary.refresh_from_db()

        assert old_primary.is_primary is False
        assert new_primary.is_primary is True

    def test_set_primary_image_initial(self):
        """
        [정상 케이스] 이미지가 없는 상태에서 첫 이미지를 대표로 설정
        """
        # Arrange
        product = ProductFactory()
        image = ProductImageFactory(product=product, is_primary=False)

        # Act
        image.is_primary = True
        ProductService.set_primary_image(image)

        # Assert
        image.refresh_from_db()
        assert image.is_primary is True

    def test_set_primary_image_ignored_if_not_primary(self):
        """
        [경계값] is_primary=False인 이미지가 전달되면 로직이 실행되지 않아야 함
        """
        # Arrange
        product = ProductFactory()
        primary_image = ProductImageFactory(product=product, is_primary=True)
        other_image = ProductImageFactory(product=product, is_primary=False)

        # Act
        # is_primary=False 상태로 서비스 호출
        ProductService.set_primary_image(other_image)

        # Assert
        primary_image.refresh_from_db()
        other_image.refresh_from_db()

        assert primary_image.is_primary is True  # 기존 대표 유지 확인
        assert other_image.is_primary is False   # 변경 없음 확인

    def test_set_primary_image_exclude_self(self):
        """
        [경계값] 자기 자신이 이미 대표인 경우, 자기 자신을 해제하지 않아야 함
        """
        # Arrange
        product = ProductFactory()
        image = ProductImageFactory(product=product, is_primary=True)

        # Act
        ProductService.set_primary_image(image)

        # Assert
        image.refresh_from_db()
        assert image.is_primary is True

    def test_set_primary_image_different_product(self):
        """
        [예외 케이스] 다른 상품의 대표 이미지에는 영향을 주지 않아야 함
        """
        # Arrange
        product1 = ProductFactory()
        product2 = ProductFactory()

        # product1: 기존 대표 있음
        p1_primary = ProductImageFactory(product=product1, is_primary=True)
        # product2: 대표 있음
        p2_primary = ProductImageFactory(product=product2, is_primary=True)

        # product1의 새 이미지
        p1_new = ProductImageFactory(product=product1, is_primary=False)

        # Act
        # product1의 새 이미지를 대표로 설정
        p1_new.is_primary = True
        ProductService.set_primary_image(p1_new)

        # Assert
        p1_primary.refresh_from_db()
        p1_new.refresh_from_db()
        p2_primary.refresh_from_db()

        assert p1_primary.is_primary is False  # product1 기존 해제
        assert p1_new.is_primary is True       # product1 신규 설정
        assert p2_primary.is_primary is True   # product2 영향 없음
