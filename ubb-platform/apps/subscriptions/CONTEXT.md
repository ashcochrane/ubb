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

**Customer economics** — **THE ALERTING RECORD, AND NOT A MARGIN RECORD** (#502, slice 7 §8):
The per-customer, per-month record the margin evaluator remembers with: an `is_unprofitable` flag,
the figures each flag was raised on, and the period before this one to compare against. Revenue is
three sources: the Stripe subscription accrual, tenant-supplied revenue, and billed usage — the
third for **every** customer since #497, because which postings carry customer revenue is a fact
each posting states (#147 §7) rather than one a customer-level setting could override. Each source
is its own column, so a figure read off it can say which kind of money it is.
**No reporting surface may read a margin figure from it**: margin is derived at read time from
postings, Charges and revenue records, and a closed period's reported cost and margin move when its
facts resolve — so a stored figure is a cache of facts that have since moved. The one door onto what
it remembers is `apps/subscriptions/economics/alerting.py`; the report is
`GET /metering/analytics/economics`.
(`apps/subscriptions/economics/models.py:CustomerEconomics`)

**Cost accumulator**:
The per-customer, per-month running total of provider/billed cost and event count, incremented from
`usage.recorded`. (`apps/subscriptions/economics/models.py:CustomerCostAccumulator`)

**Revenue mode** — **RETIRED, AND THE TERM IS NOT REPLACED** (#497, slice 7 §9):
A per-customer switch deciding whether billed usage counted as revenue in the margin calculation,
resolved from the tenant's billing mode wherever it was unset. It turned *"UBB does not raise this
customer's invoices"* into *"this customer produced no revenue"* — the inversion #141 §1.1's
governing invariant forbids — and it answered coarsely, per customer, a question #147 §7 answers
precisely per posting. **Nothing succeeds it**: ask the posting. `Posting.pricing_status` is
`known`, `waived`, `unknown` or `not_applicable`, and `not_applicable_reason` says which of the two
causes applies. The tenant-level posture that survives is `tenant_posture`, which is DERIVED from
the billing mode, never stored (ADR-0006 §4), and decides who invoices — and nothing more.

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
margin under its own name, never the subscription figure's. **It is the WHOLE revenue for the
customer and period it covers — authoritative, never added to** (#537): revenue derived from priced
usage inside that period is superseded, and unpriced usage there does not make the revenue
incomplete — in the one economic query, and in the alerting record and live margin that
`economics/services.py` composes, so the analytics and `is_unprofitable` state one revenue. The
period is the record's own span whatever basis is asked for; a figure with no period end covers
none. Figures that overlap are two facts: their amounts add and the usage is superseded once. A
Stripe subscription supersedes nothing.
(`apps/subscriptions/economics/models.py:TenantSuppliedRevenue`,
`apps/subscriptions/queries.py:supplied_revenue_covered_periods`)

**Recorded vs recognised**:
The two labelled views of a supplied figure. **Recorded** places the whole amount on the day its
record's period opens and is the default every surface falls back to — it invents nothing.
**Recognised** spreads it by the record's own recognition method, and only ever along time.
So under **recorded**, windows elsewhere in a figure's covered period may contain known zero
recorded revenue (#537); **recognised** is the view for revenue attributable across the period.
(`apps/subscriptions/economics/revenue.py:SuppliedRevenueService`)

**Unprofitable / provider-cost spike**:
The transition-guarded conditions that emit `customer.unprofitable` (below the margin floor
for N consecutive periods) / `provider.cost_spike` (a period-over-period cost jump).

**Resnapshot**:
Rebuilding a CLOSED month's two per-customer caches — the cost accumulator and the alerting record —
by consuming metering's dirty-period markers once the accumulator's dispatches have settled. The
accumulator is repaired from the posting ledger first, so a marker works **at any age**: the hourly
sweep covers three calendar months, and the marker channel covers everything older. **Caches
survive; authorities do not** — a marker is written by anything that can change the inputs, whether
that is usage backfilled into a prior month, a supplier cost settled long after the call, or a
figure the tenant supplied about a month that closed (#502).

## Ports & events

**ports.py**:
The single surface billing may import (ADR-001) — it lets billing stamp/repair subscription AR rows
(payment-failed fast path, dead-letter repair) without reaching into the subscriptions ORM.
(`apps/subscriptions/ports.py`)

**Events**:
Consumes `usage.recorded` (cost accumulation); emits `customer.unprofitable`,
`provider.cost_spike`.
