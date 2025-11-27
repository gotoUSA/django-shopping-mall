"""
Payment Configuration (Toss Payments)
토스페이먼츠 관련 모든 설정을 관리합니다.
"""

import os

# ==========================================
# 토스페이먼츠 설정
# ==========================================
#
# 토스페이먼츠 대시보드에서 발급받은 키를 환경변수로 설정하세요.
# https://developers.tosspayments.com/my/api-keys
#
# .env 파일 예시:
# TOSS_CLIENT_KEY=test_ck_...  # 클라이언트 키 (프론트엔드용)
# TOSS_SECRET_KEY=test_sk_...  # 시크릿 키 (서버용)
# TOSS_WEBHOOK_SECRET=...      # 웹훅 시크릿 (웹훅 서명 검증용)

# 토스페이먼츠 API 키
TOSS_CLIENT_KEY = os.environ.get("TOSS_CLIENT_KEY", "")  # 테스트 클라이언트 키
TOSS_SECRET_KEY = os.environ.get("TOSS_SECRET_KEY", "")  # 테스트 시크릿 키

# 토스페이먼츠 웹훅 시크릿 (웹훅 서명 검증용)
# 토스페이먼츠 대시보드 > 웹훅 > 웹훅 엔드포인트 추가 후 발급
TOSS_WEBHOOK_SECRET = os.environ.get("TOSS_WEBHOOK_SECRET", "")

# 토스페이먼츠 API URL
# 테스트: https://api.tosspayments.com
# 운영: https://api.tosspayments.com (동일)
TOSS_BASE_URL = os.environ.get("TOSS_BASE_URL", "https://api.tosspayments.com")
