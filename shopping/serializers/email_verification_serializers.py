from django.utils import timezone

from rest_framework import serializers

from shopping.models.email_verification import EmailLog, EmailVerificationToken


class EmailVerificationTokenSerializer(serializers.ModelSerializer):
    """이메일 인증 토큰 시리얼라이저"""

    class Meta:
        model = EmailVerificationToken
        fields = ["token", "verification_code", "created_at", "is_expired"]
        read_only_fields = ["token", "verification_code", "created_at"]

    is_expired = serializers.SerializerMethodField()

    def get_is_expired(self, obj):
        return obj.is_expired()


class SendVerificationEmailSerializer(serializers.Serializer):
    """이메일 발송 요청 시리얼라이저"""

    message = serializers.CharField(read_only=True)
    verification_code = serializers.CharField(read_only=True, required=False)

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user

        # 이미 인증된 사용자 체크
        if user.is_email_verified:
            raise serializers.ValidationError({"error": "이미 이메일 인증이 완료되었습니다."})

        # 최근 토큰 확인 (재발송 제한)
        recent_token = EmailVerificationToken.objects.filter(user=user, is_used=False).order_by("-created_at").first()

        if recent_token and not recent_token.can_resend():
            raise serializers.ValidationError({"error": "1분 후에 다시 시도해주세요."})

        return attrs


class VerifyEmailByTokenSerializer(serializers.Serializer):
    """UUID 토큰으로 이메일 인증 시리얼라이저"""

    token = serializers.UUIDField(required=True, write_only=True)
    message = serializers.CharField(read_only=True)

    def validate_token(self, value):
        try:
            token = EmailVerificationToken.objects.get(token=value, is_used=False)
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError("유효하지 않은 토큰입니다.")

        if token.is_expired():
            raise serializers.ValidationError("토큰이 만료되었습니다.")

        self.token_obj = token
        return value

    def save(self):
        """토큰 인증 처리"""
        user = self.token_obj.user

        # 사용자 이메일 인증 처리
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

        # 토큰 사용 처리
        self.token_obj.mark_as_used()

        # 로그 업데이트
        EmailLog.objects.filter(token=self.token_obj).update(status="verified", verified_at=timezone.now())

        return user


class VerifyEmailByCodeSerializer(serializers.Serializer):
    """6자리 코드로 이메일 인증 시리얼라이저"""

    code = serializers.CharField(required=True, write_only=True, min_length=6, max_length=6)
    message = serializers.CharField(read_only=True)

    def validate_code(self, value):
        request = self.context.get("request")
        user = request.user

        # 대문자로 변환
        value = value.upper()

        try:
            token = EmailVerificationToken.objects.get(user=user, verification_code=value, is_used=False)
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError("유효하지 않은 인증 코드입니다.")

        if token.is_expired():
            raise serializers.ValidationError("인증 코드가 만료되었습니다.")

        self.token_obj = token
        return value

    def save(self):
        """코드 인증 처리"""
        user = self.token_obj.user

        # 사용자 이메일 인증 처리
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

        # 토큰 사용 처리
        self.token_obj.mark_as_used()

        # 로그 업데이트
        EmailLog.objects.filter(token=self.token_obj).update(status="verified", verified_at=timezone.now())

        return user


class ResendVerificationEmailSerializer(serializers.Serializer):
    """이메일 재발송 시리얼라이저"""

    message = serializers.CharField(read_only=True)
    verification_code = serializers.CharField(read_only=True, required=False)

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user

        # 이미 인증된 사용자 체크
        if user.is_email_verified:
            raise serializers.ValidationError({"error": "이미 이메일 인증이 완료되었습니다."})

        # 최근 토큰 확인 (재발송 제한)
        recent_token = EmailVerificationToken.objects.filter(user=user, is_used=False).order_by("-created_at").first()

        if recent_token and not recent_token.can_resend():
            raise serializers.ValidationError({"error": "1분 후에 다시 시도해주세요. 잠시만 기다려주세요."})

        return attrs


class EmailLogSerializer(serializers.ModelSerializer):
    """이메일 로그 시리얼라이저 (Admin용)"""

    class Meta:
        model = EmailLog
        fields = "__all__"
        read_only_fields = ["created_at"]
