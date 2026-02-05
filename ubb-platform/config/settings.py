import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["SECRET_KEY"]  # Required — KeyError = fail to start

DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1", "yes")

_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()]
if not DEBUG and not ALLOWED_HOSTS:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set when DEBUG=False")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    # UBB Apps
    "apps.platform.tenants",
    "apps.platform.customers",
    "apps.metering.usage",
    "apps.metering.pricing",
    "apps.billing.stripe",
    "apps.billing.gating",
    "apps.billing.invoicing",
    "apps.tenant_billing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.CorrelationIdMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///db.sqlite3",
        conn_max_age=600,
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Redis / Celery
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

from kombu import Queue

CELERY_TASK_QUEUES = [
    Queue("ubb_invoicing"),
    Queue("ubb_webhooks"),
    Queue("ubb_topups"),
    Queue("ubb_billing"),
]

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "expire-stale-topup-attempts": {
        "task": "apps.platform.customers.tasks.expire_stale_topup_attempts",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    "reconcile-wallet-balances": {
        "task": "apps.platform.customers.tasks.reconcile_wallet_balances",
        "schedule": crontab(minute=0, hour="*/1"),  # Every hour
    },
    "cleanup-webhook-events": {
        "task": "apps.billing.stripe.tasks.cleanup_webhook_events",
        "schedule": crontab(minute=0, hour=3),  # Daily at 3 AM UTC
    },
    "close-tenant-billing-periods": {
        "task": "apps.tenant_billing.tasks.close_tenant_billing_periods",
        "schedule": crontab(minute=0, hour=0, day_of_month=1),  # 1st of month 00:00 UTC
    },
    "generate-tenant-platform-invoices": {
        "task": "apps.tenant_billing.tasks.generate_tenant_platform_invoices",
        "schedule": crontab(minute=0, hour=1, day_of_month=1),  # 1st of month 01:00 UTC
    },
    "reconcile-tenant-billing-periods": {
        "task": "apps.tenant_billing.tasks.reconcile_tenant_billing_periods",
        "schedule": crontab(minute=0, hour="*/1"),  # Every hour
    },
    "reconcile-missing-receipts": {
        "task": "apps.billing.invoicing.tasks.reconcile_missing_receipts",
        "schedule": crontab(minute=30, hour="*/1"),  # Every hour at :30
    },
}

# UBB Platform Settings
UBB_ARREARS_DEFAULT_THRESHOLD = int(
    os.environ.get("UBB_ARREARS_DEFAULT_THRESHOLD", "5000000")
)
UBB_INVOICE_PERIOD_DAYS = int(os.environ.get("UBB_INVOICE_PERIOD_DAYS", "7"))
UBB_PLATFORM_FEE_PERCENTAGE = float(
    os.environ.get("UBB_PLATFORM_FEE_PERCENTAGE", "1.0")
)

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {"()": "core.logging.CorrelationIdFilter"},
        "redacting": {"()": "core.logging.RedactingFilter"},
    },
    "formatters": {
        "json": {"()": "core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation_id", "redacting"],
        },
    },
    "loggers": {
        "apps": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "core": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "api": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "django.request": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "stripe": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "celery": {"level": "INFO", "handlers": ["console"], "propagate": False},
    },
    "root": {"level": "WARNING", "handlers": ["console"]},
}

# Stripe
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# CORS
_cors = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()]
CORS_ALLOW_CREDENTIALS = True

# Security headers
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
