"""
오래된 장바구니 정리 Management Command

비회원 및 회원의 오래된 장바구니를 자동으로 삭제합니다.
Cron으로 주기적으로 실행하여 DB 용량을 관리합니다.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from shopping.models import Cart


class Command(BaseCommand):
    help = "오래된 장바구니를 정리합니다 (비회원: 7일, 회원 비활성: 90일)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--anonymous-days",
            type=int,
            default=7,
            help="비회원 활성 장바구니 보관 기간 (기본: 7일)",
        )
        parser.add_argument(
            "--inactive-days",
            type=int,
            default=90,
            help="회원 비활성 장바구니 보관 기간 (기본: 90일)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제 삭제하지 않고 삭제 대상만 출력",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        anonymous_days = options["anonymous_days"]
        inactive_days = options["inactive_days"]
        dry_run = options["dry_run"]

        # 1. 비회원 활성 장바구니: N일 이상 미수정
        anon_active_cutoff = now - timedelta(days=anonymous_days)
        anon_active_qs = Cart.objects.filter(
            user__isnull=True, is_active=True, updated_at__lt=anon_active_cutoff
        )
        anon_active_count = anon_active_qs.count()

        # 2. 비회원 비활성 장바구니: 즉시 삭제
        anon_inactive_qs = Cart.objects.filter(user__isnull=True, is_active=False)
        anon_inactive_count = anon_inactive_qs.count()

        # 3. 회원 비활성 장바구니: N일 이상
        user_inactive_cutoff = now - timedelta(days=inactive_days)
        user_inactive_qs = Cart.objects.filter(
            user__isnull=False, is_active=False, updated_at__lt=user_inactive_cutoff
        )
        user_inactive_count = user_inactive_qs.count()

        # 출력
        self.stdout.write(self.style.WARNING(f"=== 장바구니 정리 {'(DRY RUN)' if dry_run else ''} ==="))
        self.stdout.write(f"기준 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("")

        self.stdout.write(self.style.NOTICE("[삭제 대상]"))
        self.stdout.write(
            f"1. 비회원 활성 장바구니 ({anonymous_days}일 미수정): {anon_active_count}개"
        )
        self.stdout.write(f"2. 비회원 비활성 장바구니: {anon_inactive_count}개")
        self.stdout.write(f"3. 회원 비활성 장바구니 ({inactive_days}일 경과): {user_inactive_count}개")
        self.stdout.write(f"총 삭제 대상: {anon_active_count + anon_inactive_count + user_inactive_count}개")
        self.stdout.write("")

        # 삭제 실행
        if not dry_run:
            anon_active_deleted = anon_active_qs.delete()
            anon_inactive_deleted = anon_inactive_qs.delete()
            user_inactive_deleted = user_inactive_qs.delete()

            self.stdout.write(self.style.SUCCESS("[삭제 완료]"))
            self.stdout.write(f"비회원 활성: {anon_active_deleted[0]}개")
            self.stdout.write(f"비회원 비활성: {anon_inactive_deleted[0]}개")
            self.stdout.write(f"회원 비활성: {user_inactive_deleted[0]}개")
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ 총 {anon_active_deleted[0] + anon_inactive_deleted[0] + user_inactive_deleted[0]}개 삭제됨"
                )
            )
        else:
            self.stdout.write(self.style.WARNING("DRY RUN 모드: 실제로 삭제하지 않았습니다."))
            self.stdout.write("실제 삭제하려면 --dry-run 옵션을 제거하세요.")
