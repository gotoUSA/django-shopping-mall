from __future__ import annotations

import logging
from typing import Any

from django.db.models import Count
from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import filters, permissions, serializers as drf_serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer, ValidationError

from ..models.order import Order
from ..permissions import IsOrderOwnerOrAdmin
from ..serializers.order_serializers import OrderCreateSerializer, OrderDetailSerializer, OrderListSerializer
from ..services.order_service import OrderService, OrderServiceError
from ..throttles import OrderCancelRateThrottle, OrderCreateRateThrottle

logger = logging.getLogger(__name__)


# ===== Swagger 문서화용 응답 Serializers =====

class OrderCreateResponseSerializer(drf_serializers.Serializer):
    """주문 생성 성공 응답"""
    order_id = drf_serializers.IntegerField(help_text="생성된 주문 ID")
    order_number = drf_serializers.CharField(help_text="주문 번호")
    status = drf_serializers.CharField(help_text="주문 상태 (pending)")
    task_id = drf_serializers.CharField(help_text="비동기 작업 ID")
    message = drf_serializers.CharField()
    status_url = drf_serializers.CharField(help_text="주문 상태 확인 URL")


class OrderCancelResponseSerializer(drf_serializers.Serializer):
    """주문 취소 성공 응답"""
    message = drf_serializers.CharField()


class OrderErrorResponseSerializer(drf_serializers.Serializer):
    """주문 에러 응답"""
    error = drf_serializers.CharField()
    message = drf_serializers.CharField(required=False)
    detail = drf_serializers.CharField(required=False)
    verification_required = drf_serializers.BooleanField(required=False)
    verification_url = drf_serializers.CharField(required=False)


class OrderPagination(PageNumberPagination):
    """주문 목록 페이지네이션"""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(
        summary="주문 목록 조회",
        description="""
내 주문 목록을 조회합니다.

**필터링:**
- `status`: 주문 상태 필터 (pending, paid, shipped, delivered, canceled)

**정렬:**
- `ordering`: created_at, -created_at (기본: 최신순)

**페이지네이션:**
- `page`: 페이지 번호
- `page_size`: 페이지당 항목 수 (기본: 10, 최대: 100)
        """,
        tags=["Orders"],
    ),
    retrieve=extend_schema(
        summary="주문 상세 조회",
        description="주문 상세 정보를 조회합니다. 본인 주문 또는 관리자만 조회 가능합니다.",
        tags=["Orders"],
    ),
)
class OrderViewSet(viewsets.ModelViewSet):
    """
    주문 관리 ViewSet

    엔드포인트:
    - GET    /api/orders/           - 주문 목록 조회
    - POST   /api/orders/           - 주문 생성
    - GET    /api/orders/{id}/      - 주문 상세 조회
    - POST   /api/orders/{id}/cancel/ - 주문 취소

    권한:
    - 인증된 사용자만 접근 가능
    - 본인 주문 또는 관리자만 조회/수정 가능
    """

    permission_classes = [permissions.IsAuthenticated, IsOrderOwnerOrAdmin]
    pagination_class = OrderPagination

    # 필터링 및 정렬 설정
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_throttles(self):
        """액션별로 다른 throttle 적용"""
        if self.action == "create":
            return [OrderCreateRateThrottle()]
        elif self.action == "cancel":
            return [OrderCancelRateThrottle()]
        return super().get_throttles()

    def get_queryset(self) -> Any:
        """
        주문 조회 쿼리셋

        성능 최적화:
        - select_related("user"): N+1 방지
        - prefetch_related("order_items__product"): 주문 아이템 최적화
        - annotate(item_count): 아이템 개수 미리 계산

        보안:
        - 관리자: 전체 주문 조회
        - 일반 사용자: 본인 주문만 조회
        """
        queryset = (
            Order.objects.select_related("user")
            .prefetch_related("order_items__product")
            .annotate(item_count=Count("order_items"))
        )

        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        else:
            return queryset.filter(user=self.request.user)

    def get_serializer_class(self) -> type[BaseSerializer]:
        if self.action == "list":
            return OrderListSerializer
        elif self.action == "create":
            return OrderCreateSerializer
        return OrderDetailSerializer

    @extend_schema(
        request=OrderCreateSerializer,
        responses={
            202: OrderCreateResponseSerializer,
            400: OrderErrorResponseSerializer,
            403: OrderErrorResponseSerializer,
        },
        summary="주문 생성",
        description="""
새 주문을 생성합니다.

**필수 조건:**
- 이메일 인증이 완료된 사용자만 주문 가능

**요청 본문:**
```json
{
    "items": [
        {"product_id": 1, "quantity": 2},
        {"product_id": 3, "quantity": 1}
    ],
    "shipping_address": "서울시 강남구...",
    "use_points": 1000
}
```

**비동기 처리:**
- 주문은 비동기로 처리되며, 202 Accepted 응답을 반환합니다.
- `status_url`을 통해 주문 상태를 확인할 수 있습니다.
        """,
        tags=["Orders"],
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """주문 생성 (이메일 인증 필요)"""
        # 이메일 인증 체크
        if not request.user.is_email_verified:
            logger.warning(f"미인증 사용자 주문 생성 시도: user_id={request.user.id}, email={request.user.email}")
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

        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # 비동기 처리를 위해 하이브리드 방식 사용
            order, task_id = serializer.create_hybrid(serializer.validated_data)

            logger.info(
                f"주문 하이브리드 생성: order_id={order.id}, order_number={order.order_number}, "
                f"task_id={task_id}, user_id={request.user.id}"
            )

            return Response(
                {
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "status": "pending",
                    "task_id": task_id,
                    "message": "주문 처리 중입니다. 잠시 후 주문 내역에서 확인해주세요.",
                    "status_url": f"/api/orders/{order.id}/",
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except ValidationError as e:
            logger.error(f"주문 생성 실패 (ValidationError): user_id={request.user.id}, error={str(e)}")
            return Response(
                e.detail if hasattr(e, "detail") else {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except OrderServiceError as e:
            logger.error(f"주문 생성 실패 (OrderServiceError): user_id={request.user.id}, error={str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"주문 생성 실패 (Unexpected): user_id={request.user.id}, error={str(e)}", exc_info=True)
            return Response({"error": "주문 생성 중 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=None,
        responses={
            200: OrderCancelResponseSerializer,
            400: OrderErrorResponseSerializer,
        },
        summary="주문 취소",
        description="""
주문을 취소합니다.

**취소 가능 조건:**
- 배송 전 상태의 주문만 취소 가능
- 본인 주문만 취소 가능

**처리 내용:**
- 주문 상태를 'canceled'로 변경
- 사용한 포인트 환불
- 재고 복구
        """,
        tags=["Orders"],
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: int | None = None) -> Response:
        """주문 취소"""
        order = self.get_object()

        try:
            OrderService.cancel_order(order)
            logger.info(f"주문 취소 성공: order_id={order.id}, order_number={order.order_number}, user_id={request.user.id}")
            return Response({"message": "주문이 취소되었습니다."})
        except OrderServiceError as e:
            logger.warning(f"주문 취소 실패: order_id={order.id}, user_id={request.user.id}, error={str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """주문 목록 조회"""
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
