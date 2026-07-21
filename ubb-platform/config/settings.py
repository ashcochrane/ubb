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
    "apps.platform.membership",
    "apps.platform.events",
    "apps.platform.audit",
    "apps.platform.tasks",
    "apps.metering.usage",
    "apps.metering.pricing",
    "apps.billing.wallets",
    "apps.billing.topups",
    "apps.billing.stripe",
    "apps.billing.gating",
    "apps.billing.invoicing",
    "apps.billing.tenant_billing",
    "apps.billing.connectors.stripe",
    "apps.subscriptions",
    "apps.referrals",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.CorrelationIdMiddleware",
    # Clears the request-scoped audit actor at request end (see core/auth.py +
    # apps/platform/audit/actors.py). Wraps the view, so its reset runs after
    # auth captured the actor — the mirror of the correlation-id reset above.
    "core.middleware.RequestActorMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # #78: wrong-method 405s bypass the API's exception handlers — this
    # rewrites them onto the problem+json dialect (scoped to /api/v1/).
    "api.v1.problems.MethodNotAllowedProblemMiddleware",
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
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

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

# Cache (Redis-backed — required for cross-process rate limiting and dispatch caching)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

# Celery safety defaults
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 600          # 10 min hard kill
CELERY_TASK_SOFT_TIME_LIMIT = 300     # 5 min SoftTimeLimitExceeded
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000

from kombu import Queue

CELERY_TASK_QUEUES = [
    Queue("ubb_invoicing"),
    Queue("ubb_webhooks"),
    Queue("ubb_topups"),
    Queue("ubb_billing"),
    Queue("ubb_events"),
    Queue("ubb_economics"),
    Queue("ubb_subscriptions"),
    Queue("ubb_referrals"),
    Queue("ubb_metering"),
]

from datetime import timedelta

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "expire-stale-topup-attempts": {
        "task": "apps.billing.topups.tasks.expire_stale_topup_attempts",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    "reconcile-wallet-balances": {
        "task": "apps.billing.wallets.tasks.reconcile_wallet_balances",
        "schedule": crontab(minute=0, hour="*/1"),  # Every hour
    },
    "expire-credit-grants": {
        "task": "apps.billing.wallets.tasks.expire_credit_grants",
        "schedule": crontab(minute=10),  # hourly at :10
    },
    "cleanup-webhook-events": {
        "task": "apps.billing.stripe.tasks.cleanup_webhook_events",
        "schedule": crontab(minute=0, hour=3),  # Daily at 3 AM UTC
    },
    "close-tenant-billing-periods": {
        "task": "apps.billing.tenant_billing.tasks.close_tenant_billing_periods",
        "schedule": crontab(minute=0, hour=0, day_of_month=1),  # 1st of month 00:00 UTC
    },
    "generate-tenant-platform-invoices": {
        "task": "apps.billing.tenant_billing.tasks.generate_tenant_platform_invoices",
        "schedule": crontab(minute=0, hour=1, day_of_month=1),  # 1st of month 01:00 UTC
    },
    "reconcile-tenant-billing-periods": {
        "task": "apps.billing.tenant_billing.tasks.reconcile_tenant_billing_periods",
        "schedule": crontab(minute=0, hour="*/1"),  # Every hour
    },
    "reconcile-missing-receipts": {
        "task": "apps.billing.invoicing.tasks.reconcile_missing_receipts",
        "schedule": crontab(minute=30, hour="*/1"),  # Every hour at :30
    },
    "sweep-outbox": {
        "task": "apps.platform.events.tasks.sweep_outbox",
        "schedule": crontab(minute="*/1"),
    },
    "cleanup-outbox": {
        "task": "apps.platform.events.tasks.cleanup_outbox",
        "schedule": crontab(minute=0, hour=4),
    },
    "calculate-all-economics": {
        "task": "apps.subscriptions.tasks.calculate_all_economics_task",
        "schedule": crontab(minute=0, hour=2),  # Daily at 2 AM UTC
    },
    "reconcile-all-referrals": {
        "task": "apps.referrals.tasks.reconcile_all_referrals_task",
        "schedule": crontab(minute=0, hour=5),  # Daily at 5 AM UTC
    },
    "reconcile-topups-with-stripe": {
        "task": "apps.billing.connectors.stripe.tasks.reconcile_topups_with_stripe",
        "schedule": crontab(minute=20),  # Hourly at :20
    },
    "emit-referral-payouts": {
        "task": "apps.referrals.tasks.emit_referral_payouts_task",
        "schedule": crontab(minute=0, hour=4),  # Daily at 4 AM UTC
    },
    "close-abandoned-tasks": {
        "task": "apps.platform.tasks.tasks.close_abandoned_tasks",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
    "reap-stale-tasks": {
        "task": "apps.platform.tasks.tasks.reap_stale_tasks",
        "schedule": crontab(minute="*/5"),  # Tier-2 P5: every 5 minutes
    },
    "flush-api-key-last-used": {
        "task": "core.tasks.flush_api_key_last_used",
        "schedule": crontab(minute="*/5"),
    },
    "cleanup-webhook-delivery-attempts": {
        "task": "apps.platform.events.tasks_webhook_cleanup.cleanup_webhook_delivery_attempts",
        "schedule": crontab(minute=0, hour=3),  # Daily at 3 AM UTC
    },
    "reconcile-budget-counters": {
        "task": "apps.billing.gating.tasks.reconcile_budget_counters",
        "schedule": crontab(minute=15),  # hourly at :15
    },
    "reconcile-live-ledgers": {
        "task": "apps.billing.gating.tasks.reconcile_live_ledgers",
        "schedule": crontab(minute=25),  # hourly at :25 (free slot; D16)
    },
    "close-postpaid-usage-periods": {
        "task": "apps.billing.invoicing.tasks.close_postpaid_usage_periods",
        # 1st 00:05 UTC — INSIDE the renewal-draft window (F5.5 consolidation):
        # Stripe mints the subscription renewal draft at the 00:00 anchor and
        # auto-finalizes it ~1h later; a consolidated close must land between.
        "schedule": crontab(minute=5, hour=0, day_of_month=1),
    },
    "reconcile-postpaid-usage": {
        "task": "apps.billing.invoicing.tasks.reconcile_postpaid_usage",
        "schedule": crontab(minute=45),  # hourly at :45
    },
    "reconcile-usage-drawdowns": {
        "task": "apps.billing.wallets.tasks.reconcile_usage_drawdowns",
        "schedule": crontab(minute=40),  # hourly at :40
    },
    "reconcile-cost-accumulators": {
        "task": "apps.subscriptions.tasks.reconcile_cost_accumulators",
        "schedule": crontab(minute=50),  # hourly at :50
    },
    "resnapshot-dirty-periods": {
        "task": "apps.subscriptions.tasks.resnapshot_dirty_periods",
        # hourly at :55 — AFTER reconcile-cost-accumulators (:50) so the
        # accumulators the snapshots read are already ledger-corrected.
        "schedule": crontab(minute=55),
    },
    "reconcile-invoice-payment-status": {
        "task": "apps.billing.invoicing.tasks.reconcile_invoice_payment_status",
        "schedule": crontab(minute=15),
    },
    "settle-raw-events": {
        "task": "apps.metering.usage.tasks.settle_raw_events",
        # Straggler sweeper for the async ingest settlement path: the ingest
        # endpoint's on_commit dispatch is the primary trigger; this catches a
        # lost dispatch or a crashed worker mid-batch. Sub-minute cadence
        # (crontab has no seconds field) — a plain float/timedelta schedule.
        "schedule": timedelta(seconds=10),
    },
    "monitor-ingest-health": {
        "task": "apps.metering.usage.tasks.monitor_ingest_health",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
}

# UBB Platform Settings
UBB_MIN_BALANCE_DEFAULT = int(
    os.environ.get("UBB_MIN_BALANCE_DEFAULT", "0")
)
UBB_INVOICE_PERIOD_DAYS = int(os.environ.get("UBB_INVOICE_PERIOD_DAYS", "7"))
UBB_PLATFORM_FEE_PERCENTAGE = float(
    os.environ.get("UBB_PLATFORM_FEE_PERCENTAGE", "1.0")
)
# Postpaid push retry bound: both limits sit inside Stripe's 24h idempotency-key
# window so every automatic retry of usage-invoice-{id} keys stays a safe replay.
UBB_POSTPAID_PUSH_MAX_ATTEMPTS = int(os.environ.get("UBB_POSTPAID_PUSH_MAX_ATTEMPTS", "8"))
UBB_POSTPAID_PUSH_MAX_AGE_HOURS = int(os.environ.get("UBB_POSTPAID_PUSH_MAX_AGE_HOURS", "20"))
# Async-ingest ops (first-tenant hardening spec §3).
UBB_OPS_TOKEN = os.environ.get("UBB_OPS_TOKEN", "")  # unset => ops endpoint 404s
UBB_INGEST_SETTLE_LAG_WARN_SECONDS = int(
    os.environ.get("UBB_INGEST_SETTLE_LAG_WARN_SECONDS", "120"))
UBB_INGEST_QUEUE_DEPTH_WARN = int(
    os.environ.get("UBB_INGEST_QUEUE_DEPTH_WARN", "10000"))

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
STRIPE_CONNECT_CLIENT_ID = os.environ.get("STRIPE_CONNECT_CLIENT_ID", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
# Stripe TEST mode (sandbox tenants, F4.4). When STRIPE_TEST_WEBHOOK_SECRET is
# configured, the LIVE webhook endpoints reject livemode=False events (test
# traffic must use /webhooks/stripe/test); when unset, all-test dev setups
# (STRIPE_SECRET_KEY=sk_test_...) keep working unchanged.
STRIPE_TEST_SECRET_KEY = os.environ.get("STRIPE_TEST_SECRET_KEY", "")
STRIPE_TEST_WEBHOOK_SECRET = os.environ.get("STRIPE_TEST_WEBHOOK_SECRET", "")
STRIPE_CONNECT_TEST_CLIENT_ID = os.environ.get("STRIPE_CONNECT_TEST_CLIENT_ID", "")

# Clerk — tenant-member token verification (identity build 1, #79). All empty =>
# member auth is OFF and the API is API-key-only, byte-for-byte as before. A
# member token is verified SERVER-SIDE and offline (no Clerk call per request).
# Two mutually-exclusive modes, selected by which key is set:
#   * Production: CLERK_ISSUER + one RS256 key source — CLERK_JWKS_URL (fetched
#     + cached) or CLERK_JWT_PUBLIC_KEY (a PEM pinned in config). RS256 needs the
#     `cryptography` package (PyJWT's backend), installed at deploy time.
#   * Local/dev/test: CLERK_ISSUER + CLERK_HS256_SECRET. Real Clerk tokens are
#     never HS256, so this can never accept a live token; it exists only so dev
#     and the test suite can mint member principals without a JWKS round-trip. It
#     is ignored the moment an RS256 key is configured (RS256 wins).
# The Clerk session JWT must carry an `email` claim (a JWT-template custom claim)
# so a first login can be matched to a pending Member by email.
CLERK_ISSUER = os.environ.get("CLERK_ISSUER", "")
CLERK_JWKS_URL = os.environ.get("CLERK_JWKS_URL", "")
CLERK_JWT_PUBLIC_KEY = os.environ.get("CLERK_JWT_PUBLIC_KEY", "")
CLERK_HS256_SECRET = os.environ.get("CLERK_HS256_SECRET", "")

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
