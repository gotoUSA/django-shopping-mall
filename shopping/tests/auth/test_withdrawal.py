import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestWithdrawal:
    def test_withdraw_success(self, authenticated_client):
        """정상 탈퇴"""
        pass

    def test_withdraw_wrong_password(self, authenticated_client):
        """잘못된 비밀번호로 탈퇴 실패"""
        pass

    def test_login_after_withdrawal(self, api_client):
        """탈퇴 후 로그인 시도"""
        pass

    def test_data_preserved_after_withdrawal(self, db):
        """탈퇴 후 포인트/주문 내역 보존"""
        pass

    def test_reregister_after_withdrawal(self, api_client):
        """탈퇴 후 재가입 시도"""
        pass
