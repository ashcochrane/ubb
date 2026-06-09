"""
Root pytest conftest.

Overrides the Redis/cache URL to DB index 15 during test runs so that
cache.clear() (FLUSHDB) in budget/gating/risk tests does not touch the
application or Celery broker data (DB 1).

Tests still use REAL Redis (not LocMemCache) because gating and budget tests
require cross-process cache semantics.  Only the database index changes.
"""
import os

import django
from django.conf import settings


def pytest_configure(config):
    # Derive the test Redis URL by replacing the DB index with /15.
    # The env-provided REDIS_URL may use any index; we want a dedicated slot.
    import re

    base_url = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
    # Replace the trailing /N (db index) with /15
    test_url = re.sub(r"/\d+$", "/15", base_url)

    # Only override if Django settings haven't been configured yet to avoid
    # interfering with a pre-configured test settings module.
    if not settings.configured:
        return

    # Patch CACHES and Celery URLs so every part of the test process uses DB 15.
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": test_url,
        }
    }
    settings.REDIS_URL = test_url
    # Keep Celery pointing at the same isolated DB so in-process task calls work.
    settings.CELERY_BROKER_URL = test_url
    settings.CELERY_RESULT_BACKEND = test_url
