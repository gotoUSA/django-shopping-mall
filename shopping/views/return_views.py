from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from shopping.models import Return
from shopping.serializers.return_serializers import (
    ReturnApproveSerializer,
    ReturnCompleteSerializer,
    ReturnConfirmReceiveSerializer,
    ReturnCreateSerializer,
    ReturnDetailSerializer,
    ReturnListSerializer,
    ReturnRejectSerializer,
    ReturnUpdateSerializer,
)


class ReturnViewSet(viewsets.ModelViewSet):
    """
    교환/환불 API ViewSet

    기능:
    - list: 내 교환/환불 목록 조회
    - retrieve: 교환/환불 상세 조회
    - create: 교환/환불 신청 (POST /api/orders/{order_id}/returns/)
    - update: 송장번호 입력 (PATCH)
    - destroy: 신청 취소 (DELETE)

    액션:
    - approve: 승인 (판매자)
    - reject: 거부 (판매자)
    - confirm_receive: 반품 도착 확인 (판매자)
    - complete: 완료 처리 (판매자)
    """

    permission_classes = [IsAuthenticated]
    queryset = Return.objects.all()

    def get_serializer_class(self):
        """액션별 Serializer 선택"""
        if self.action == "create":
            return ReturnCreateSerializer
        elif self.action == "list":
            return ReturnListSerializer
        elif self.action in ["retrieve"]:
            return ReturnDetailSerializer
        elif self.action in ["update", "partial_update"]:
            return ReturnUpdateSerializer
        elif self.action == "approve":
            return ReturnApproveSerializer
        elif self.action == "reject":
            return ReturnRejectSerializer
        elif self.action == "confirm_receive":
            return ReturnConfirmReceiveSerializer
        elif self.action == "complete":
            return ReturnCompleteSerializer
        return ReturnListSerializer

    def get_queryset(self):
        """
        현재 사용자의 교환/환불만 조회

        향후 판매자 권한 추가 시:
        - 판매자는 자신의 상품에 대한 교환/환불 조회 가능
        """
        user = self.request.user
        queryset = (
            Return.objects.filter(user=user)
            .select_related("order", "exchange_product")
            .prefetch_related("return_items__order_item__product")
        )

        # 필터링
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        type_filter = self.request.query_params.get("type")
        if type_filter:
            queryset = queryset.filter(type=type_filter)

        return queryset

    def create(self, request, *args, **kwargs):
        """
        교환/환불 신청

        URL: POST /api/orders/{order_id}/returns/
        """
        order_id = kwargs.get("order_id")

        serializer = self.get_serializer(data=request.data, context={"request": request, "order_id": order_id})

        serializer.is_valid(raise_exception=True)
        return_obj = serializer.save()

        # 응답
        return Response(
            {
                "message": f"{return_obj.get_type_display()} 신청이 완료되었습니다.",
                "return": ReturnDetailSerializer(return_obj).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        """
        신청 취소

        조건:
        - 신청(requested) 상태에서만 취소 가능
        """
        return_obj = self.get_object()

        # 권한 확인
        if return_obj.user != request.user:
            return Response({"message": "권한이 없습니다."}, status=status.HTTP_403_FORBIDDEN)

        # 상태 확인
        if return_obj.status != "requested":
            return Response({"message": "신청 상태에서만 취소할 수 있습니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 삭제
        return_obj.delete()

        return Response({"message": "교환/환불 신청이 취소되었습니다."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """
        승인 (판매자만)

        POST /api/returns/{id}/approve/
        """
        return_obj = self.get_object()

        # 권한 확인 (향후 판매자 권한 체크 추가)
        # if not request.user.is_seller:
        #     return Response({"message": "판매자만 승인할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data, context={"return_obj": return_obj})
        serializer.is_valid(raise_exception=True)
        return_obj = serializer.save()

        return Response(
            {"message": "승인되었습니다.", "return": ReturnDetailSerializer(return_obj).data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        """
        거부 (판매자만)

        POST /api/returns/{id}/reject/
        Body: {"rejected_reason": "거부 사유"}
        """
        return_obj = self.get_object()

        # 권한 확인 (향후 판매자 권한 체크 추가)
        # if not request.user.is_seller:
        #     return Response({"message": "판매자만 거부할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data, context={"return_obj": return_obj})
        serializer.is_valid(raise_exception=True)
        return_obj = serializer.save()

        return Response(
            {"message": "거부되었습니다.", "return": ReturnDetailSerializer(return_obj).data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="confirm-receive")
    def confirm_receive(self, request, pk=None):
        """
        반품 도착 확인 (판매자만)

        POST /api/returns/{id}/confirm-receive/
        """
        return_obj = self.get_object()

        # 권한 확인 (향후 판매자 권한 체크 추가)
        # if not request.user.is_seller:
        #     return Response({"message": "판매자만 수령 확인할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data={}, context={"return_obj": return_obj})
        serializer.is_valid(raise_exception=True)
        return_obj = serializer.save()

        return Response(
            {"message": "반품 도착이 확인되었습니다.", "return": ReturnDetailSerializer(return_obj).data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """
        완료 처리 (판매자만)

        POST /api/returns/{id}/complete/

        환불: 자동 환불 처리
        교환: Body에 교환 상품 송장번호 필요
        """
        return_obj = self.get_object()

        # 권한 확인 (향후 판매자 권한 체크 추가)
        # if not request.user.is_seller:
        #     return Response({"message": "판매자만 완료 처리할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data, context={"return_obj": return_obj})
        serializer.is_valid(raise_exception=True)

        try:
            return_obj = serializer.save()

            message = "환불이 완료되었습니다." if return_obj.type == "refund" else "교환 상품이 발송되었습니다."

            return Response(
                {"message": message, "return": ReturnDetailSerializer(return_obj).data},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response({"message": f"처리 중 오류가 발생했습니다: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
