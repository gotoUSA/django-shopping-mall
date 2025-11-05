FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /code

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 파일 복사
COPY requirements.txt /code/
COPY requirements-dev.txt /code/

# Python 패키지 설치 (에러 발생 시 빌드 중단)
RUN pip install --upgrade pip 
RUN pip install --no-cache-dir -r requirements.txt || exit 1
RUN pip install --no-cache-dir -r requirements-dev.txt || exit 1

# 프로젝트 파일 복사
COPY . /code/

# 환경변수 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 포트 노출
EXPOSE 8000
