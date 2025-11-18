from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model

from rest_framework import serializers

from ..models.product_qa import ProductAnswer, ProductQuestion

User = get_user_model()


class ProductQuestionBaseSerializer(serializers.ModelSerializer):
    """
    문의 작성/수정용 Base Serializer

    공통 validation 로직을 제공합니다.
    """

    def validate_title(self, value: str) -> str:
        """제목 유효성 검증"""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("제목은 최소 2자 이상이어야 합니다.")
        return value.strip()

    def validate_content(self, value: str) -> str:
        """내용 유효성 검증"""
        if len(value.strip()) < 5:
            raise serializers.ValidationError("내용은 최소 5자 이상이어야 합니다.")
        return value.strip()

    class Meta:
        model = ProductQuestion
        abstract = True


class ProductAnswerSerializer(serializers.ModelSerializer):
    """문의 답변 Serializer"""

    seller_username = serializers.CharField(source="seller.username", read_only=True)

    class Meta:
        model = ProductAnswer
        fields = [
            "id",
            "content",
            "seller",
            "seller_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["seller", "created_at", "updated_at"]


class ProductQuestionListSerializer(serializers.ModelSerializer):
    """문의 목록 조회용 Serializer"""

    user_username = serializers.CharField(source="user.username", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    has_answer = serializers.BooleanField(source="is_answered", read_only=True)
    display_title = serializers.SerializerMethodField()
    display_content = serializers.SerializerMethodField()
    can_view = serializers.SerializerMethodField()

    class Meta:
        model = ProductQuestion
        fields = [
            "id",
            "product",
            "product_name",
            "user_username",
            "display_title",
            "display_content",
            "is_secret",
            "has_answer",
            "can_view",
            "created_at",
        ]

    def get_can_view(self, obj: ProductQuestion) -> bool:
        """현재 사용자가 볼 수 있는지"""
        request = self.context.get("request")
        if not request:
            return False
        return obj.can_view(request.user)

    def get_display_title(self, obj: ProductQuestion) -> str:
        """비밀글인 경우 제목 마스킹"""
        request = self.context.get("request")
        if not request:
            return "비밀글입니다"

        # ViewSet의 get_queryset()에서 이미 필터링했으므로
        # 여기서는 그냥 제목을 반환
        # 만약 비밀글이고 볼 수 없다면 애초에 queryset에 포함되지 않음
        return obj.title

    def get_display_content(self, obj: ProductQuestion) -> str:
        """비밀글인 경우 내용 마스킹"""
        request = self.context.get("request")
        if not request:
            return "비밀글입니다. 작성자와 판매자만 볼 수 있습니다."

        # ViewSet의 get_queryset()에서 이미 필터링했으므로
        # 여기서는 그냥 내용을 반환
        # 목록에서는 내용 미리보기만 (100자)
        if len(obj.content) > 100:
            return obj.content[:100] + "..."
        return obj.content


class ProductQuestionDetailSerializer(serializers.ModelSerializer):
    """문의 상세 조회용 Serializer"""

    user_username = serializers.CharField(source="user.username", read_only=True)

    product_name = serializers.CharField(source="product.name", read_only=True)

    answer = ProductAnswerSerializer(read_only=True)
    can_edit = serializers.SerializerMethodField()
    can_answer = serializers.SerializerMethodField()

    class Meta:
        model = ProductQuestion
        fields = [
            "id",
            "product",
            "product_name",
            "user",
            "user_username",
            "title",
            "content",
            "is_secret",
            "is_answered",
            "answer",
            "can_edit",
            "can_answer",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["user", "is_answered", "created_at", "updated_at"]

    def get_can_edit(self, obj: ProductQuestion) -> bool:
        """작성자만 수정 가능"""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.user == request.user

    def get_can_answer(self, obj: ProductQuestion) -> bool:
        """판매자만 답변 가능"""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.product.seller == request.user or request.user.is_staff


class ProductQuestionCreateSerializer(ProductQuestionBaseSerializer):
    """문의 작성용 Serializer"""

    class Meta:
        model = ProductQuestion
        fields = [
            # product는 view에서 자동으로 설정하므로 제외
            "title",
            "content",
            "is_secret",
        ]


class ProductQuestionUpdateSerializer(ProductQuestionBaseSerializer):
    """문의 수정용 Serializer"""

    class Meta:
        model = ProductQuestion
        fields = ["title", "content", "is_secret"]


class ProductAnswerCreateSerializer(serializers.ModelSerializer):
    """답변 작성용 Serializer"""

    class Meta:
        model = ProductAnswer
        fields = ["content"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """답변 작성 권한 확인"""
        request = self.context.get("request")
        question = self.context.get("question")

        if not question:
            raise serializers.ValidationError("문의를 찾을 수 없습니다.")

        if hasattr(question, "answer"):
            raise serializers.ValidationError("이미 답변이 등록되어 있습니다.")

        if question.product.seller != request.user and not request.user.is_staff:
            raise serializers.ValidationError("답변 권한이 없습니다.")

        return attrs

    def create(self, validated_data: dict[str, Any]) -> ProductAnswer:
        """답변 생성"""
        from shopping.services import ProductQAService

        question = self.context["question"]
        user = self.context["request"].user
        content = validated_data["content"]

        return ProductQAService.create_answer(
            question=question,
            seller=user,
            content=content
        )


class ProductAnswerUpdateSerializer(serializers.ModelSerializer):
    """답변 수정용 Serializer"""

    class Meta:
        model = ProductAnswer
        fields = ["content"]
