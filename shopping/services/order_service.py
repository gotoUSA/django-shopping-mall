"""주문 서비스 레이어"""

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F

from ..models.cart import Cart
from ..models.order import Order, OrderItem
from ..models.point_history import PointHistory
from ..models.product import Product
from .shipping_service import ShippingService


class OrderServiceError(Exception):
    """주문 서비스 관련 에러"""

    pass


class OrderService:
    """주문 관련 비즈니스 로직을 처리하는 서비스"""

    @staticmethod
    @transaction.atomic
    def create_order_from_cart(
        user,
        cart: Cart,
        shipping_name: str,
        shipping_phone: str,
        shipping_postal_code: str,
        shipping_address: str,
        shipping_detail_address: str,
        request_message: str = "",
        use_points: int = 0,
    ) -> Order:
        """
        장바구니에서 주문 생성

        Args:
            user: 주문 사용자
            cart: 장바구니
            shipping_name: 수령인 이름
            shipping_phone: 수령인 전화번호
            shipping_postal_code: 우편번호
            shipping_address: 주소
            shipping_detail_address: 상세주소
            request_message: 배송 요청사항
            use_points: 사용할 포인트

        Returns:
            Order: 생성된 주문

        Raises:
            OrderServiceError: 재고 부족 등의 오류
        """
        # 1. 주문 총액 계산
        total_amount = cart.total_amount

        # 2. 배송비 계산
        shipping_result = ShippingService.calculate_fee(
            total_amount=total_amount, postal_code=shipping_postal_code
        )

        # 3. 최종 결제 금액 계산 (배송비 포함, 포인트 차감)
        total_with_shipping = (
            total_amount + shipping_result["shipping_fee"] + shipping_result["additional_fee"]
        )
        final_amount = max(Decimal("0"), total_with_shipping - Decimal(str(use_points)))

        # 4. 주문 생성
        order = Order.objects.create(
            user=user,
            status="pending",  # 결제 대기 상태
            total_amount=total_amount,
            shipping_fee=shipping_result["shipping_fee"],
            additional_shipping_fee=shipping_result["additional_fee"],
            used_points=use_points,
            final_amount=final_amount,
            shipping_name=shipping_name,
            shipping_phone=shipping_phone,
            shipping_postal_code=shipping_postal_code,
            shipping_address=shipping_address,
            shipping_detail_address=shipping_detail_address,
            request_message=request_message,
        )

        # 5. 주문 아이템 생성 + 재고 차감
        OrderService._create_order_items_and_decrease_stock(order, cart)

        # 6. 포인트 사용 처리
        if use_points > 0:
            OrderService._process_point_usage(user, order, use_points, total_amount, final_amount)

        # 7. 장바구니 비우기
        cart.items.all().delete()

        return order

    @staticmethod
    def _create_order_items_and_decrease_stock(order: Order, cart: Cart) -> None:
        """
        주문 아이템 생성 및 재고 차감

        Args:
            order: 주문
            cart: 장바구니

        Raises:
            OrderServiceError: 재고 부족
        """
        for cart_item in cart.items.all():
            # 재고 최종 확인 (select_for_update로 동시성 제어)
            product = Product.objects.select_for_update().get(pk=cart_item.product.pk)

            if product.stock < cart_item.quantity:
                raise OrderServiceError(
                    f"{product.name}의 재고가 부족합니다. "
                    f"(요청: {cart_item.quantity}개, 재고: {product.stock}개)"
                )

            # F() 객체를 사용한 안전한 재고 차감
            Product.objects.filter(pk=product.pk).update(stock=F("stock") - cart_item.quantity)

            # OrderItem 생성
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_name=cart_item.product.name,
                quantity=cart_item.quantity,
                price=cart_item.product.price,
            )

    @staticmethod
    def _process_point_usage(
        user, order: Order, use_points: int, total_amount: Decimal, final_amount: Decimal
    ) -> None:
        """
        포인트 사용 처리

        Args:
            user: 사용자
            order: 주문
            use_points: 사용할 포인트
            total_amount: 주문 총액
            final_amount: 최종 결제 금액
        """
        # 포인트 차감
        user.use_points(use_points)

        # 포인트 사용 이력 기록
        PointHistory.create_history(
            user=user,
            points=-use_points,  # 음수로 기록
            type="use",
            order=order,
            description=f"주문 #{order.order_number} 결제시 사용",
            metadata={
                "order_id": order.id,
                "order_number": order.order_number,
                "total_amount": str(total_amount),
                "final_amount": str(final_amount),
            },
        )
