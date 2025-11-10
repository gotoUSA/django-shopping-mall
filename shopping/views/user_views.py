from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from shopping.serializers.user_serializers import PasswordChangeSerializer, UserSerializer


class ProfileView(APIView):
    """
    사용자 프로필 API
    - GET: 현재 로그인한 사용자 정보 조회
    - PUT/PATCH: 사용자 정보 수정
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """프로필 조회"""
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        """프로필 전체 수정"""
        serializer = UserSerializer(request.user, data=request.data, partial=False)

        if serializer.is_valid():
            serializer.save()
            return Response(
                {"user": serializer.data, "message": "프로필이 수정되었습니다."},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        """프로필 부분 수정"""
        serializer = UserSerializer(request.user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(
                {"user": serializer.data, "message": "프로필이 수정되었습니다."},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordChangeView(APIView):
    """
    비밀번호 변경 API
    - POST: 현재 비밀번호 확인 후 새 비밀번호로 변경
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            serializer.save()

            # 비밀번호 변경 후에도 로그인 유지
            update_session_auth_hash(request, request.user)

            return Response({"message": "비밀번호가 변경되었습니다."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def withdraw(request):
    """
    회원 탈퇴 API
    - POST: 비밀번호 확인 후 탈퇴 처리

    처리 내용:
    1. 비밀번호 확인
    2. 사용자 상태 변경 (is_withdrawn, is_active)
    3. 모든 JWT 토큰 무효화 (보안 강화)
    4. 포인트 및 주문 내역은 보존
    """
    password = request.data.get("password")

    # 비밀번호 누락 확인
    if not password:
        return Response({"error": "비밀번호를 입력해주세요."}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user

    # 비밀번호 확인
    if not user.check_password(password):
        return Response(
            {"error": "비밀번호가 올바르지 않습니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # 트랜잭션으로 원자성 보장
        with transaction.atomic():
            # 1. 사용자 탈퇴 처리
            user.is_withdrawn = True
            user.withdrawn_at = timezone.now()
            user.is_active = False
            user.save()

            # 2. 모든 JWT 토큰 무효화
            # OutstandingToken에서 해당 사용자의 모든 토큰을 찾아 블랙리스트에 추가
            outstanding_tokens = OutstandingToken.objects.filter(user=user)

            for outstanding_token in outstanding_tokens:
                # 이미 블랙리스트에 없는 토큰만 추가
                BlacklistedToken.objects.get_or_create(token=outstanding_token)

        return Response({"message": "회원 탈퇴가 완료되었습니다."}, status=status.HTTP_200_OK)

    except Exception as e:
        # 예외 발생 시 자동 롤백 (transaction.atomic이 처리)
        return Response(
            {"error": f"탈퇴 처리 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
