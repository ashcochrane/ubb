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

## Fixed date windows need explicitly-dated fixtures

A test that checks a **hardcoded date window** (e.g. `PS, PE = date(2026, 6, 1), date(2026, 7, 1)`)
must stamp the data it expects inside that window with **explicit dates inside the window** — never
rely on "now". `UsageEvent.effective_at` defaults to `timezone.now`, so an event created without it
lands wherever today happens to be: the test is green all June, then goes red on July 1 when the
clock leaves the window (this exact bomb took 27 tests red — issue #20). The idiom:

```python
PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
MID = timezone.make_aware(timezone.datetime(2026, 6, 15))  # explicit, inside [PS, PE)
UsageEvent.objects.create(..., effective_at=MID)
```

No freezegun/time-machine — pin the data, not the clock. There is no mechanical checker because the
rule needs judgment; the legitimate shapes are:

- **Fixed window + explicit in-window dates** — the default for billing/margin windowing tests.
- **Relative window + relative data** — e.g. `_prior_month()` plus an `effective_at` computed *from
  that window*; both move together.
- **Now-stamped data on purpose** — live-gate, drawdown, and arrival-basis tests genuinely test
  "now"; they must pair it with a relative or effectively-unbounded window, never a fixed one.
- Anything flowing through `UsageService.record_usage` is validated against the **rolling**
  `backfill_window_days` bound — a hardcoded past `effective_at` there is the same bomb inverted
  (it drifts out of the accept bound as time advances). Stamp relative to now on that path.

## What good tests here look like

- **Exercise real behavior end-to-end**, not mocks of your own code: record a usage event through
  `UsageService.record_usage`, then run the billing handler, then assert the wallet ledger — the way
  `apps/billing/gating/tests/test_budget_e2e.py` does.
- **Assert invariants**, since so much of this domain is money and idempotency: a redelivered event
  debits exactly once, accept-hold plus settle-delta nets to the exact price, a stale run gets
  reaped. Prefer an invariant assertion over a single golden value.
- **Money in micros**, as integers, everywhere in fixtures and assertions.

## "Done" means

Full suite green **and** `.venv/bin/python manage.py check` clean **and** any needed migrations
generated (`makemigrations`) and committed. A behavior change that adds or moves a hard rule should
add or extend the test that enforces it (the boundary ADR is the model: the rule and its test change
in the same commit).
