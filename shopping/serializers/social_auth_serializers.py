from dj_rest_auth.registration.serializers import SocialLoginSerializer
from rest_framework import serializers

from shopping.serializers.user_serializers import UserSerializer


class CustomSocialLoginSerializer(SocialLoginSerializer):
    """
    소셜 로그인 커스텀 시리얼라이저

    기본 dj-rest-auth 응답에 사용자 정보를 추가합니다.
    """

    user = UserSerializer(read_only=True)

    class Meta:
        fields = ["access_token", "refresh_token", "user"]


class SocialAccountSerializer(serializers.Serializer):
    """
    소셜 계정 정보 시리얼라이저

    연결된 소셜 계정 목록을 보여줍니다.
    """

    provider = serializers.CharField(help_text="소셜 로그인 제공자 (google/kakao/naver)")
    uid = serializers.CharField(help_text="소셜 계정 고유 ID")
    extra_data = serializers.JSONField(help_text="추가 정보 (이름, 프로필 사진 등)")
    date_joined = serializers.DateTimeField(source="date_joined", help_text="연결 날짜")

    class Meta:
        fields = ["provider", "uid", "extra_data", "date_joined"]
