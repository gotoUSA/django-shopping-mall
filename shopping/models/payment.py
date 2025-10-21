from decimal import Decimal

from django.db import models


class Payment(models.Model):
    """
    결제 정보 모델
    토스페이먼츠 결제 데이터를 저장합니다.
    """

    # 결제 상태 선택지
    STATUS_CHOICES = [
        ("ready", "결제 준비"),  # 결제창 오픈 전
        ("in_progress", "결제 진행중"),  # 결제창에서 진행중
        ("waiting_for_deposit", "입금 대기"),  # 가상계좌 입금 대기
        ("done", "결제 완료"),  # 결제 성공
        ("canceled", "결제 취소"),  # 전체 취소
        ("partial_canceled", "부분 취소"),  # 부분 취소 (향후 확장용)
        ("aborted", "결제 실패"),  # 결제 실패
        ("expired", "결제 만료"),  # 가상계좌 입금 기한 만료
    ]

    # 주문 참조 (1:1 관계)
    order = models.OneToOneField(
        "Order",
        on_delete=models.PROTECT,  # 결제 기록이 있으면 주문 삭제 불가
        related_name="payment",
        verbose_name="주문",
    )

    # 토스페이먼츠 결제 정보
    payment_key = models.CharField(
        max_length=200,
        unique=True,
        null=True,
        blank=True,
        verbose_name="토스 결제키",
        help_text="토스페이먼츠에서 발급한 고유 결제키",
    )

    toss_order_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="토스 주문번호",
        help_text="우리 시스템의 주문번호",
    )

    # 금액 정보
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        verbose_name="결제 금액",
    )

    # 결제 수단 정보
    method = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="결제 수단",
        help_text="카드, 계좌이체, 가상계좌 등",
    )

    # 카드 정보 (카드 결제시)
    card_company = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="카드사",
    )

    card_number = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="카드번호",
        help_text="마스킹된 카드번호",
    )

    installment_plan_months = models.IntegerField(
        default=0,
        verbose_name="할부 개월수",
        help_text="0은 일시불",
    )

    # 결제 상태
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="ready",
        verbose_name="결제 상태",
    )

    # 승인 정보
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="승인 일시",
    )

    # 영수증 URL
    receipt_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="영수증 URL",
    )

    # 취소 정보 (전체 취소시)
    is_canceled = models.BooleanField(
        default=False,
        verbose_name="취소 여부",
    )

    canceled_amount = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=Decimal("0"),
        verbose_name="취소 금액",
    )

    cancel_reason = models.TextField(
        blank=True,
        verbose_name="취소 사유",
    )

    canceled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="취소 일시",
    )

    # 토스페이먼츠 원본 응답 저장 (디버깅용)
    raw_response = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="토스 응답 원본",
        help_text="토스페이먼츠 API 응답 전체",
    )

    # 실패 정보
    fail_reason = models.TextField(
        blank=True,
        verbose_name="실패 사유",
    )

    # 시간 정보
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성일시",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="수정일시",
    )

    class Meta:
        db_table = "shopping_payment"
        verbose_name = "결제"
        verbose_name_plural = "결제 목록"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["payment_key"]),
            models.Index(fields=["toss_order_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.toss_order_id} - {self.get_status_display()} ({self.amount:,}원)"

    @property
    def is_paid(self):
        """결제 완료 여부"""
        return self.status == "done"

    @property
    def can_cancel(self):
        """취소 가능 여부"""
        return self.status == "done" and not self.is_canceled

    def mark_as_paid(self, payment_data):
        """
        결제 완료 처리
        토스페이먼츠 승인 응답으로 정보 업데이트
        """
        self.status = "done"
        self.payment_key = payment_data.get("paymentKey")
        self.approved_at = payment_data.get("approvedAt")
        self.method = payment_data.get("method", "")

        # 카드 정보 저장
        card = payment_data.get("card", {})
        if card:
            self.card_company = card.get("company", "")
            self.card_number = card.get("number", "")
            self.installment_plan_months = card.get("installmentPlanMonths", 0)

        # 영수증 URL
        self.receipt_url = payment_data.get("receipt", {}).get("url", "")

        # 원본 응답 저장
        self.raw_response = payment_data

        self.save()

    def mark_as_failed(self, reason=""):
        """결제 실패 처리"""
        self.status = "aborted"
        self.fail_reason = reason
        self.save()

    def mark_as_canceled(self, cancel_data):
        """
        결제 취소 처리
        토스페이먼츠 취소 응답으로 정보 업데이트
        """
        self.status = "canceled"
        self.is_canceled = True
        self.canceled_amount = self.amount  # 전체 취소
        self.cancel_reason = cancel_data.get("cancelReason", "")
        self.canceled_at = cancel_data.get("canceledAt")

        # 원본 응답 업데이트
        self.raw_response = cancel_data

        self.save()

    def save(self, *args, **kwargs):
        """저장 전 처리"""
        # toss_order_id가 없으면 주문번호로 설정
        if not self.toss_order_id and self.order:
            self.toss_order_id = self.order.order_number

        super().save(*args, **kwargs)


class PaymentLog(models.Model):
    """
    결제 로그 모델
    결제 과정의 모든 이벤트를 기록합니다.
    """

    LOG_TYPE_CHOICES = [
        ("request", "결제 요청"),
        ("approve", "결제 승인"),
        ("cancel", "결제 취소"),
        ("webhook", "웹훅 수신"),
        ("error", "에러 발생"),
    ]

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="logs",
        verbose_name="결제",
    )

    log_type = models.CharField(
        max_length=20,
        choices=LOG_TYPE_CHOICES,
        verbose_name="로그 타입",
    )

    message = models.TextField(verbose_name="로그 메시지")

    data = models.JSONField(default=dict, blank=True, verbose_name="추가 데이터")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일시")

    class Meta:
        db_table = "shopping_payment_logs"
        verbose_name = "결제 로그"
        verbose_name_plural = "결제 로그 목록"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_log_type_display()}] {self.payment.order_id} - {self.created_at}"
