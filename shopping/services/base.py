"""서비스 레이어 공통 모듈

서비스 클래스에서 공통으로 사용하는 유틸리티를 제공합니다.

현업 네이밍 컨벤션:
- base.py: 기본 클래스, 데코레이터, 공통 유틸리티
- decorators.py: 데코레이터 전용 (규모가 커지면 분리)
- mixins.py: 믹스인 클래스
- exceptions.py: 예외 클래스 (규모가 커지면 분리)
"""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

# 제네릭 타입 변수 (반환 타입 보존용)
T = TypeVar("T")


def log_service_call(func: Callable[..., T]) -> Callable[..., T]:
    """
    서비스 메서드 호출 로깅 데코레이터

    기능:
    - 메서드 호출 시작/종료 DEBUG 로깅
    - 실행 시간 측정 (ms)
    - 느린 실행 경고 (100ms 이상)
    - 비즈니스 예외 WARNING 로깅
    - 시스템 예외 ERROR 로깅 (스택 트레이스 포함)

    사용법:
        @staticmethod
        @log_service_call
        def some_method(...):
            ...

    Note:
        - 민감 정보(password, token)는 로깅에서 제외됩니다.
        - 서비스 클래스 이름은 모듈명에서 추출됩니다.
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        # 서비스 클래스명 추출 (모듈명에서)
        module_name = func.__module__
        service_name = module_name.split(".")[-1].replace("_service", "").title() + "Service"

        func_name = func.__name__
        start_time = time.perf_counter()

        # 인자 정보 추출 (민감 정보 제외)
        safe_kwargs = {k: v for k, v in kwargs.items() if k not in ("password", "token", "secret")}

        logger.debug(
            "[%s.%s] 호출 시작 | args=%s, kwargs=%s",
            service_name,
            func_name,
            args[1:3] if len(args) > 1 else (),
            safe_kwargs,
        )

        try:
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - start_time) * 1000  # ms

            logger.debug(
                "[%s.%s] 호출 완료 | elapsed=%.2fms",
                service_name,
                func_name,
                elapsed,
            )

            # 느린 쿼리 경고 (100ms 이상)
            if elapsed > 100:
                logger.warning(
                    "[%s.%s] 느린 실행 감지 | elapsed=%.2fms",
                    service_name,
                    func_name,
                    elapsed,
                )

            return result

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000

            # 비즈니스 에러인지 확인 (code 속성 존재 여부로 판단)
            if hasattr(e, "code") and hasattr(e, "message"):
                logger.warning(
                    "[%s.%s] 비즈니스 에러 | code=%s, message=%s, elapsed=%.2fms",
                    service_name,
                    func_name,
                    e.code,
                    e.message,
                    elapsed,
                )
            else:
                logger.error(
                    "[%s.%s] 예외 발생 | error=%s, elapsed=%.2fms",
                    service_name,
                    func_name,
                    str(e),
                    elapsed,
                    exc_info=True,  # 스택 트레이스 포함
                )
            raise

    return wrapper


class ServiceError(Exception):
    """
    서비스 레이어 기본 예외 클래스

    모든 서비스별 예외의 부모 클래스로 사용할 수 있습니다.

    Attributes:
        message: 에러 메시지
        code: 에러 코드 (API 응답에 활용)
        details: 추가 상세 정보

    사용법:
        class CartServiceError(ServiceError):
            pass

        raise CartServiceError("재고 부족", code="INSUFFICIENT_STOCK")
    """

    def __init__(self, message: str, code: str = "SERVICE_ERROR", details: dict | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"
