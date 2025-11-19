from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from shopping.serializers.user_serializers import PasswordChangeSerializer, UserSerializer

logger = logging.getLogger(__name__)


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    사용자 프로필 API (Generic View 사용)
    - GET: 현재 로그인한 사용자 정보 조회
    - PUT/PATCH: 사용자 정보 수정
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        """현재 로그인한 사용자 반환"""
        return self.request.user


class PasswordChangeView(APIView):
    """
    비밀번호 변경 API
    - POST: 현재 비밀번호 확인 후 새 비밀번호로 변경
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            serializer.save()
            logger.info(f"비밀번호 변경 완료: user_id={request.user.id}")
            return Response({"message": "비밀번호가 변경되었습니다."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



@api_view(["POST"])
@permission_classes([IsAuthenticated])
def withdraw(request: Request) -> Response:
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
        logger.warning(f"회원 탈퇴 실패 - 비밀번호 불일치: user_id={user.id}")
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
            logger.info(f"사용자 탈퇴 처리: user_id={user.id}, username={user.username}")

            # 2. 모든 JWT 토큰 무효화
            outstanding_tokens = OutstandingToken.objects.filter(user=user)

            for outstanding_token in outstanding_tokens:
                # 이미 블랙리스트에 없는 토큰만 추가
                BlacklistedToken.objects.get_or_create(token=outstanding_token)

            logger.info(f"JWT 토큰 무효화 완료: user_id={user.id}, token_count={outstanding_tokens.count()}")

        return Response({"message": "회원 탈퇴가 완료되었습니다."}, status=status.HTTP_200_OK)

    except OutstandingToken.DoesNotExist:
        # 토큰이 없는 경우 (정상 케이스일 수 있음)
        logger.warning(f"탈퇴 처리 - 토큰 없음: user_id={user.id}")
        return Response({"message": "회원 탈퇴가 완료되었습니다."}, status=status.HTTP_200_OK)

    except Exception as e:
        # 예상치 못한 에러
        logger.error(f"탈퇴 처리 중 오류 발생: user_id={user.id}, error={str(e)}", exc_info=True)
        return Response(
            {"error": "탈퇴 처리 중 오류가 발생했습니다. 고객센터에 문의해주세요."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

