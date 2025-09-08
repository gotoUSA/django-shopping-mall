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
        """주문 조회 - 관리자는 전체, 일반 사용자는 본인 것만"""
        if self.request.user.is_staff or self.request.user.is_superuser:
            # 관리자는 모든 주문 조회 가능
            return Order.objects.all().prefetch_related("order_items__product")
        else:
            # 일반 사용자는 본인 주문만 조회 가능
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

    def list(self, request, *args, **kwargs):
        """주문 목록 조회 - 페이지네이션 구조 확인"""
        queryset = self.filter_queryset(self.get_queryset())

        # 페이지네이션이 설정되어 있으면
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # 페이지네이션이 없으면
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
