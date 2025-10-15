from django.apps import AppConfig


class ShoppingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopping"

    def ready(self):
        """
        앱이 준비되면 시그널 등록

        소셜 로그인 시그널을 활성화하여
        자동 이메일 인증 처리가 작동하도록 합니다.
        """
        import shopping.signals  # noqa
