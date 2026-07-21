# UBB — Agent Orientation

Usage, spend-control, and margin infrastructure in front of Stripe. **UBB owns** metering,
real-time spend control, provider/billed-cost tracking, customer margin, and (for billing tenants)
prepaid credit drawdown / period-close Stripe line-item push. **Stripe owns** invoicing, payment
collection, tax, dunning, portal, refunds, disputes, and subscription/seat lifecycle.

This directory (`ubb/`) is the git root; the Django project is `ubb-platform/`. Full positioning:
`docs/architecture/positioning.md`.

## The golden rule — read before changing any product

Four products — **metering, billing, subscriptions, referrals** — sit on a shared platform kernel
(`apps/platform` + `core/`). Products communicate ONLY via four named channels:

1. **Outbox events** — `apps.platform.events.outbox.write_event` + the handler registry (async default).
2. **`queries.py` read contracts** — module-level functions returning plain data, never ORM objects
   (`apps/metering/queries.py`, `apps/billing/queries.py`).
3. **`ports.py`** — an explicit call surface one product exposes to one other
   (`apps/subscriptions/ports.py`, consumed by billing).
4. **Platform hooks** — `apps/platform/customers/hooks.py`, for synchronous lifecycle reactions.

Enforced in CI by `apps/platform/tests/test_product_boundaries.py` — an AST walker that catches
lazy function-body imports too. Full matrix + rationale:
`docs/architecture/2026-06-12-adr-001-product-boundaries.md`. The composition layer (`api/v1`,
`apps/*/api`) may import any product; products never import `api.*`.

Tenant billing modes (`Tenant.billing_mode`): `meter_only` · `prepaid` · `postpaid`.
Domain vocabulary: `CONTEXT-MAP.md` → per-product `CONTEXT.md`.

## Running the suite

From `ubb-platform/` (venv at `ubb-platform/.venv`):

- Full suite: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest`
- Boundary check: `.venv/bin/python -m pytest apps/platform/tests/test_product_boundaries.py`
- Migrations: `.venv/bin/python manage.py makemigrations` then `... migrate`
- Sanity: `.venv/bin/python manage.py check`
- Spec regen (after any API surface change): `.venv/bin/python scripts/export_openapi.py` —
  refreshes the committed `openapi/v1.json`, the single source of truth for the tenant surface
  (ADR-002; CI's drift/breaking/TS gates enforce it — see `openapi/README.md`)

Celery + the outbox drive async work; entry point is `config/settings.py`.

## Conventions

Coding standards, testing conventions, and Django patterns live in `docs/conventions/` (grown
incrementally). Import discipline is the load-bearing one — see the golden rule above.

## The ratchet — keep this repo's docs from re-sprawling

When a plan or issue lands, **fold its lasting outcomes into the living docs**: the per-product
`CONTEXT.md` glossary (via `/domain-modeling`), an ADR in `docs/adr/` for a genuinely
hard-to-reverse decision, or `docs/conventions/`. **Prefer backing any hard rule with a test, as
ADR-001 does.** Dated docs under `docs/plans/` and `docs/reviews/` are **frozen history** — read
them for "why we decided X", never edit them as current truth.

## Agent skills

### Issue tracker

GitHub Issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Multi-context: `CONTEXT-MAP.md` at the repo root points to one `CONTEXT.md` per product
(`ubb-platform/apps/<product>/CONTEXT.md`). ADRs live in `docs/adr/` (new) and `docs/architecture/`
(existing). See `docs/agents/domain.md`.
