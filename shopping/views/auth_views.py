from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from shopping.models.user import User
from shopping.serializers.user_serializers import LoginSerializer, PasswordChangeSerializer, RegisterSerializer, UserSerializer
from shopping.services.user_service import UserService
from shopping.throttles import LoginRateThrottle, RegisterRateThrottle, TokenRefreshRateThrottle


# 회원가입 응답용 Serializer (Swagger 문서화용)
class RegisterResponseSerializer(drf_serializers.Serializer):
    """회원가입 성공 응답 스키마"""
    message = drf_serializers.CharField()
    user = UserSerializer()
    tokens = inline_serializer(
        name="TokensSerializer",
        fields={
            "access": drf_serializers.CharField(),
            "refresh": drf_serializers.CharField(),
        },
    )
    verification_code = drf_serializers.CharField(required=False, help_text="DEBUG 모드에서만 포함")


class RegisterView(CreateAPIView):
    """
    회원가입 API (비동기 이메일 발송)
    - POST: 새 사용자 생성 및 JWT 토큰 발급
    """

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]

    @extend_schema(
        request=RegisterSerializer,
        responses={201: RegisterResponseSerializer},
        summary="회원가입",
        description="새 사용자를 생성하고 JWT 토큰을 발급합니다.",
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer: RegisterSerializer) -> None:
        """
        사용자 생성 후 후처리 (토큰 생성 + 이메일 발송)

        트랜잭션을 사용하여 동시 가입 시도 시 race condition 방지:
        - 여러 요청이 동시에 validation을 통과할 수 있음
        - atomic 트랜잭션 내에서 DB constraint가 최종 방어선
        - IntegrityError 발생 시 ValidationError로 변환하여 400 반환
        """
        with transaction.atomic():
            user = serializer.save()
            # UserService로 회원가입 후처리 (토큰 생성 + 이메일 발송)
            result = UserService.register_user(user)
            # create() 메서드에서 접근할 수 있도록 인스턴스에 저장
            self._user = user
            self._result = result

    def create(self, request: Request, *args, **kwargs) -> Response:
        """회원가입 응답 커스터마이징"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        response_data = {
            "message": "회원가입이 완료되었습니다. 인증 이메일을 확인해주세요.",
            "user": UserSerializer(self._user).data,
            "tokens": self._result["tokens"],
        }

        # DEBUG 모드에서만 verification_code 포함
        if "verification_code" in self._result["verification_result"]:
            response_data["verification_code"] = self._result["verification_result"]["verification_code"]

        return Response(response_data, status=status.HTTP_201_CREATED)



class LoginView(APIView):
    """
    로그인 API
    - POST: 인증 후 JWT 토큰 발급
    - 로그인 시 비회원 장바구니가 있으면 회원 장바구니로 병합
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            user = serializer.validated_data["user"]

            # 비회원 장바구니 병합 (로그인 전 세션에 장바구니가 있었다면)
            session_key = request.session.session_key
            if session_key:
                try:
                    from shopping.models.cart import Cart

                    Cart.merge_anonymous_cart(user, session_key)
                except Exception:
                    # 병합 실패해도 로그인은 진행 (에러 무시)
                    pass

            # 마지막 로그인 시간 및 IP 업데이트
            user.last_login = timezone.now()

            # IP 주소 가져오기
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip = x_forwarded_for.split(",")[0]
            else:
                ip = request.META.get("REMOTE_ADDR")
            user.last_login_ip = ip

            user.save(update_fields=["last_login", "last_login_ip"])

            # JWT 토큰 생성
            refresh = RefreshToken.for_user(user)

            # 응답 데이터 구성
            response_data = {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
                "message": "로그인 되었습니다.",
            }

            return Response(response_data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomTokenRefreshView(TokenRefreshView):
    """
    Refresh Token으로 새로운 Access Token 발급 (Redis Lock 적용)

    요청 형식:
    {
        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }

    응답 형식:
    {
        "access": "새로운_access_token",
        "refresh": "새로운_refresh_token",  # ROTATE_REFRESH_TOKENS=True인 경우
        "message": "토큰이 갱신되었습니다."
    }

    에러 응답 (동시 갱신 시도):
    {
        "error": "토큰이 현재 갱신 중입니다."
    }
    HTTP 429 TOO_MANY_REQUESTS
    """

    throttle_classes = [TokenRefreshRateThrottle]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from django.core.cache import cache

        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "refresh token이 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        lock_key = f"refresh_lock:{refresh_token[:20]}"

        if not cache.add(lock_key, "locked", timeout=5):
            return Response(
                {"error": "토큰이 현재 갱신 중입니다."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        try:
            serializer = self.get_serializer(data=request.data)
            try:
                serializer.is_valid(raise_exception=True)
            except TokenError as e:
                raise InvalidToken(e.args[0])

            response_data = serializer.validated_data
            response_data["message"] = "토큰이 갱신되었습니다."
            return Response(response_data, status=status.HTTP_200_OK)
        finally:
            cache.delete(lock_key)

class LogoutView(APIView):
    """
    로그아웃 API
    - POST: Refresh Token을 블랙리스트에 추가
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        try:
            # 요청에서 refresh token 가져오기
            refresh_token = request.data.get("refresh")

            if not refresh_token:
                return Response(
                    {"error": "Refresh token이 필요합니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 토큰 블랙리스트에 추가
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({"message": "로그아웃 되었습니다."}, status=status.HTTP_200_OK)

        except TokenError:
            return Response(
                {"error": "유효하지 않은 토큰입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_token(request: Request) -> Response:
    """
    토큰 유효성 확인 API
    - GET: 현재 Access Token이 유효한지 확인
    """
    return Response(
        {
            "valid": True,
            "user": UserSerializer(request.user).data,
            "message": "유효한 토큰입니다.",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def email_verification_request(request: Request) -> Response:
    """
    이메일 인증 요청 API (추후 구현)
    - POST: 인증 이메일 발송
    """
    # TODO: 이메일 발송 로직 구현
    return Response(
        {"message": "이메일 인증 기능은 준비중입니다."},
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )
