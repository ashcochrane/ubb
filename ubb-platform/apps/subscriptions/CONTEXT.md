# Subscriptions

The read-only Stripe subscription **mirror** plus per-customer **margin / unit economics**. Stripe
owns subscription invoicing, collection, dunning, and lifecycle; UBB mirrors it for revenue
attribution and drives seat quantity. Code anchors are relative to `ubb-platform/`.

## Subscription mirror

**Subscription mirror**:
A read-only local reflection of one Stripe subscription; Stripe stays the source of truth and UBB
only reflects its status/amount/period. (`apps/subscriptions/models.py:StripeSubscription`)
_Avoid_: treating the mirror as authoritative over Stripe.

**Subscription invoice**:
A synced row per Stripe subscription invoice, tracked for revenue attribution and AR status.
(`apps/subscriptions/models.py:SubscriptionInvoice`)

**Axis**:
The kind of a subscription line — `access` (a fixed access fee, quantity 1) or `seat` (per-seat,
quantity = seat count). (`apps/subscriptions/models.py:CustomerSubscriptionItem.axis`)

**Grandfathered price**:
Because Stripe Prices are immutable, a fee edit mints a *new* Price; existing subscriptions keep
their old one unless explicitly migrated.
(`apps/subscriptions/models.py:TenantBillingPlan.pricing_version`)

## Plans & provisioning

**Billing plan**:
A tenant-defined template — an access fee plus a per-seat fee — with its provisioned Stripe
Product/Price ids per axis. (`apps/subscriptions/models.py:TenantBillingPlan`)

**Charge-ready**:
The precondition that a tenant has a connected Stripe account with charges enabled; provisioning and
subscribing refuse to run otherwise.

**Lifecycle verbs**:
`cancel` / `pause` / `resume`, wrapped around Stripe. Trials and coupons are deliberately Stripe's
job, not UBB's.

## Seats

**Seat**:
An `account_type="seat"` customer under a business; the live seat-roster count must equal the
business's billed seat quantity.

**Seat quantity sync**:
Pushing the full *live* seat count (never a delta) to Stripe on a roster change, bound to that
change's transaction commit. (`apps/subscriptions/orchestration/seats.py`)
_Avoid_: pushing deltas — always full state.

## Unit economics / margin

**Customer economics**:
The per-customer, per-month margin snapshot — revenue (subscription + usage-billed) minus provider
cost — with a gross margin and an `is_unprofitable` flag.
(`apps/subscriptions/economics/models.py:CustomerEconomics`)

**Cost accumulator**:
The per-customer, per-month running total of provider/billed cost and event count, incremented from
`usage.recorded`. (`apps/subscriptions/economics/models.py:CustomerCostAccumulator`)

**Revenue mode**:
A per-customer switch (`billed` vs `metered_only`) deciding whether billed usage counts as revenue
in the margin calc.

**Accrued subscription revenue**:
Pro-rated recurring revenue for a window — manual revenue profile + Stripe subscription nominal —
computed without touching invoices.

**Unprofitable / provider-cost spike**:
The transition-guarded conditions that emit `margin.customer_unprofitable` (below the margin floor
for N consecutive periods) / `margin.provider_cost_spike` (a period-over-period cost jump).

**Resnapshot**:
Refreshing a prior month's margin snapshot after backfilled usage dirtied it, by consuming
metering's backfill-dirty-period markers once the accumulator has settled.

## Ports & events

**ports.py**:
The single surface billing may import (ADR-001) — it lets billing stamp/repair subscription AR rows
(payment-failed fast path, dead-letter repair) without reaching into the subscriptions ORM.
(`apps/subscriptions/ports.py`)

**Events**:
Consumes `usage.recorded` (cost accumulation); emits `margin.customer_unprofitable`,
`margin.provider_cost_spike`.
