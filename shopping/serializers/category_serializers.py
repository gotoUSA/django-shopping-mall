from rest_framework import serializers
from django.db.models import Count, Q
from ..models.product import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    """
    카테고리 기본 serializer

    카테고리 정보와 함께 부모 카테고리 정보, 활성 상품 수를 제공합니다.
    """

    # 부모 카테고리 정보 (읽기 전용)
    parent_id = serializers.IntegerField(
        source="parent.id",
        read_only=True,
        allow_null=True,
        help_text="부모 카테고리 ID",
    )
    parent_name = serializers.CharField(
        source="parent.name",
        read_only=True,
        allow_null=True,
        help_text="부모 카테고리 ID",
    )

    # 해당 카테고리의 활성 상품 수
    product_count = serializers.SerializerMethodField(
        help_text="카테고리에 속한 활성 상품 수"
    )

    # 하위 카테고리 수
    children_count = serializers.SerializerMethodField(
        help_text="직계 하위 카테고리 수"
    )

    # 전체 경로 (예: "전자제품 > 컴퓨터 > 노트북")
    full_path = serializers.SerializerMethodField(
        help_text="최상위부터 현재까지의 전체 경로"
    )

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "parent",
            "parent_id",
            "parent_name",
            "is_active",
            "product_count",
            "children_count",
            "full_path",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def get_product_count(self, obj):
        """
        해당 카테고리의 활성 상품 수를 반환

        주의: ViewSet에서 annotate로 미리 계산하면 더 효율적입니다.
        """
        # annotate로 이미 계산된 경우
        if hasattr(obj, "product_count"):
            return obj.product_count

        # 그렇지 않은 경우 직접 계산
        return Product.objects.filter(category=obj, is_active=True).count()

    def get_children_count(self, obj):
        """직계 하위 카테고리 수 반환"""
        return obj.children.filter(is_active=True).count()

    def get_full_path(self, obj):
        """
        카테고리의 전체 경로를 반환
        예: "전자제품 > 컴퓨터 > 노트북"
        """
        path_parts = []
        current = obj

        # 부모를 따라 올라가며 경로 구성
        while current:
            path_parts.append(current.name)
            current = current.parent

        # 역순으로 정렬하여 최상위부터 표시
        path_parts.reverse()
        return " > ".join(path_parts)


class CategoryTreeSerializer(serializers.ModelSerializer):
    """
    카테고리 트리 구조 표현용 serializer

    계층적 구조로 카테고리를 표현할 때 사용합니다.
    """

    # 하위 카테고리들 (재귀적 구조)
    children = serializers.SerializerMethodField()

    # 상품 수
    product_count = serializers.IntegerField(read_only=True)

    # 해당 카테고리가 리프 노드인지 여부
    is_leaf = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "product_count",
            "is_leaf",
            "children",
        ]

    def get_children(self, obj):
        """
        하위 카테고리들을 재귀적으로 반환

        주의: 깊이가 깊을 경우 성능 문제가 발생할 수 있습니다.
        필요시 depth 제한을 추가하세요.
        """
        # 활성화된 하위 카테고리만 가져오기
        children = obj.children.filter(is_active=True)

        # 재귀적으로 serializer 호출
        return CategoryTreeSerializer(children, many=True, context=self.context).data

    def get_is_leaf(self, obj):
        """리프 노드(하위 카테고리가 없는 노드)인지 확인"""
        return not obj.children.filter(is_active=True).exists()


class CategoryCreateUpdateSerializer(serializers.ModelSerializer):
    """
    카테고리 생성/수정용 Serializer

    관리자가 카테고리를 추가하거나 수정할 때 사용합니다.
    """

    # 부모 카테고리는 활성화된 것만 선택 가능
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        help_text="부모 카테고리 ID (최상위 카테고리는 null)",
    )

    # slug는 선택적 (없으면 name으로 자동 생성)
    slug = serializers.SlugField(
        max_length=100,
        required=False,
        allow_blank=True,
        help_text="URL용 슬러그 (비워두면 이름으로 자동 생성)",
    )

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "parent",
            "description",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate_name(self, value):
        """
        부모 카테고리 검증
        - 자기 자신을 부모로 설정할 수 없음
        - 자신의 하위 카테고리를 부모로 설정할 수 없음 (순환 참조 방지)
        """
        if self.instance and value:
            # 자기 자신인지 확인
            if value.pk == self.instance.pk:
                raise serializers.ValidationError(
                    "자기 자신을 부모 카테고리로 설정할 수 없습니다."
                )

            # 자신의 하위 카테고리인지 확인
            # get_descendants 메서드가 있다고 가정 (django-mptt 사용 시)
            # 없다면 재귀적으로 확인하는 로직 필요
            current = value
            while current.parent:
                if current.parent.pk == self.instance.pk:
                    raise serializers.ValidationError(
                        "하위 카테고리를 부모로 설정할 수 없습니다."
                    )
                current = current.parent

        return value

    def validate(self, attrs):
        """전체 유효성 검증"""
        # 비활성화할 때 하위 카테고리나 상품이 있는지 확인
        if self.instance and not attrs.get("is_active", True):
            # 활성화된 하위 카테고리가 있는지 확인
            if self.instance.children.filter(is_active=True).exists():
                raise serializers.ValidationError(
                    {
                        "is_active": "활성화된 하위 카테고리가 있는 경우 비활성화할 수 없습니다."
                    }
                )

            # 활성화된 상품이 있는지 확인
            if self.instance.products.filter(is_active=True).exists():
                raise serializers.ValidationError(
                    {"is_active": "활성화된 상품이 있는 경우 비활성화할 수 없습니다."}
                )

        return attrs


class SimpleCategorySerializer(serializers.ModelSerializer):
    """
    간단한 카테고리 정보만 제공하는 Serializer

    다른 모델에서 카테고리를 참조할 때 사용합니다.
    예: ProductSerializer에서 카테고리 정보 표시
    """

    class Meta:
        model = Category
        fields = ["id", "name", "slug"]
        read_only_fields = fields
