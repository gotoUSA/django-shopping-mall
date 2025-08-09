from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction

from ..models.order import Order, OrderItem
from ..serializers.order_serializers import (
    OrderListSerializer,
    OrderDetailSerializer,
    OrderCreateSerializer,
)


class OrderViewSet(viewsets.ModelViewSet):
    """주문 관리 ViewSet"""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """본인 주문만 조회"""
        return Order.objects.filter(user=self.request.user).prefetch_related(
            "order_items__product"
        )

    def get_serializer_class(self):
        if self.action == "list":
            return OrderListSerializer
        elif self.action == "create":
            return OrderCreateSerializer
        return OrderDetailSerializer

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """주문 취소"""
        order = self.get_object()

        if not order.can_cancel:
            return Response(
                {"error": "취소할 수 없는 주문입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # 재고 복구
            for item in order.order_items.all():
                if item.product:
                    item.product.stock += item.quantity
                    item.product.save()

            # 주문 상태 변경
            order.status = "cancelled"
            order.save()

        return Response({"message": "주문이 취소되었습니다."})
