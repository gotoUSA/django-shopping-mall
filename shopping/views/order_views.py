import logging

from django.db import transaction
from django.db.models import F
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import permissions, status, viewsets, filters
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models.product import Product
from ..models.order import Order
from ..serializers.order_serializers import OrderCreateSerializer, OrderDetailSerializer, OrderListSerializer

logger = logging.getLogger(__name__)


class OrderPagination(PageNumberPagination):
    """주문 목록 페이지네이션"""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class OrderViewSet(viewsets.ModelViewSet):
    """주문 관리 ViewSet"""

    permission_classes = [permissions.IsAuthenticated]

    # 페이지네이션 설정
    pagination_class = OrderPagination

    # 필터링 및 정렬 설정
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status"]  # status 필터 지원
    ordering_fields = ["created_at"]  # created_at 정렬만 지원
    ordering = ["-created_at"]  # 기본 정렬: 최신순

    def get_queryset(self):
        """주문 조회 - 관리자는 전체, 일반 사용자는 본인 것만"""
        if self.request.user.is_staff or self.request.user.is_superuser:
            # 관리자는 모든 주문 조회 가능
            return Order.objects.all().prefetch_related("order_items__product")
        else:
            # 일반 사용자는 본인 주문만 조회 가능
            return Order.objects.filter(user=self.request.user).prefetch_related("order_items__product")

    def get_serializer_class(self):
        if self.action == "list":
            return OrderListSerializer
        elif self.action == "create":
            return OrderCreateSerializer
        return OrderDetailSerializer

    # create 메서드 오버라이드
    def create(self, request, *args, **kwargs):
        """
        주문 생성

        이메일 인증이 완료된 사용자만 주문을 생성할 수 있습니다.
        """
        # 이메일 인증 체크
        if not request.user.is_email_verified:
            logger.warning(f"미인증 사용자 주문 생성 시도: user_id={request.user.id}, " f"email={request.user.email}")
            return Response(
                {
                    "error": "이메일 인증이 필요합니다.",
                    "message": "주문을 생성하려면 먼저 이메일 인증을 완료해주세요.",
                    "detail": "이메일 인증 후 모든 기능을 사용하실 수 있습니다.",
                    "verification_required": True,
                    "verification_url": "/api/email-verification/send/",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # 이메일 인증이 완료되었다면 정상적으로 주문 생성
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """주문 취소"""
        order = self.get_object()

        with transaction.atomic():
            # 동시성 제어: 주문 잠금 (select_for_update)
            order = Order.objects.select_for_update().get(pk=order.pk)

            # 트랜잭션 내에서 다시 취소 가능 여부 체크
            if not order.can_cancel:
                return Response(
                    {"error": "취소할 수 없는 주문입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 주문 상태가 "paid"인 경우에만 재고 북구 및 sold_count 차감
            if order.status == "paid":
                # 재고 복구 및 sold_count 차감 (결제 완료된 주문만)
                for item in order.order_items.select_for_update():
                    if item.product:
                        product = Product.objects.select_for_update().get(pk=item.product.pk)

                        # F() 객체로 안전하게 재고 복구 및 sold_count 차감
                        Product.objects.filter(pk=product.pk).update(
                            stock=F("stock") + item.quantity,
                            sold_count=F("sold_count") - item.quantity,
                        )
            # pending 상태는 재초 처리 안 함

            # 주문 상태 변경
            order.status = "canceled"
            order.save(update_fields=["status", "updated_at"])

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
