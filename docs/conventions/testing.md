# Testing conventions

Stack: **pytest + pytest-django + factory_boy** against **real Postgres and real Redis** (not
LocMemCache — gating/budget tests need cross-process cache semantics). Run everything from
`ubb-platform/`.

## Running

- Full suite: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest`
  (`DJANGO_SETTINGS_MODULE` is also set in `pytest.ini`, so bare `.venv/bin/python -m pytest` works.)
- The boundary gate: `.venv/bin/python -m pytest apps/platform/tests/test_product_boundaries.py`
- CI (`.github/workflows/ci.yml`) runs the suite on every push and PR — Python 3.13, from
  `requirements.lock.txt`, with `postgres:16` + `redis:7` services. Keep it green.

## Layout

- Tests live in `apps/<app>/tests/test_*.py` (and nested module dirs, e.g.
  `apps/platform/customers/tests/`). No top-level `tests.py`.
- Shared setup helpers live in `tests/_helpers.py` next to the tests that use them (e.g.
  `apps/metering/pricing/tests/_helpers.py:rate_in_default_book`). Reuse them rather than
  re-scaffolding tenants/customers/wallets by hand.
- DB tests are marked `@pytest.mark.django_db` (often on a `class TestXxx:` with `test_...` methods).

## Two non-obvious guards (in the root `conftest.py`)

1. **Redis DB 15.** The suite is moved onto Redis DB index 15 so `cache.clear()` / `FLUSHDB` in
   gating/budget tests never touches app or Celery-broker data (DB 1). Don't hardcode a different
   index in a test.
2. **Stripe network guard (autouse).** A sentinel key is forced and **any un-mocked Stripe network
   call raises `AssertionError`** naming the test. So: mock Stripe explicitly, or your test fails
   loudly rather than silently hitting `api.stripe.com`. The one deliberate exception is the
   live-AR test, gated by the `UBB_STRIPE_LIVE_TEST` env / `test_live_stripe_ar` node — leave it
   skipped by default.

## What good tests here look like

- **Exercise real behavior end-to-end**, not mocks of your own code: record a usage event through
  `UsageService.record_usage`, then run the billing handler, then assert the wallet ledger — the way
  `apps/billing/tests/test_tiered_drawdown.py` does.
- **Assert invariants**, since so much of this domain is money and idempotency: marginals sum to the
  closed form, a redelivered event debits exactly once, a zero-marginal event never touches the
  wallet, a stale run gets reaped. Prefer an invariant assertion over a single golden value.
- **Money in micros**, as integers, everywhere in fixtures and assertions.

## "Done" means

Full suite green **and** `.venv/bin/python manage.py check` clean **and** any needed migrations
generated (`makemigrations`) and committed. A behavior change that adds or moves a hard rule should
add or extend the test that enforces it (the boundary ADR is the model: the rule and its test change
in the same commit).
