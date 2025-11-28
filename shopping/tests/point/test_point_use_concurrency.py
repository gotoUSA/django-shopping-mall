"""
포인트 사용 API 경량 동시성 테스트

테스트 범위:
- 10명 동시 요청 시 기본 동작 검증
- 최종 포인트 잔액 정합성
- 데이터 손실/중복 없음
- PointHistory 레코드 정합성

주의: 이 테스트는 기본적인 동시성 동작만 검증합니다.
실제 대규모 동시성 테스트는 Locust를 사용하세요.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from django.db import connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APIClient

from shopping.models.point import PointHistory
from shopping.models.user import User
from shopping.tests.factories import PointHistoryFactory, UserFactory


class TestPointUseConcurrency(TransactionTestCase):
    """
    포인트 사용 API 경량 동시성 테스트

    TransactionTestCase 사용 이유:
    - 실제 DB 트랜잭션 테스트 필요
    - 동시성 시나리오에서 select_for_update 검증
    """

    def setUp(self):
        """테스트 설정"""
        # Django DB connection 닫기 (각 스레드가 새 연결 사용하도록)
        connection.close()

    def _make_point_use_request(self, user_id: int, amount: int) -> dict:
        """
        포인트 사용 요청 헬퍼

        각 스레드에서 독립적인 DB 연결과 APIClient 사용
        """
        # 각 스레드에서 새로운 연결 사용
        from django.db import connection

        connection.close()

        client = APIClient()
        user = User.objects.get(id=user_id)
        client.force_authenticate(user=user)

        url = reverse("point_use")
        response = client.post(url, {"amount": amount}, format="json")

        return {
            "status_code": response.status_code,
            "success": response.data.get("success", False),
            "message": response.data.get("message", ""),
            "remaining": response.data.get("data", {}).get("remaining_points"),
        }

    def test_concurrent_10_users_same_user(self):
        """
        동일 사용자 10회 동시 요청

        시나리오:
        - 사용자 보유 포인트: 10,000P
        - 10개 요청이 각각 500P 사용 시도
        - 예상: 성공 10회 또는 일부 포인트 부족
        - 검증: 최종 잔액 정합성
        """
        # Arrange
        user = UserFactory.with_points(10000)
        # FIFO 대상 적립 이력 생성
        PointHistoryFactory.earn(
            user=user,
            points=10000,
            balance=10000,
            expires_at=timezone.now() + timedelta(days=365),
        )

        num_requests = 10
        amount_per_request = 500
        results = []

        # Act - 동시 요청
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self._make_point_use_request, user.id, amount_per_request) for _ in range(num_requests)]

            for future in as_completed(futures):
                results.append(future.result())

        # Assert
        user.refresh_from_db()

        # 성공한 요청 수 카운트
        success_count = sum(1 for r in results if r["success"])

        # 성공한 요청 수만큼 포인트가 차감되어야 함
        expected_remaining = 10000 - (success_count * amount_per_request)
        assert user.points == expected_remaining, (
            f"포인트 정합성 오류: expected={expected_remaining}, actual={user.points}, " f"success_count={success_count}"
        )

        # PointHistory 레코드 수 검증 (use 타입)
        use_history_count = PointHistory.objects.filter(user=user, type="use").count()
        assert (
            use_history_count == success_count
        ), f"이력 정합성 오류: use_history={use_history_count}, success={success_count}"

        # 모든 요청이 성공했거나 포인트 부족으로 실패해야 함
        for result in results:
            assert result["status_code"] in [200, 400], f"예상치 못한 상태 코드: {result['status_code']}"

    def test_concurrent_10_different_users(self):
        """
        서로 다른 10명의 사용자 동시 요청

        시나리오:
        - 10명의 사용자 각각 5,000P 보유
        - 각 사용자가 1,000P 사용 시도
        - 예상: 모두 성공
        - 검증: 각 사용자 잔액 정합성
        """
        # Arrange
        users = []
        for _ in range(10):
            user = UserFactory.with_points(5000)
            PointHistoryFactory.earn(
                user=user,
                points=5000,
                balance=5000,
                expires_at=timezone.now() + timedelta(days=365),
            )
            users.append(user)

        amount_per_request = 1000
        results = []

        # Act - 동시 요청
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self._make_point_use_request, user.id, amount_per_request) for user in users]

            for future in as_completed(futures):
                results.append(future.result())

        # Assert
        # 모든 요청이 성공해야 함
        success_count = sum(1 for r in results if r["success"])
        assert success_count == 10, f"모든 요청이 성공해야 함: success={success_count}/10"

        # 각 사용자의 잔액 검증
        for user in users:
            user.refresh_from_db()
            assert user.points == 4000, f"사용자 {user.id} 잔액 오류: expected=4000, actual={user.points}"

        # 총 PointHistory 레코드 수 검증
        total_use_histories = PointHistory.objects.filter(type="use").count()
        assert total_use_histories == 10, f"총 use 이력 수 오류: expected=10, actual={total_use_histories}"

    def test_concurrent_race_condition_prevention(self):
        """
        Race Condition 방지 검증

        시나리오:
        - 사용자 보유 포인트: 1,000P
        - 10개 요청이 각각 500P 사용 시도
        - 예상: 최대 2회만 성공 (1000 / 500 = 2)
        - 검증: 포인트 음수 방지
        """
        # Arrange
        user = UserFactory.with_points(1000)
        PointHistoryFactory.earn(
            user=user,
            points=1000,
            balance=1000,
            expires_at=timezone.now() + timedelta(days=365),
        )

        num_requests = 10
        amount_per_request = 500
        results = []

        # Act - 동시 요청
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self._make_point_use_request, user.id, amount_per_request) for _ in range(num_requests)]

            for future in as_completed(futures):
                results.append(future.result())

        # Assert
        user.refresh_from_db()

        # 성공한 요청 수
        success_count = sum(1 for r in results if r["success"])

        # 최대 2회만 성공해야 함
        assert success_count <= 2, f"Race condition 발생: success_count={success_count} (expected <= 2)"

        # 포인트는 절대 음수가 되면 안 됨
        assert user.points >= 0, f"포인트 음수 방지 실패: points={user.points}"

        # 정합성 검증
        expected_remaining = 1000 - (success_count * amount_per_request)
        assert user.points == expected_remaining, f"정합성 오류: expected={expected_remaining}, actual={user.points}"

    def test_concurrent_metadata_integrity(self):
        """
        동시 요청 시 metadata 정합성 검증

        시나리오:
        - 단일 적립 이력에서 여러 요청이 동시에 차감
        - metadata.used_amount와 usage_history 정합성 검증
        """
        # Arrange
        user = UserFactory.with_points(5000)
        earn_history = PointHistoryFactory.earn(
            user=user,
            points=5000,
            balance=5000,
            expires_at=timezone.now() + timedelta(days=365),
        )

        num_requests = 5
        amount_per_request = 500
        results = []

        # Act - 동시 요청
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self._make_point_use_request, user.id, amount_per_request) for _ in range(num_requests)]

            for future in as_completed(futures):
                results.append(future.result())

        # Assert
        success_count = sum(1 for r in results if r["success"])

        # 적립 이력의 metadata 검증
        earn_history.refresh_from_db()
        used_amount = earn_history.metadata.get("used_amount", 0)
        usage_history = earn_history.metadata.get("usage_history", [])

        # used_amount는 성공한 요청 수 × 금액과 일치해야 함
        expected_used = success_count * amount_per_request
        assert used_amount == expected_used, f"used_amount 정합성 오류: expected={expected_used}, actual={used_amount}"

        # usage_history 항목 수는 성공한 요청 수와 일치해야 함
        assert (
            len(usage_history) == success_count
        ), f"usage_history 정합성 오류: expected={success_count}, actual={len(usage_history)}"

        # usage_history 합계도 검증
        history_total = sum(h["amount"] for h in usage_history)
        assert history_total == expected_used, f"usage_history 합계 오류: expected={expected_used}, actual={history_total}"
