"""
만료된 비밀번호 재설정 토큰 정리 Management Command

만료되거나 사용된 비밀번호 재설정 토큰을 자동으로 삭제합니다.
Cron 또는 Celery Beat으로 주기적으로 실행하여 DB 용량을 관리합니다.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from shopping.models.password_reset import PasswordResetToken


class Command(BaseCommand):
    help = "만료되거나 사용된 비밀번호 재설정 토큰을 정리합니다"

    def add_arguments(self, parser):
        parser.add_argument(
            "--used-days",
            type=int,
            default=30,
            help="사용된 토큰 보관 기간 (기본: 30일, 감사 목적)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제 삭제하지 않고 삭제 대상만 출력",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        used_days = options["used_days"]
        dry_run = options["dry_run"]

        # 만료 시간 계산 (settings.PASSWORD_RESET_TIMEOUT)
        timeout_seconds = getattr(settings, "PASSWORD_RESET_TIMEOUT", 86400)
        expiry_cutoff = now - timedelta(seconds=timeout_seconds)

        # 사용된 토큰 보관 기간
        used_cutoff = now - timedelta(days=used_days)

        # 1. 만료된 미사용 토큰 (created_at이 만료 기간 초과)
        expired_unused_qs = PasswordResetToken.objects.filter(
            is_used=False,
            created_at__lt=expiry_cutoff
        )
        expired_unused_count = expired_unused_qs.count()

        # 2. 오래된 사용된 토큰 (used_at이 보관 기간 초과)
        old_used_qs = PasswordResetToken.objects.filter(
            is_used=True,
            used_at__lt=used_cutoff
        )
        old_used_count = old_used_qs.count()

        # 총 삭제 대상
        total_count = expired_unused_count + old_used_count

        # 출력
        self.stdout.write(
            self.style.WARNING(
                f"=== 비밀번호 재설정 토큰 정리 {'(DRY RUN)' if dry_run else ''} ==="
            )
        )
        self.stdout.write(f"기준 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(
            f"토큰 만료 시간: {timeout_seconds}초 ({timeout_seconds // 3600}시간)"
        )
        self.stdout.write(f"사용된 토큰 보관 기간: {used_days}일")
        self.stdout.write("")

        self.stdout.write(self.style.NOTICE("[삭제 대상]"))
        self.stdout.write(
            f"1. 만료된 미사용 토큰 (생성 후 {timeout_seconds // 3600}시간 초과): "
            f"{expired_unused_count}개"
        )
        self.stdout.write(
            f"2. 오래된 사용된 토큰 (사용 후 {used_days}일 초과): {old_used_count}개"
        )
        self.stdout.write(f"총 삭제 대상: {total_count}개")
        self.stdout.write("")

        # 삭제 실행
        if not dry_run:
            if total_count > 0:
                expired_unused_deleted = expired_unused_qs.delete()
                old_used_deleted = old_used_qs.delete()

                self.stdout.write(self.style.SUCCESS("[삭제 완료]"))
                self.stdout.write(f"만료된 미사용 토큰: {expired_unused_deleted[0]}개")
                self.stdout.write(f"오래된 사용된 토큰: {old_used_deleted[0]}개")
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ 총 {expired_unused_deleted[0] + old_used_deleted[0]}개 삭제됨"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS("✓ 삭제할 토큰이 없습니다.")
                )
        else:
            self.stdout.write(
                self.style.WARNING("DRY RUN 모드: 실제로 삭제하지 않았습니다.")
            )
            self.stdout.write("실제 삭제하려면 --dry-run 옵션을 제거하세요.")
