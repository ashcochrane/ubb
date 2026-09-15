# Subscriptions

The Stripe subscription **control plane** — UBB drives the lifecycle (subscribe, seats, cancel,
pause, resume) as calls into Stripe and mirrors Stripe's resulting status/amount/period read-only —
plus per-customer **margin / unit economics**. Stripe stays the invoicing, collection, dunning, and
tax authority throughout. Code anchors are relative to `ubb-platform/`.

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
(`apps/platform/plans/models.py:Plan.pricing_version`)

## Plans & provisioning

**Billing plan**: moved to the platform kernel — see `apps/platform/CONTEXT.md` → Plans.
Subscriptions realizes a plan's *fee* axes as Stripe Prices; it does not own the plan.

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
The per-customer, per-month margin snapshot — revenue minus provider cost — with a gross margin and
an `is_unprofitable` flag. Revenue is three sources: the Stripe subscription accrual, tenant-supplied
revenue, and billed usage **only where the customer's resolved revenue mode is `billed`**. Each is
its own column, so a figure read off it can say which kind of money it is.
(`apps/subscriptions/economics/models.py:CustomerEconomics`)

**Cost accumulator**:
The per-customer, per-month running total of provider/billed cost and event count, incremented from
`usage.recorded`. (`apps/subscriptions/economics/models.py:CustomerCostAccumulator`)

**Revenue mode**:
A per-customer switch (`billed` vs `metered_only`) deciding whether billed usage counts as revenue
in the margin calc.

**Accrued subscription revenue**:
Pro-rated Stripe subscription revenue for a window, computed without touching invoices. ⚠ **It used
to be a sum of two sources under a name that admitted only one**, and the second — a per-customer
recurring amount the tenant collected elsewhere — landed in the same snapshot column as this one,
so no surface could say where a revenue figure had come from. Slice 7 (#496) split them: this term
is Stripe's alone, and the other is below.

**Tenant-supplied revenue**:
What a tenant that bills its customers somewhere other than UBB says it earned from one customer
over one period, stated per period with its own span, its own recognition method and its own source
reference. UBB neither created nor invoiced it and **no surface may present it as a Charge**; it is
admitted so that margin can be computed at the scope it was supplied at (#153 §3.2). It reaches the
margin under its own name, never the subscription figure's.
(`apps/subscriptions/economics/models.py:TenantSuppliedRevenue`)

**Recorded vs recognised**:
The two labelled views of a supplied figure. **Recorded** places the whole amount on the day its
record's period opens and is the default every surface falls back to — it invents nothing.
**Recognised** spreads it by the record's own recognition method, and only ever along time.
(`apps/subscriptions/economics/revenue.py:SuppliedRevenueService`)

**Unprofitable / provider-cost spike**:
The transition-guarded conditions that emit `customer.unprofitable` (below the margin floor
for N consecutive periods) / `provider.cost_spike` (a period-over-period cost jump).

**Resnapshot**:
Refreshing a prior month's margin snapshot after backfilled usage dirtied it, by consuming
metering's backfill-dirty-period markers once the accumulator has settled.

## Ports & events

**ports.py**:
The single surface billing may import (ADR-001) — it lets billing stamp/repair subscription AR rows
(payment-failed fast path, dead-letter repair) without reaching into the subscriptions ORM.
(`apps/subscriptions/ports.py`)

**Events**:
Consumes `usage.recorded` (cost accumulation); emits `customer.unprofitable`,
`provider.cost_spike`.
