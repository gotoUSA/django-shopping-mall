"""
계좌번호 등 민감 정보 암호화 유틸리티

Fernet 대칭 암호화를 사용하여 계좌번호를 안전하게 저장하고,
필요 시 복호화하여 사용할 수 있습니다.

사용 예시:
    >>> from shopping.utils.encryption import encrypt_account_number, decrypt_account_number
    >>> account = "110-123-456789"
    >>> encrypted = encrypt_account_number(account)
    >>> decrypted = decrypt_account_number(encrypted)
    >>> assert decrypted == account
"""

from __future__ import annotations

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_cipher() -> Fernet:
    """
    암호화 키를 사용하여 Fernet 인스턴스 생성

    Returns:
        Fernet: 암호화/복호화에 사용할 Fernet 인스턴스

    Raises:
        ValueError: ENCRYPTION_KEY가 설정되지 않은 경우
    """
    encryption_key = getattr(settings, 'ENCRYPTION_KEY', None)

    if not encryption_key:
        raise ValueError(
            "ENCRYPTION_KEY가 설정되지 않았습니다. "
            ".env 파일에 ENCRYPTION_KEY를 추가해주세요.\n"
            "생성 방법: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )

    # 문자열로 저장된 키를 bytes로 변환
    if isinstance(encryption_key, str):
        encryption_key = encryption_key.encode()

    return Fernet(encryption_key)


def encrypt_account_number(account_number: str) -> str:
    """
    계좌번호를 암호화합니다.

    Args:
        account_number: 암호화할 계좌번호 (예: "110-123-456789")

    Returns:
        str: Base64로 인코딩된 암호화된 문자열

    Raises:
        ValueError: account_number가 비어있는 경우

    Example:
        >>> encrypted = encrypt_account_number("110-123-456789")
        >>> print(encrypted)  # gAAAAABf...
    """
    if not account_number:
        raise ValueError("계좌번호가 비어있습니다.")

    try:
        cipher = _get_cipher()
        encrypted_bytes = cipher.encrypt(account_number.encode())
        return encrypted_bytes.decode()
    except Exception as e:
        logger.error(f"계좌번호 암호화 실패: {e}")
        raise


def decrypt_account_number(encrypted_account: str) -> str:
    """
    암호화된 계좌번호를 복호화합니다.

    Args:
        encrypted_account: 암호화된 계좌번호 (Base64 문자열)

    Returns:
        str: 복호화된 원본 계좌번호

    Raises:
        ValueError: encrypted_account가 비어있거나 복호화 실패 시

    Example:
        >>> decrypted = decrypt_account_number("gAAAAABf...")
        >>> print(decrypted)  # 110-123-456789
    """
    if not encrypted_account:
        raise ValueError("암호화된 계좌번호가 비어있습니다.")

    try:
        cipher = _get_cipher()
        decrypted_bytes = cipher.decrypt(encrypted_account.encode())
        return decrypted_bytes.decode()
    except InvalidToken:
        logger.error("계좌번호 복호화 실패: 잘못된 토큰 또는 암호화 키")
        raise ValueError("계좌번호 복호화에 실패했습니다. 암호화 키를 확인해주세요.")
    except Exception as e:
        logger.error(f"계좌번호 복호화 실패: {e}")
        raise


def mask_account_number(account_number: Optional[str]) -> str:
    """
    계좌번호를 마스킹 처리합니다.

    마지막 4자리만 표시하고 나머지는 별표(*)로 대체합니다.
    하이픈(-)이 있는 경우 구조를 유지합니다.

    Args:
        account_number: 마스킹할 계좌번호 (예: "110-123-456789")

    Returns:
        str: 마스킹된 계좌번호 (예: "***-***-6789")

    Example:
        >>> masked = mask_account_number("110-123-456789")
        >>> print(masked)  # ***-***-6789

        >>> masked = mask_account_number("1234567890")
        >>> print(masked)  # ******7890
    """
    if not account_number:
        return ""

    # 하이픈 제거하여 순수 숫자만 추출
    numbers_only = account_number.replace("-", "").replace(" ", "")

    if len(numbers_only) < 4:
        # 4자리 미만인 경우 전체 마스킹
        return "*" * len(account_number)

    # 마지막 4자리 추출
    last_four = numbers_only[-4:]

    # 하이픈이 있는 경우 구조 유지
    if "-" in account_number:
        parts = account_number.split("-")
        masked_parts = []

        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # 마지막 파트: 뒤 4자리 표시
                masked_part = "*" * (len(part) - 4) + last_four if len(part) >= 4 else last_four[-len(part):]
            else:
                # 다른 파트: 전체 마스킹
                masked_part = "*" * len(part)
            masked_parts.append(masked_part)

        return "-".join(masked_parts)
    else:
        # 하이픈이 없는 경우: 앞부분 마스킹 + 뒤 4자리
        return "*" * (len(numbers_only) - 4) + last_four


def is_encrypted(value: str) -> bool:
    """
    문자열이 암호화된 값인지 확인합니다.

    Fernet으로 암호화된 값은 Base64 형식이며 특정 패턴을 가집니다.

    Args:
        value: 확인할 문자열

    Returns:
        bool: 암호화된 값이면 True, 아니면 False

    Note:
        이 함수는 완벽하지 않으며, 형식만 확인합니다.
        실제 복호화 가능 여부는 decrypt_account_number()로 확인해야 합니다.
    """
    if not value:
        return False

    # Fernet 토큰은 Base64로 인코딩되며 'gAAAAA'로 시작
    # (버전 0x80을 나타내는 바이트)
    try:
        return value.startswith('gAAAAA') and len(value) > 50
    except (AttributeError, TypeError):
        return False
