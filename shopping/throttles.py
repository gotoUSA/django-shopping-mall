"""
API 엔드포인트 Rate Limiting (속도 제한) 클래스

이 모듈은 다양한 throttle 클래스를 구현하여 API 남용을 방지합니다:
- 인증 엔드포인트 (로그인, 회원가입): 엄격한 제한으로 brute force 공격 방지
- 결제 엔드포인트: 적절한 제한으로 남용 방지하면서 정상적인 사용 허용
- 주문 엔드포인트: 적절한 제한으로 스팸 방지
- 이메일 인증: 엄격한 제한으로 스팸 방지
- 전역 제한: 모든 API 요청에 대한 기본 제한

모든 throttle 클래스는 최적의 성능과 분산 rate limiting 지원을 위해
Redis 캐시 백엔드를 사용합니다.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


# ============================================================
# 인증 관련 Throttles (높은 보안)
# ============================================================


class LoginRateThrottle(AnonRateThrottle):
    """
    로그인 엔드포인트 속도 제한

    Brute force 공격을 방지합니다.
    제한: IP 주소당 15분에 5회

    적용 대상: LoginView
    """
    scope = "login"


class RegisterRateThrottle(AnonRateThrottle):
    """
    회원가입 엔드포인트 속도 제한

    스팸 계정 생성을 방지합니다.
    제한: IP 주소당 1시간에 3회

    적용 대상: RegisterView
    """
    scope = "register"


class TokenRefreshRateThrottle(UserRateThrottle):
    """
    토큰 갱신 엔드포인트 속도 제한

    과도한 토큰 갱신 요청을 방지합니다.
    제한: 사용자당 1분에 10회

    적용 대상: CustomTokenRefreshView
    """
    scope = "token_refresh"


class PasswordResetRateThrottle(AnonRateThrottle):
    """
    비밀번호 재설정 엔드포인트 속도 제한

    비밀번호 재설정 스팸을 방지합니다.
    제한: IP 주소당 1시간에 3회

    적용 대상: PasswordResetRequestView
    """
    scope = "password_reset"


# ============================================================
# 이메일 인증 관련 Throttles (높은 보안)
# ============================================================


class EmailVerificationRateThrottle(UserRateThrottle):
    """
    이메일 인증 발송 엔드포인트 속도 제한

    이메일 스팸과 남용을 방지합니다.
    제한: 사용자당 1분에 1회

    적용 대상: SendVerificationEmailView
    """
    scope = "email_verification"


class EmailVerificationResendRateThrottle(UserRateThrottle):
    """
    이메일 인증 재발송 엔드포인트 속도 제한

    과도한 재발송 요청을 방지합니다.
    제한: 사용자당 1시간에 3회

    적용 대상: ResendVerificationEmailView
    """
    scope = "email_verification_resend"


# ============================================================
# 결제 관련 Throttles (중간 보안)
# ============================================================


class PaymentRequestRateThrottle(UserRateThrottle):
    """
    결제 요청 엔드포인트 속도 제한

    결제 스팸을 방지하면서 정상적인 구매는 허용합니다.
    제한: 사용자당 1분에 10회

    적용 대상: PaymentRequestView
    """
    scope = "payment_request"


class PaymentConfirmRateThrottle(UserRateThrottle):
    """
    결제 승인 엔드포인트 속도 제한

    중복 결제 승인을 방지합니다.
    제한: 사용자당 1분에 5회

    적용 대상: PaymentConfirmView
    """
    scope = "payment_confirm"


class PaymentCancelRateThrottle(UserRateThrottle):
    """
    결제 취소 엔드포인트 속도 제한

    과도한 취소 요청을 방지합니다.
    제한: 사용자당 1분에 5회

    적용 대상: PaymentCancelView
    """
    scope = "payment_cancel"


# ============================================================
# 주문 관련 Throttles (중간 보안)
# ============================================================


class OrderCreateRateThrottle(UserRateThrottle):
    """
    주문 생성 엔드포인트 속도 제한

    주문 스팸을 방지하면서 정상적인 구매는 허용합니다.
    제한: 사용자당 1분에 10회

    적용 대상: OrderViewSet.create
    """
    scope = "order_create"


class OrderCancelRateThrottle(UserRateThrottle):
    """
    주문 취소 엔드포인트 속도 제한

    과도한 취소 요청을 방지합니다.
    제한: 사용자당 1분에 5회

    적용 대상: OrderViewSet.cancel
    """
    scope = "order_cancel"


# ============================================================
# 전역 Throttles (기본 보안)
# ============================================================


class GlobalAnonRateThrottle(AnonRateThrottle):
    """
    비인증 사용자 전역 속도 제한

    모든 비인증 API 요청에 대한 기본 제한입니다.
    제한: IP 주소당 1시간에 100회

    적용 대상: 모든 API 엔드포인트 (기본값)
    """
    scope = "anon_global"


class GlobalUserRateThrottle(UserRateThrottle):
    """
    인증 사용자 전역 속도 제한

    모든 인증된 API 요청에 대한 기본 제한입니다.
    제한: 사용자당 1시간에 1000회

    적용 대상: 모든 API 엔드포인트 (기본값)
    """
    scope = "user_global"


# ============================================================
# 특수 케이스 Throttles
# ============================================================


class WebhookRateThrottle(AnonRateThrottle):
    """
    웹훅 엔드포인트 속도 제한

    외부 서비스로부터의 웹훅 스팸을 방지합니다.
    제한: IP 주소당 1분에 100회

    참고: 웹훅은 신뢰할 수 있는 소스에서 오고 시그니처로 검증되므로
    관대한 제한을 설정했습니다. 예상되는 웹훅 볼륨에 따라 조정하세요.

    적용 대상: 웹훅 뷰 (예: TossPayments 웹훅)
    """
    scope = "webhook"
