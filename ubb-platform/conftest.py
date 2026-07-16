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
import pytest
from django.conf import settings


def pytest_configure(config):
    # Derive the test Redis URL by replacing the DB index with a dedicated
    # slot (default /15). UBB_TEST_REDIS_DB lets parallel local pytest
    # processes pick disjoint slots — cache.clear() is a FLUSHDB, so two
    # concurrent runs sharing one index would wipe each other's keys mid-test.
    import re

    base_url = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
    test_db = os.environ.get("UBB_TEST_REDIS_DB", "15")
    test_url = re.sub(r"/\d+$", f"/{test_db}", base_url)

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


@pytest.fixture(autouse=True)
def _stripe_guard(request, monkeypatch):
    """Force a sentinel Stripe key + block real Stripe network I/O.

    A missed mock.patch must fail loudly here instead of silently hitting
    api.stripe.com (a real key exported in the shell would win over the
    .env placeholder). The UBB_STRIPE_LIVE_TEST-gated module is the one
    deliberate exception.
    """
    if "test_live_stripe_ar" in request.node.nodeid:
        yield
        return
    import stripe

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_sentinel")
    monkeypatch.setattr(stripe, "api_key", "sk_test_sentinel")

    def _blocked(*args, **kwargs):
        raise AssertionError(
            f"Un-mocked Stripe network call in {request.node.nodeid}")

    monkeypatch.setattr(
        "stripe._api_requestor._APIRequestor.request_raw", _blocked)
    monkeypatch.setattr(
        "stripe._api_requestor._APIRequestor.request_raw_async", _blocked)
    yield
