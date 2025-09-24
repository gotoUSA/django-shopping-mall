"""
URL configuration for myproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

from shopping.views import payment_views

from shopping.views.email_verification_views import (
    SendVerificationEmailView,
    VerifyEmailView,
    ResendVerificationEmailView,
    check_verification_status,
)

# Swagger 설정
schema_view = get_schema_view(
    openapi.Info(
        title="Django 쇼핑몰 API",
        default_version="v1",
        description="쇼핑몰 프로젝트 API 문서",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@shopping.local"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
    url="http://127.0.0.1:8000",  # Base URL
    patterns=[  # API URL 패턴지정
        path("api/", include("shopping.urls")),
    ],
)


urlpatterns = [
    # 관리자 페이지
    path("admin/", admin.site.urls),
    # shopping 앱 URLs 포함
    path("api/", include("shopping.urls")),
    # 웹페이지
    path("shopping/", include("shopping.urls")),
    # DRF 인증 URLs (로그인/로그아웃 페이지)
    path("api-auth/", include("rest_framework.urls")),
    # Swagger URLs
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    # 이메일 인증 관련 URLs
    path(
        "auth/email/send/",
        SendVerificationEmailView.as_view(),
        name="email-verification-send",
    ),
    path(
        "auth/email/verify/",
        VerifyEmailView.as_view(),
        name="email-verification-verify",
    ),
    path(
        "auth/email/resend/",
        ResendVerificationEmailView.as_view(),
        name="email-verification-resend",
    ),
    path(
        "auth/email/status/",
        check_verification_status,
        name="email-verification-status",
    ),
]

# 개발 환경에서 미디어 파일 서빙

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
