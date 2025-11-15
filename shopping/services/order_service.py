"""주문 서비스 레이어"""

import logging
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F

from ..models.cart import Cart
from ..models.order import Order, OrderItem
from ..models.product import Product
from .point_service import PointService
from .shipping_service import ShippingService

logger = logging.getLogger(__name__)


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
        shipping_address_detail: str,
        order_memo: str = "",
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
            shipping_address_detail: 상세주소
            order_memo: 배송 요청사항
            use_points: 사용할 포인트

        Returns:
            Order: 생성된 주문

        Raises:
            OrderServiceError: 재고 부족 등의 오류
        """
        logger.info(
            f"주문 생성 시작: user_id={user.id}, cart_id={cart.id}, "
            f"use_points={use_points}, postal_code={shipping_postal_code}"
        )

        # 1. 주문 총액 계산
        total_amount = cart.total_amount

        # 2. 배송비 계산
        shipping_result = ShippingService.calculate_fee(
            total_amount=total_amount, postal_code=shipping_postal_code
        )
        logger.info(
            f"배송비 계산 완료: total_amount={total_amount}, "
            f"shipping_fee={shipping_result['shipping_fee']}, "
            f"additional_fee={shipping_result['additional_fee']}, "
            f"is_free_shipping={shipping_result['is_free_shipping']}"
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
            is_free_shipping=shipping_result["is_free_shipping"],
            used_points=use_points,
            final_amount=final_amount,
            shipping_name=shipping_name,
            shipping_phone=shipping_phone,
            shipping_postal_code=shipping_postal_code,
            shipping_address=shipping_address,
            shipping_address_detail=shipping_address_detail,
            order_memo=order_memo,
        )
        logger.info(
            f"주문 생성 완료: order_id={order.id}, order_number={order.order_number}, "
            f"total_amount={total_amount}, final_amount={final_amount}"
        )

        # 5. 주문 아이템 생성 + 재고 차감
        OrderService._create_order_items_and_decrease_stock(order, cart)

        # 6. 포인트 사용 처리
        if use_points > 0:
            OrderService._process_point_usage(user, order, use_points, total_amount, final_amount)

        # 7. 장바구니 비우기
        cart.items.all().delete()
        logger.info(f"장바구니 비우기 완료: cart_id={cart.id}, user_id={user.id}")

        logger.info(
            f"주문 생성 프로세스 완료: order_id={order.id}, order_number={order.order_number}, "
            f"user_id={user.id}"
        )

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
        logger.info(
            f"주문 아이템 생성 및 재고 차감 시작: order_id={order.id}, "
            f"cart_items_count={cart.items.count()}"
        )

        for cart_item in cart.items.all():
            # 재고 최종 확인 (select_for_update로 동시성 제어)
            product = Product.objects.select_for_update().get(pk=cart_item.product.pk)

            if product.stock < cart_item.quantity:
                logger.error(
                    f"재고 부족: product_id={product.pk}, product_name={product.name}, "
                    f"requested={cart_item.quantity}, available={product.stock}"
                )
                raise OrderServiceError(
                    f"{product.name}의 재고가 부족합니다. "
                    f"(요청: {cart_item.quantity}개, 재고: {product.stock}개)"
                )

            # F() 객체를 사용한 안전한 재고 차감
            Product.objects.filter(pk=product.pk).update(stock=F("stock") - cart_item.quantity)
            logger.info(
                f"재고 차감: product_id={product.pk}, product_name={product.name}, "
                f"quantity={cart_item.quantity}, previous_stock={product.stock}"
            )

            # OrderItem 생성
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_name=cart_item.product.name,
                quantity=cart_item.quantity,
                price=cart_item.product.price,
            )
            logger.info(
                f"주문 아이템 생성: order_id={order.id}, product_id={product.pk}, "
                f"product_name={product.name}, quantity={cart_item.quantity}, price={cart_item.product.price}"
            )

        logger.info(f"주문 아이템 생성 및 재고 차감 완료: order_id={order.id}")

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
        logger.info(
            f"포인트 사용 처리 시작: user_id={user.id}, order_id={order.id}, "
            f"use_points={use_points}"
        )

        # 포인트 차감 (PointService 사용)
        PointService.use_points(
            user=user,
            amount=use_points,
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

        logger.info(
            f"포인트 사용 완료: user_id={user.id}, order_id={order.id}, "
            f"use_points={use_points}"
        )

    @staticmethod
    @transaction.atomic
    def cancel_order(order: Order) -> None:
        """
        주문 취소 처리

        주문 상태를 취소로 변경하고, 재고를 복구합니다.
        - pending 상태: 재고만 복구
        - paid 상태: 재고 복구 + sold_count 차감

        Args:
            order: 취소할 주문

        Raises:
            OrderServiceError: 취소할 수 없는 주문인 경우
        """
        # 동시성 제어: 주문 잠금 (select_for_update)
        order = Order.objects.select_for_update().get(pk=order.pk)

        # 트랜잭션 내에서 취소 가능 여부 체크
        if not order.can_cancel:
            logger.warning(
                f"취소 불가능한 주문 취소 시도: order_id={order.id}, "
                f"status={order.status}, user_id={order.user.id}"
            )
            raise OrderServiceError("취소할 수 없는 주문입니다.")

        logger.info(
            f"주문 취소 시작: order_id={order.id}, order_number={order.order_number}, "
            f"status={order.status}, user_id={order.user.id}"
        )

        # 주문 상태에 따라 재고/sold_count 복구
        for item in order.order_items.select_for_update():
            if item.product:
                if order.status == "paid":
                    # paid 상태: 재고 복구 + sold_count 차감
                    Product.objects.filter(pk=item.product.pk).update(
                        stock=F("stock") + item.quantity,
                        sold_count=F("sold_count") - item.quantity,
                    )
                    logger.info(
                        f"재고 및 판매량 복구: product_id={item.product.pk}, "
                        f"product_name={item.product_name}, quantity={item.quantity}"
                    )
                elif order.status == "pending":
                    # pending 상태: 재고만 복구 (sold_count는 아직 증가 안했음)
                    Product.objects.filter(pk=item.product.pk).update(stock=F("stock") + item.quantity)
                    logger.info(
                        f"재고 복구: product_id={item.product.pk}, "
                        f"product_name={item.product_name}, quantity={item.quantity}"
                    )

        # 주문 상태 변경
        order.status = "canceled"
        order.save(update_fields=["status", "updated_at"])

        logger.info(
            f"주문 취소 완료: order_id={order.id}, order_number={order.order_number}, "
            f"user_id={order.user.id}"
        )
