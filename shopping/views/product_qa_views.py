from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from ..models.product import Product
from ..models.product_qa import ProductQuestion
from ..serializers.product_qa_serializers import (
    ProductAnswerCreateSerializer,
    ProductAnswerSerializer,
    ProductAnswerUpdateSerializer,
    ProductQuestionCreateSerializer,
    ProductQuestionDetailSerializer,
    ProductQuestionListSerializer,
    ProductQuestionUpdateSerializer,
)


class ProductQuestionPagination(PageNumberPagination):
    """상품 문의 페이지네이션"""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class ProductQuestionViewSet(viewsets.ModelViewSet):
    """
    상품 문의 ViewSet

    상품 문의 CRUD 및 답변 관리 기능을 제공합니다.
    """

    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = ProductQuestionPagination

    def get_queryset(self):
        """
        상품별 문의 목록 조회

        비밀글 필터링:
        - 비밀글이 아닌 것: 모두 조회
        - 비밀글: 작성자, 판매자, 관리자만 조회
        """
        product_id = self.kwargs.get("product_pk")

        # 기본 쿼리셋
        queryset = (
            ProductQuestion.objects.filter(product_id=product_id)
            .select_related("user", "product", "product__seller")
            .prefetch_related("answer")
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

    def get_serializer_class(self):
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

    def create(self, request, *args, **kwargs):
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

    def retrieve(self, request, *args, **kwargs):
        """문의 상세 조회"""
        question = self.get_object()

        if not question.can_view(request.user):
            raise PermissionDenied("이 문의를 볼 권한이 없습니다.")

        serializer = self.get_serializer(question)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
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

    def destroy(self, request, *args, **kwargs):
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

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def answer(self, request, pk=None, product_pk=None):
        """
        답변 작성
        POST /api/products/{product_id}/questions/{id}/answer/

        요청 본문:
        {
            "content": "내일 출발 예정입니다!"
        }
        """
        question = self.get_object()

        # 판매자 권한 확인
        if not request.user.is_seller:
            return Response({"error": "판매자만 답변을 작성할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        # 해당 상품의 판매자인지 확인
        if question.product.seller != request.user:
            return Response({"error": "본인 상품의 문의에만 답변할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

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

    @action(detail=True, methods=["patch"], permission_classes=[permissions.IsAuthenticated])
    def update_answer(self, request, pk=None, product_pk=None):
        """
        답변 수정
        PATCH /api/products/{product_id}/questions/{id}/update_answer/

        요청 본문:
        {
            "content": "수정된 답변 내용"
        }
        """
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

    @action(
        detail=True,
        methods=["delete"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def delete_answer(self, request, pk=None, product_pk=None):
        """
        답변 삭제
        DELETE /api/products/{product_id}/questions/{id}/delete_answer/
        """
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


class MyQuestionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    내가 작성한 문의 ViewSet

    엔드포인트:
    - GET /api/my/questions/     - 내가 작성한 문의 목록
    - GET /api/my/questions/{id}/ - 문의 상세
    """

    serializer_class = ProductQuestionDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ProductQuestionPagination

    def get_queryset(self):
        """현재 사용자가 작성한 문의만 조회"""
        return (
            ProductQuestion.objects.filter(user=self.request.user)
            .select_related("product", "product__seller", "user")
            .prefetch_related("answer")
            .order_by("-created_at")
        )
