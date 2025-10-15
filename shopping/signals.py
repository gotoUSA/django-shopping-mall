from django.dispatch import receiver
from allauth.socialaccount.signals import pre_social_login
from shopping.models.email_verification import EmailVerificationToken


@receiver(pre_social_login)
def handle_social_login(sender, request, sociallogin, **kwargs):
    """
    소셜 로그인 시그널 핸들러

    소셜 로그인이 발생하면 자동으로:
    1. 사용자의 is_email_verified를 True로 설정
    2. 기존 이메일 인증 토큰 무효화
    Args:
        sender: 시그널을 보낸 객체
        request: HTTP 요청 객체
        sociallogin: SocialLogin 인스턴스
        **kwargs: 추가 매개변수
    """

    # 소셜 로그인으로 연결된 사용자 가져오기
    user = sociallogin.user

    # 신규 가입인 경우 (user.pk가 None이면 아직 DB에 저장 안 됨)
    if not user.pk:
        return

    # 이메일 자동 인증 처리
    if not user.is_email_verified:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

        print(f"✅ 소셜 로그인: {user.email} 이메일 자동 인증 완료")

    # 기존 이메일 인증 토큰 무효화 (이미 소셜로 인증됨)
    EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)

    print(f"🔐 소셜 로그인: {user.email} 기존 인증 토큰 무효화 완료")
