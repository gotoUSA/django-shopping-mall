from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone

from shopping.models.user import User
from shopping.serializers.user_serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    PasswordChangeSerializer,
    TokenResponseSerializer,
)

from shopping.views.email_verification_views import SendVerificationEmailView
from shopping.models.email_verification import EmailVerificationToken, EmailLog
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


class RegisterView(APIView):
    """
    회원가입 API
    - POST: 새 사용자 생성 및 JWT 토큰 발급
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            # 사용자 생성
            user = serializer.save()

            # JWT 토큰 생성
            refresh = RefreshToken.for_user(user)

            # 이메일 인증 토큰 생성 및 발송
            try:
                # 토큰 생성
                token = EmailVerificationToken.objects.create(user=user)

                # 이메일 로그 생성
                email_log = EmailLog.objects.create(
                    user=user,
                    email_type="verification",
                    recipient_email=user.email,
                    subject="[쇼핑몰] 이메일 인증을 완료해주세요",
                    token=token,
                    status="pending",
                )

                # 이메일 발송
                verification_url = (
                    f"{settings.FRONTEND_URL}/verify-email?token={token.token}"
                )

                html_message = render_to_string(
                    "email/verification.html",
                    {
                        "user": user,
                        "verification_url": verification_url,
                        "verfication_code": token.verification_code,
                    },
                )

                plain_message = f"""
안녕하세요, {user.first_name}님!

회원가입을 환영합니다!
이메일 인증을 완료하려면 아래 링크를 클릭하거나 인증 코드를 입력해주세요.

인증 링크: {verification_url}
인증 코드: {token.verification_code}

이 링크와 코드는 24시간 동안 유효합니다.
"""

                send_mail(
                    subject="[쇼핑몰] 이메일 인증을 완료해주세요",
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=True,  # 이메일 실패해도 회원가입은 성공
                )

            except Exception as e:
                # 이메일 발송 실패해도 회원가입은 성공
                pass

            # 응답 데이터 구성
            response_data = {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
                "message": "회원가입이 완료되었습니다.",
                "email_sent": True,
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    로그인 API
    - POST: 인증 후 JWT 토큰 발급
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            user = serializer.validated_data["user"]

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
    커스텀 토큰 갱신 API
    - POST: Refresh Token으로 새로운 Access Token 발급

    기본 TokenRefreshView를 상속받아 커스터마이징
    """

    def post(self, request, *args, **kwargs):
        """
        요청 형식:
        {
            "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
        }

        응답 형식:
        {
            "access": "새로운_access_token",
            "refresh": "새로운_refresh_token" (ROTATE_REFRESH_TOKENS=True인 경우)
        }
        """
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            # 토큰 에러 처리
            raise InvalidToken(e.args[0])

        # 성공 메시지 추가
        response_data = serializer.validated_data
        response_data["message"] = "토큰이 갱신되었습니다."

        return Response(response_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    로그아웃 API
    - POST: Refresh Token을 블랙리스트에 추가
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
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

            return Response(
                {"message": "로그아웃 되었습니다."}, status=status.HTTP_200_OK
            )

        except TokenError:
            return Response(
                {"error": "유효하지 않은 토큰입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            serializer.save()

            # 비밀번호 변경 후에도 로그인 유지
            update_session_auth_hash(request, request.user)

            return Response(
                {"message": "비밀번호가 변경되었습니다."}, status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_token(request):
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
def email_verification_request(request):
    """
    이메일 인증 요청 API (추후 구현)
    - POST: 인증 이메일 발송
    """
    # TODO: 이메일 발송 로직 구현
    return Response(
        {"message": "이메일 인증 기능은 준비중입니다."},
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def withdraw(request):
    """
    회원 탈퇴 API
    - POST: 비밀번호 확인 후 탈퇴 처리
    """
    password = request.data.get("password")

    if not password:
        return Response(
            {"error": "비밀번호를 입력해주세요."}, status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user

    # 비밀번호 확인
    if not user.check_password(password):
        return Response(
            {"error": "비밀번호가 올바르지 않습니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 탈퇴 처리 (실제로 삭제하지 않고 플래그만 변경)
    user.is_withdrawn = True
    user.withdrawn_at = timezone.now()
    user.is_active = False  # 비활성화
    user.save()

    return Response(
        {"message": "회원 탈퇴가 완료되었습니다."}, status=status.HTTP_200_OK
    )
