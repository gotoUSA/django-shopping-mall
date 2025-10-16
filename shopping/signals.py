from django.dispatch import receiver
from django.db.models.signals import post_save
from allauth.socialaccount.signals import pre_social_login
from allauth.socialaccount.models import SocialAccount
from shopping.models.email_verification import EmailVerificationToken
from shopping.models.user import User


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
    updated_count = EmailVerificationToken.objects.filter(
        user=user, is_used=False
    ).update(is_used=True)

    if updated_count > 0:
        print(f"🔐 소셜 로그인: {user.email} 기존 인증 토큰 무효화 완료")


@receiver(post_save, sender=SocialAccount)
def handle_new_social_account(sender, instance, created, **kwargs):
    """
    소셜 계정 생성 시그널 핸들러 (신규 가입자)

    신규 소셜 가입 시:
    1. 자동으로 이메일 인증 처리
    2. 기존 미사용 토큰 무효화

    Args:
        sender: SocialAccount 모델
        instance: 생성된 SocialAccount 인스턴스
        created: 신규 생성 여부
        **kwargs: 추가 매개변수
    """
    # 신규 생성된 소셜 계정만 처리
    if not created:
        return

    user = instance.user

    # 이메일이 없으면 스킵
    if not user.email:
        print(f"⚠️ 소셜 가입: {user.username} - 이메일 없음")
        return

    if user.is_email_verified:
        return

    # 이메일 자동 인증 처리
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])
    print(f"✅ 소셜 가입 (신규): {user.email} 이메일 자동 인증 완료")

    # 혹시 있을 수 있는 기존 토큰 무효화
    updated_count = EmailVerificationToken.objects.filter(
        user=user, is_used=False
    ).update(is_used=True)

    if updated_count > 0:
        print(
            f"🔐 소셜 가입: {user.email} 기존 인증 토큰 {updated_count}개 무효화 완료"
        )
