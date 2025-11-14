"""
소셜 로그인 커스텀 어댑터

django-allauth의 기본 동작을 오버라이드하여
API 방식 소셜 로그인에 최적화

목적:
- 웹 기반 signup 페이지 리다이렉트 방지
- 자동 가입 처리 (API 응답으로 JWT 반환)
- 이메일 자동 인증 처리
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

if TYPE_CHECKING:
    from allauth.socialaccount.models import SocialLogin
    from django.contrib.auth.models import AbstractBaseUser
    from django.http import HttpRequest


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    API 전용 소셜 계정 어댑터

    django-allauth가 웹 페이지로 리다이렉트하는 것을 방지하고
    API 응답으로 직접 처리
    """

    def is_auto_signup_allowed(self, request: HttpRequest, sociallogin: SocialLogin) -> bool:
        """
        자동 가입 허용 여부

        API 방식에서는 항상 자동 가입을 허용하여
        signup 페이지로 리다이렉트하지 않음

        Args:
            request: HTTP 요청 객체
            sociallogin: SocialLogin 인스턴스

        Returns:
            bool: 항상 True (자동 가입 허용)
        """
        return True

    def populate_user(self, request: HttpRequest, sociallogin: SocialLogin, data: dict[str, Any]) -> AbstractBaseUser:
        """
        소셜 로그인 데이터로 User 객체 생성/업데이트

        OAuth 제공자로부터 받은 데이터를 User 모델에 매핑
        이메일 자동 인증 처리

        Args:
            request: HTTP 요청 객체
            sociallogin: SocialLogin 인스턴스
            data: OAuth 제공자로부터 받은 사용자 데이터

        Returns:
            User: 생성/업데이트된 User 인스턴스
        """
        user = super().populate_user(request, sociallogin, data)

        # 소셜 로그인은 OAuth 제공자가 이미 이메일을 인증했으므로
        # 별도의 이메일 인증 절차 불필요
        user.is_email_verified = True

        return user

    def save_user(self, request: HttpRequest, sociallogin: SocialLogin, form: Any = None) -> AbstractBaseUser:
        """
        User 저장 시 추가 처리

        Args:
            request: HTTP 요청 객체
            sociallogin: SocialLogin 인스턴스
            form: 회원가입 폼 (API에서는 None)

        Returns:
            User: 저장된 User 인스턴스
        """
        user = super().save_user(request, sociallogin, form)

        # 이메일 자동 인증 확인 (populate_user에서 설정했지만 재확인)
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])

        return user
