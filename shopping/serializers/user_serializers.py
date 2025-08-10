from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from shopping.models.user import User


class UserSerializer(serializers.ModelSerializer):
    """
    사용자 프로필 조회/수정용 시리얼라이저
    - 비밀번호는 제외하고 표시
    - 읽기 전용 필드 설정
    """

    class Meta:
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "birth_date",
            "postal_code",
            "address",
            "address_detail",
            "membership_level",
            "points",
            "is_email_verified",
            "is_phone_verified",
            "agree_marketing_email",
            "agree_marketing_sms",
            "date_joined",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "username",
            "membership_level",
            "points",
            "is_email_verified",
            "is_phone_verified",
            "date_joined",
            "last_login",
        ]


class RegisterSerializer(serializers.ModelSerializer):
    """
    회원가입용 시리얼라이저
    - 필수: username, email, password, password2
    - 선택: 나머지 필드들
    """

    # 비밀번호 확인 필드 (DB에는 저장 안됨)
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type", "password"},
        lebel="비밀번호 확인",
    )

    # 비밀번호는 쓰기 전용
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],  # Django 기본 비밀번호 검증
        style={"input_type": "password"},
        label="비밀번호",
    )

    # 이메일 필수
    email = serializers.EmailField(required=True, label="이메일")

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password2",
            "first_name",
            "last_name",
            "phone_number",
            "birth_date",
            "postal_code",
            "address",
            "address_detail",
            "agree_marketing_email",
            "agree_marketing_sms",
        ]
        extra_kwargs = {"username": {"required": True}, "email": {"required": True}}

    def validate_email(self, value):
        """이메일 중복 검사"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("이미 사용중인 이메일입니다.")
        return value

    def validate_username(self, value):
        """사용자명 중복 검사"""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("이미 사용중인 사용자명입니다.")
        return value

    def validate(self, attrs):
        """비밀번호 일치 검사"""
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "비밀번호가 일치하지 않습니다."}
            )
        return attrs

    def create(self, validated_data):
        """사용자 생성"""
        # password2는 DB에 저장하지 않으므로 제거
        validated_data.pop("password2")

        # create_user 메서드를 사용하면 비밀번호가 자동으로 해시화됨
        user = User.objects.create_user(**validated_data)

        return user


class LoginSerializer(serializers.Serializer):
    """
    로그인용 시리얼라이저
    - username과 password로 인증
    - JWT 토큰은 View에서 생성
    """

    username = serializers.CharField(required=True, label="사용자명")
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
        label="비밀번호",
    )

    def validate(self, attrs):
        """로그인 인증 검증"""
        username = attrs.get("username")
        password = attrs.get("password")

        if username and password:
            # Django 기본 인증 함수 사용
            user = authenticate(
                request=self.context.get("request"),
                username=username,
                password=password,
            )

            if not user:
                raise serializers.ValidationError(
                    "아이디 또는 비밀번호가 올바르지 않습니다."
                )

            if not user.is_active:
                raise serializers.ValidationError("비활성화된 계정입니다.")

            # 탈퇴한 회원 체크
            if user.is_withdrawn:
                raise serializers.ValidationError("탈퇴한 회원입니다.")

        else:
            raise serializers.ValidationError("아이디와 비밀번호를 모두 입력해주세요.")

        attrs["user"] = user
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    """
    비밀번호 변경용 시리얼라이저
    - 현재 비밀번호 확인 후 새 비밀번호로 변경
    """

    old_password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
        label="현재 비밀번호",
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        validators=[validate_password],
        style={"input_type": "password"},
        label="새 비밀번호",
    )
    new_password2 = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
        label="새 비밀번호 확인",
    )

    def validate_old_password(self, value):
        """현재 비밀번호 검증"""
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("현재 비밀번호가 올바르지 않습니다.")
        return value

    def validate(self, attrs):
        """새 비밀번호 일치 검사"""
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError(
                {"new_password": "새 비밀번호가 일치하지 않습니다"}
            )
        return attrs

    def save(self):
        """비밀번호 변경 저장"""
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user


class TokenResponseSerializer(serializers.Serializer):
    """
    토큰 응답용 시리얼라이저
    - 로그인/회원가입 성공 시 반환되는 데이터 구조
    """

    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = UserSerializer(read_only=True)
