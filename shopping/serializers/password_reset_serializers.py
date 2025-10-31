from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from rest_framework import serializers

from shopping.models.password_reset import PasswordResetToken

User = get_user_model()


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    비밀번호 재설정 요청 (이메일 발송)

    이메일 주소를 받아서 해당 사용자에게 재설정 링크 발송
    """

    email = serializers.EmailField(
        required=True,
        write_only=True,
        help_text="가입한 이메일 주소",
    )

    message = serializers.CharField(
        read_only=True,
        help_text="응답 메시지",
    )

    def validate_email(self, value):
        """이메일 검증"""
        # 이메일 형식은 EmailField에서 자동 검증됨
        # 여기서는 추가 검증만 수행

        # 보안: 존재하지 않는 이메일이어도 에러를 던지지 않음
        # (사용자 정보 노출 방지)
        return value.lower()  # 소문자로 통일

    def validate(self, attrs):
        """전체 검증"""
        email = attrs.get("email")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # 보안: 사용자가 존재하지 않아도 같은 메시지 반환
            # (계정 존재 여부 노출 방지)
            attrs["user"] = None
            return attrs

        # 탈퇴한 사용자는 재설정 불가
        if hasattr(user, "is_withdrawn") and user.is_withdrawn:
            raise serializers.ValidationError({"email": "탈퇴한 회원은 비밀번호 재설정을 할 수 없습니다."})

        # 비활성화된 계정은 재설정 불가
        if not user.is_active:
            raise serializers.ValidationError({"email": "비활성화된 계정입니다. 관리자에게 문의하세요."})

        attrs["user"] = user
        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    비밀번호 재설정 확인 (새 비밀번호 설정)

    토큰과 새 비밀번호를 받아서 비밀번호 변경
    """

    token = serializers.UUIDField(
        required=True,
        write_only=True,
        help_text="이메일로 받은 재설정 토큰",
    )

    new_password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
        help_text="새 비밀번호 (최소 8자)",
    )

    new_password2 = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
        help_text="새 비밀번호 확인",
    )

    message = serializers.CharField(
        read_only=True,
        help_text="응답 메시지",
    )

    def validate_token(self, value):
        """토큰 검증"""
        try:
            token_obj = PasswordResetToken.objects.get(token=value, is_used=False)
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError("유효하지 않은 토큰입니다.")

        # 만료 확인
        if token_obj.is_expired():
            raise serializers.ValidationError("토큰이 만료되었습니다. 다시 요청해주세요.")

        # 인스턴스에 저장 (save에서 사용)
        self.token_obj = token_obj
        return value

    def validate_new_password(self, value):
        """새 비밀번호 검증 (Django 비밀번호 정책 적용)"""
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))

        return value

    def validate(self, attrs):
        """전체 검증"""
        new_password = attrs.get("new_password")
        new_password2 = attrs.get("new_password2")

        # 비밀번호 일치 확인
        if new_password != new_password2:
            raise serializers.ValidationError({"new_password2": "비밀번호가 일치하지 않습니다."})

        return attrs

    def save(self):
        """비밀번호 변경 처리"""
        user = self.token_obj.user
        new_password = self.validated_data["new_password"]

        # 비밀번호 변경
        user.set_password(new_password)
        user.save(update_fields=["password"])

        # 토큰 사용 처리
        self.token_obj.mark_as_used()

        # EmailLog 업데이트 (있는 경우)
        from shopping.models.email_verification import EmailLog

        EmailLog.objects.filter(
            user=user, email_type="password_reset", status="sent", sent_at__gte=self.token_obj.created_at
        ).update(status="verified", verified_at=timezone.now())

        return user
