"""
Base Django settings for EduConnect project.

Common settings shared across all environments (development, testing, production).
Official MongoDB backend: django_mongodb_backend.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# BASE_DIR points to repository root (c:\...\Education)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")

# Security key from environment
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-educonnect-default-dev-key-change-in-production-12345",
)

# Application definition
INSTALLED_APPS = [
    # MongoDB-compatible Admin, Auth, ContentTypes configs
    "educonnect.apps.MongoAdminConfig",
    "educonnect.apps.MongoAuthConfig",
    "educonnect.apps.MongoContentTypesConfig",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Official MongoDB backend
    "django_mongodb_backend",
    # Accounts and Authentication app
    "apps.accounts.apps.AccountsConfig",
    # Project core module
    "apps.core",
]

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# Authentication & Session Settings
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard_redirect"
LOGOUT_REDIRECT_URL = "accounts:login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 86400  # 24 hours


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "educonnect.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "educonnect.wsgi.application"
ASGI_APPLICATION = "educonnect.asgi.application"

# ==============================================================================
# Database Configuration - Official MongoDB Backend
# ==============================================================================
# Supports both MongoDB Atlas (mongodb+srv://) and Local MongoDB (mongodb://)
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_NAME = os.getenv("MONGODB_NAME", "educonnect_db")

DATABASES = {
    "default": {
        "ENGINE": "django_mongodb_backend",
        "HOST": MONGODB_URI,
        "NAME": MONGODB_NAME,
    },
}

# Required MongoDB backend settings
DATABASE_ROUTERS = ["django_mongodb_backend.routers.MongoRouter"]
DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"

# Official MongoDB pre-packaged migration paths
MIGRATION_MODULES = {
    "admin": "mongo_migrations.admin",
    "auth": "mongo_migrations.auth",
    "contenttypes": "mongo_migrations.contenttypes",
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
