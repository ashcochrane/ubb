# Context Map

UBB is one Django project (`ubb-platform/`) partitioned into four product contexts on a shared
platform kernel. These boundaries are the ones specified in
`docs/architecture/2026-06-12-adr-001-product-boundaries.md` and enforced by
`apps/platform/tests/test_product_boundaries.py`.

Each per-product `CONTEXT.md` is a **glossary only** (no implementation detail) and is grown
lazily by `/domain-modeling` as terms are resolved — several are still to be written.

## Contexts

- [Platform kernel](./ubb-platform/apps/platform/CONTEXT.md) — tenants, customers, the
  events/outbox, runs, auth, locking, and the plan catalog (`apps/platform/plans/`). The shared
  kernel; anything may depend on it. (`core/` is its plumbing.)
  - [`apps/platform/event_types`](./ubb-platform/apps/platform/CONTEXT.md#event-type-catalogue) —
    the tenant's declaration surface for what it meters: the Event Type and its supplier, category,
    declared quantities and reported-cost mapping. In the kernel because metering rates against it,
    billing reads it, and the Code Builder generates from it.
  - [`apps/platform/grouping_fields`](./ubb-platform/apps/platform/CONTEXT.md#grouping-fields) — the
    per-tenant `GroupingField`/`GroupingFieldValue` registry: the single declared vocabulary for
    analytics grouping and rate selection, read by metering via `grouping_fields/queries.py`
    (ADR-0005).
- [Metering](./ubb-platform/apps/metering/CONTEXT.md) — usage recording, provider/billed cost,
  declared grouping fields, customer margin, and the RateCard pricing engine.
- [Billing](./ubb-platform/apps/billing/CONTEXT.md) — prepaid credit ledger, real-time spend gate,
  auto-top-up, period-close Stripe line-item push, and the Stripe connector kit.
- [Subscriptions](./ubb-platform/apps/subscriptions/CONTEXT.md) — seat / subscription unit
  economics.
- [Referrals](./ubb-platform/apps/referrals/CONTEXT.md) — the referrals product.

## Relationships — the only sanctioned cross-context channels (ADR-001 §3, §5)

- **Any context → Platform kernel**: direct import allowed (`apps.platform.*`, `core.*`).
- **Product ↔ Product — outbox events**: the async default. e.g. metering emits `usage.recorded`,
  consumed by subscriptions/billing; `balance.low` → billing auto-top-up.
- **Metering / Billing → any product — `queries.py`**: plain-data read contracts. e.g.
  `apps/billing/queries.py:is_usage_period_closed()` is consulted by metering before it accepts a
  backdated `effective_at`.
- **Subscriptions → Billing — `ports.py`**: `apps/subscriptions/ports.py` (invoice payment-failed
  fast path + dead-letter invoice repair).
- **Platform → Product — hooks**: the `apps/platform/customers/hooks.py` registry; products
  register listeners in `AppConfig.ready()` for synchronous lifecycle reactions (e.g. seat-roster
  change → Stripe quantity push on the same transaction commit).
- **Billing → Subscriptions — Stripe connector kit** (named exception): `stripe.services`, the
  `StripeWebhookEvent` dedup table, and `connectors.stripe.invoice_routing` are shared Stripe
  infrastructure importable by subscriptions.
- **`api/v1` + `apps/*/api` → any product**: the composition layer wires products together;
  products never import `api.*`.
