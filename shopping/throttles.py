"""
Rate limiting (throttling) classes for API endpoints.

This module implements various throttle classes to protect against abuse:
- Authentication endpoints (login, register): Strict limits to prevent brute force
- Payment endpoints: Moderate limits to prevent abuse while allowing legitimate use
- Order endpoints: Moderate limits to prevent spam
- Email verification: Strict limits to prevent spam
- Global limits: Default limits for all API requests

All throttle classes use Redis cache backend for optimal performance and
distributed rate limiting support.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


# ============================================================
# Authentication Throttles (High Security)
# ============================================================


class LoginRateThrottle(AnonRateThrottle):
    """
    Login endpoint rate limiting.

    Prevents brute force attacks on login endpoint.
    Limit: 5 requests per 15 minutes per IP address.

    Applied to: LoginView
    """
    scope = "login"


class RegisterRateThrottle(AnonRateThrottle):
    """
    Registration endpoint rate limiting.

    Prevents spam account creation.
    Limit: 3 requests per hour per IP address.

    Applied to: RegisterView
    """
    scope = "register"


class TokenRefreshRateThrottle(UserRateThrottle):
    """
    Token refresh endpoint rate limiting.

    Prevents excessive token refresh requests.
    Limit: 10 requests per minute per user.

    Applied to: CustomTokenRefreshView
    """
    scope = "token_refresh"


class PasswordResetRateThrottle(AnonRateThrottle):
    """
    Password reset endpoint rate limiting.

    Prevents password reset spam.
    Limit: 3 requests per hour per IP address.

    Applied to: Password reset views
    """
    scope = "password_reset"


# ============================================================
# Email Verification Throttles (High Security)
# ============================================================


class EmailVerificationRateThrottle(UserRateThrottle):
    """
    Email verification send endpoint rate limiting.

    Prevents email spam and abuse.
    Limit: 1 request per minute per user.

    Applied to: Email verification send view
    """
    scope = "email_verification"


class EmailVerificationResendRateThrottle(UserRateThrottle):
    """
    Email verification resend endpoint rate limiting.

    Prevents excessive resend requests.
    Limit: 3 requests per hour per user.

    Applied to: Email verification resend view
    """
    scope = "email_verification_resend"


# ============================================================
# Payment Throttles (Medium Security)
# ============================================================


class PaymentRequestRateThrottle(UserRateThrottle):
    """
    Payment request endpoint rate limiting.

    Prevents payment spam while allowing legitimate purchases.
    Limit: 10 requests per minute per user.

    Applied to: PaymentRequestView
    """
    scope = "payment_request"


class PaymentConfirmRateThrottle(UserRateThrottle):
    """
    Payment confirmation endpoint rate limiting.

    Prevents duplicate payment confirmations.
    Limit: 5 requests per minute per user.

    Applied to: PaymentConfirmView
    """
    scope = "payment_confirm"


class PaymentCancelRateThrottle(UserRateThrottle):
    """
    Payment cancellation endpoint rate limiting.

    Prevents excessive cancellation requests.
    Limit: 5 requests per minute per user.

    Applied to: PaymentCancelView
    """
    scope = "payment_cancel"


# ============================================================
# Order Throttles (Medium Security)
# ============================================================


class OrderCreateRateThrottle(UserRateThrottle):
    """
    Order creation endpoint rate limiting.

    Prevents order spam while allowing legitimate purchases.
    Limit: 10 requests per minute per user.

    Applied to: OrderViewSet.create
    """
    scope = "order_create"


class OrderCancelRateThrottle(UserRateThrottle):
    """
    Order cancellation endpoint rate limiting.

    Prevents excessive cancellation requests.
    Limit: 5 requests per minute per user.

    Applied to: OrderViewSet.cancel
    """
    scope = "order_cancel"


# ============================================================
# Global Throttles (Default Security)
# ============================================================


class GlobalAnonRateThrottle(AnonRateThrottle):
    """
    Global rate limit for anonymous users.

    Default limit for all unauthenticated API requests.
    Limit: 100 requests per hour per IP address.

    Applied to: All API endpoints (default)
    """
    scope = "anon_global"


class GlobalUserRateThrottle(UserRateThrottle):
    """
    Global rate limit for authenticated users.

    Default limit for all authenticated API requests.
    Limit: 1000 requests per hour per user.

    Applied to: All API endpoints (default)
    """
    scope = "user_global"


# ============================================================
# Special Case Throttles
# ============================================================


class WebhookRateThrottle(AnonRateThrottle):
    """
    Webhook endpoint rate limiting.

    Prevents webhook spam from external services.
    Limit: 100 requests per minute per IP address.

    Note: This is a generous limit as webhooks are from trusted sources
    and verified by signature. Adjust based on expected webhook volume.

    Applied to: Webhook views (e.g., TossPayments webhook)
    """
    scope = "webhook"
