# 판매자 권한 관련 커스텀 권한 클래스를 정의합니다.


from rest_framework import permissions


class IsSeller(permissions.BasePermission):
    """
    판매자 권한 체크

    - 인증된 사용자이면서 is_seller=True인 경우에만 허용
    - 상품 등록, 재고 부족 상품 조회 등에 사용

    사용 예시:
        permission_classes = [IsSeller]
    """

    message = "판매자만 접근 가능합니다."

    def has_permission(self, request, view):
        """
        요청 레벨 권한 체크

        Args:
            request: HTTP 요청 객체
            view: 뷰 객체

        Returns:
            bool: 권한 여부
        """
        # 인증된 사용자인지 확인
        if not request.user or not request.user.is_authenticated:
            return False

        # 판매자 여부 확인
        return request.user.is_seller


class IsSellerAndOwner(permissions.BasePermission):
    """
    판매자이면서 해당 객체(상품)의 소유자인지 체크

    - 상품 수정/삭제에 사용
    - 객체 레벨 권한 체크 (has_object_permission)

    사용 예시:
        permission_classes = [IsAuthenticated, IsSellerAndOwner]
    """

    message = "본인이 등록한 상품만 수정/삭제할 수 있습니다."

    def has_permission(self, request, view):
        """
        요청 레벨 권한 체크 - 판매자 여부만 확인

        Args:
            request: HTTP 요청 객체
            view: 뷰 객체

        Returns:
            bool: 권한 여부
        """
        # 읽기 요청(GET, HEAD, OPTIONS)은 허용
        if request.method in permissions.SAFE_METHODS:
            return True

        # 쓰기 요청은 판매자만
        return request.user and request.user.is_authenticated and request.user.is_seller

    def has_object_permission(self, request, view, obj):
        """
        객체 레벨 권한 체크 - 본인 상품인지 확인

        Args:
            request: HTTP 요청 객체
            view: 뷰 객체
            obj: 체크할 객체 (Product)

        Returns:
            bool: 권한 여부
        """
        # 읽기 요청은 허용
        if request.method in permissions.SAFE_METHODS:
            return True

        # 쓰기 요청은 본인 상품만 가능
        return obj.seller == request.user


class IsSellerAndProductOwner(permissions.BasePermission):
    """
    판매자이면서 특정 상품의 판매자인지 체크

    - 상품 문의 답변, 교환/환불 처리 등에 사용
    - 상품 객체를 직접 전달받아 체크

    사용 방법:
        뷰에서 직접 체크:
        if not IsSellerAndProductOwner().has_permission_for_product(request, product):
            raise PermissionDenied("권한이 없습니다.")
    """

    message = "해당 상품의 판매자만 접근 가능합니다."

    def has_permission(self, request, view):
        """
        요청 레벨 권한 체크 - 판매자 여부만 확인

        Args:
            request: HTTP 요청 객체
            view: 뷰 객체

        Returns:
            bool: 권한 여부
        """
        return request.user and request.user.is_authenticated and request.user.is_seller

    def has_permission_for_product(self, request, product):
        """
        특정 상품에 대한 권한 체크

        Args:
            request: HTTP 요청 객체
            product: Product 객체

        Returns:
            bool: 권한 여부
        """
        # 판매자이면서 해당 상품의 판매자인지 확인
        return request.user and request.user.is_authenticated and request.user.is_seller and product.seller == request.user


class IsSellerOrReadOnly(permissions.BasePermission):
    """
    판매자는 모든 작업 가능, 일반 사용자는 읽기만 가능

    - 상품 목록/상세 조회는 누구나 가능
    - 상품 생성/수정/삭제는 판매자만 가능

    사용 예시:
        permission_classes = [IsSellerOrReadOnly]
    """

    message = "판매자만 상품을 등록/수정/삭제할 수 있습니다."

    def has_permission(self, request, view):
        """
        요청 레벨 권한 체크

        Args:
            request: HTTP 요청 객체
            view: 뷰 객체

        Returns:
            bool: 권한 여부
        """
        # 읽기 요청은 누구나 허용
        if request.method in permissions.SAFE_METHODS:
            return True

        # 쓰기 요청은 판매자만
        return request.user and request.user.is_authenticated and request.user.is_seller
