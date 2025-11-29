from __future__ import annotations

from typing import Any

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, serializers as drf_serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from ..models.product import Product
from ..models.product_qa import ProductAnswer, ProductQuestion
from ..serializers.product_qa_serializers import (
    ProductAnswerCreateSerializer,
    ProductAnswerSerializer,
    ProductAnswerUpdateSerializer,
    ProductQuestionCreateSerializer,
    ProductQuestionDetailSerializer,
    ProductQuestionListSerializer,
    ProductQuestionUpdateSerializer,
)


# ===== Swagger 문서화용 응답 Serializers =====


class QAErrorResponseSerializer(drf_serializers.Serializer):
    """문의 에러 응답"""
    error = drf_serializers.CharField()


class QAMessageResponseSerializer(drf_serializers.Serializer):
    """문의 메시지 응답"""
    message = drf_serializers.CharField()


class ProductQuestionPagination(PageNumberPagination):
    """상품 문의 페이지네이션"""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(
        summary="상품 문의 목록 조회",
        description="""
상품의 문의 목록을 조회합니다.

**비밀글 필터링:**
- 비밀글 아님: 모두 조회
- 비밀글: 작성자, 판매자, 관리자만 조회
        """,
        tags=["상품 문의"],
    ),
    retrieve=extend_schema(
        summary="문의 상세 조회",
        description="문의의 상세 정보와 답변을 조회합니다.",
        tags=["상품 문의"],
    ),
    create=extend_schema(
        summary="문의 작성",
        description="""
상품에 문의를 작성합니다.

**권한:** 인증 필요
        """,
        tags=["상품 문의"],
    ),
    update=extend_schema(
        summary="문의 수정",
        description="""
문의를 수정합니다.

**권한:** 작성자만
**제약:** 답변이 달린 문의는 수정 불가
        """,
        tags=["상품 문의"],
    ),
    partial_update=extend_schema(
        summary="문의 부분 수정",
        description="""
문의를 부분 수정합니다.

**권한:** 작성자만
**제약:** 답변이 달린 문의는 수정 불가
        """,
        tags=["상품 문의"],
    ),
    destroy=extend_schema(
        summary="문의 삭제",
        description="""
문의를 삭제합니다.

**권한:** 작성자 또는 관리자
**제약:** 답변이 달린 문의는 삭제 불가
        """,
        tags=["상품 문의"],
    ),
)
class ProductQuestionViewSet(viewsets.ModelViewSet):
    """상품 문의 ViewSet"""

    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = ProductQuestionPagination

    def get_queryset(self) -> Any:
        """
        상품별 문의 목록 조회

        비밀글 필터링:
        - 비밀글이 아닌 것: 모두 조회
        - 비밀글: 작성자, 판매자, 관리자만 조회
        """
        product_id = self.kwargs.get("product_pk")

        # 기본 쿼리셋 with N+1 쿼리 최적화
        queryset = (
            ProductQuestion.objects.filter(product_id=product_id)
            .select_related("user", "product", "product__seller")
            .prefetch_related(
                Prefetch(
                    "answer",
                    queryset=ProductAnswer.objects.select_related("seller")
                )
            )
            .order_by("-created_at")
        )

        user = self.request.user

        # 로그인하지 않은 경우: 비밀글 제외
        if not user.is_authenticated:
            return queryset.filter(is_secret=False)

        # 관리자는 모든 문의 조회 가능
        if user.is_staff:
            return queryset

        # 일반 사용자: 비밀글 아닌 것 OR 내가 작성한 것 OR 내가 판매자인 것
        return queryset.filter(Q(is_secret=False) | Q(user=user) | Q(product__seller=user))

    def get_serializer_class(self) -> type[BaseSerializer]:
        """액션에 따라 적절한 Serializer 반환"""
        if self.action == "list":
            return ProductQuestionListSerializer
        elif self.action == "retrieve":
            return ProductQuestionDetailSerializer
        elif self.action == "create":
            return ProductQuestionCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return ProductQuestionUpdateSerializer
        return ProductQuestionDetailSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """문의 작성"""
        if not request.user.is_authenticated:
            return Response({"error": "로그인이 필요합니다."}, status=status.HTTP_401_UNAUTHORIZED)

        product_id = self.kwargs.get("product_pk")
        product = get_object_or_404(Product, pk=product_id)

        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            serializer.save(user=request.user, product=product)

            detail_serializer = ProductQuestionDetailSerializer(serializer.instance, context={"request": request})

            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """문의 상세 조회"""
        question = self.get_object()

        if not question.can_view(request.user):
            raise PermissionDenied("이 문의를 볼 권한이 없습니다.")

        serializer = self.get_serializer(question)
        return Response(serializer.data)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """문의 수정 (작성자만)"""
        question = self.get_object()

        if question.user != request.user:
            raise PermissionDenied("수정 권한이 없습니다.")

        if question.is_answered:
            return Response(
                {"error": "답변이 달린 문의는 수정할 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """문의 삭제 (작성자만)"""
        question = self.get_object()

        if question.user != request.user and not request.user.is_staff:
            raise PermissionDenied("삭제 권한이 없습니다.")

        if question.is_answered:
            return Response(
                {"error": "답변이 달린 문의는 삭제할 수 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        request=ProductAnswerCreateSerializer,
        responses={
            201: ProductAnswerSerializer,
            400: QAErrorResponseSerializer,
        },
        summary="답변 작성",
        description="""
문의에 답변을 작성합니다.

**권한:** 판매자만 (본인 상품의 문의에만)
**제약:** 이미 답변이 있는 문의는 답변 불가
        """,
        tags=["상품 문의"],
    )
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def answer(self, request: Request, pk: int | None = None, product_pk: int | None = None) -> Response:
        question = self.get_object()

        # 해당 상품의 판매자인지 확인
        if question.product.seller != request.user:
            return Response({"error": "본인 상품의 문의에만 답변할 수 있습니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 이미 답변이 있는지 확인
        if hasattr(question, "answer"):
            return Response(
                {"error": "이미 답변이 등록되어 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProductAnswerCreateSerializer(data=request.data, context={"request": request, "question": question})

        if serializer.is_valid():
            answer = serializer.save()

            # 답변 정보 반환
            answer_serializer = ProductAnswerSerializer(answer)
            return Response(answer_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=ProductAnswerUpdateSerializer,
        responses={
            200: ProductAnswerSerializer,
            400: QAErrorResponseSerializer,
            404: QAErrorResponseSerializer,
        },
        summary="답변 수정",
        description="""
답변을 수정합니다.

**권한:** 판매자 또는 관리자
        """,
        tags=["상품 문의"],
    )
    @action(detail=True, methods=["patch"], permission_classes=[permissions.IsAuthenticated])
    def update_answer(self, request: Request, pk: int | None = None, product_pk: int | None = None) -> Response:
        question = self.get_object()

        # 답변 존재 확인
        if not hasattr(question, "answer"):
            return Response({"error": "답변이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        answer = question.answer

        # 판매자 또는 관리자만
        if answer.seller != request.user and not request.user.is_staff:
            raise PermissionDenied("수정 권한이 없습니다.")

        serializer = ProductAnswerUpdateSerializer(answer, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={
            204: QAMessageResponseSerializer,
            404: QAErrorResponseSerializer,
        },
        summary="답변 삭제",
        description="""
답변을 삭제합니다. 삭제 후 문의의 답변 완료 상태가 해제됩니다.

**권한:** 판매자 또는 관리자
        """,
        tags=["상품 문의"],
    )
    @action(
        detail=True,
        methods=["delete"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def delete_answer(self, request: Request, pk: int | None = None, product_pk: int | None = None) -> Response:
        question = self.get_object()

        # 답변 존재 확인
        if not hasattr(question, "answer"):
            return Response({"error": "답변이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        answer = question.answer

        # 판매자 또는 관리자만
        if answer.seller != request.user and not request.user.is_staff:
            raise PermissionDenied("삭제 권한이 없습니다.")

        # 답변 삭제
        answer.delete()

        # 문의의 답변 완료 상태 해제
        question.is_answered = False
        question.save(update_fields=["is_answered"])

        return Response({"message": "답변이 삭제되었습니다."}, status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary="내가 작성한 문의 목록",
        description="현재 사용자가 작성한 문의 목록을 조회합니다.",
        tags=["상품 문의"],
    ),
    retrieve=extend_schema(
        summary="내 문의 상세 조회",
        description="내가 작성한 문의의 상세 정보를 조회합니다.",
        tags=["상품 문의"],
    ),
)
class MyQuestionViewSet(viewsets.ReadOnlyModelViewSet):
    """내가 작성한 문의 ViewSet"""

    serializer_class = ProductQuestionDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ProductQuestionPagination

    def get_queryset(self) -> Any:
        """현재 사용자가 작성한 문의만 조회 with N+1 쿼리 최적화"""
        return (
            ProductQuestion.objects.filter(user=self.request.user)
            .select_related("product", "product__seller", "user")
            .prefetch_related(
                Prefetch(
                    "answer",
                    queryset=ProductAnswer.objects.select_related("seller")
                )
            )
            .order_by("-created_at")
        )
