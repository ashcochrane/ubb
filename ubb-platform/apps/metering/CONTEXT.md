# Metering

Usage recording, cost/margin tracking, and the RateCard pricing engine — *what happened, what it
cost, and what it's billed at*. Present on every tenant. Code anchors are relative to
`ubb-platform/`.

## Usage

**Usage event**:
The immutable, append-only record of one metered occurrence for a (tenant, customer), carrying its
priced provider and billed cost; never updated or deleted once written.
(`apps/metering/usage/models.py:UsageEvent`)
_Avoid_: treating a usage event as a mutable row.

**effective_at**:
When the usage economically *happened* — caller-suppliable, bounded by the tenant's backfill window
— as opposed to when it *arrived*.
_Avoid_: conflating "effective" (when it happened) with "arrival"/"created" (when we received it);
queries take an explicit `basis`.

**Stop context**:
The immutable, system-owned array a usage event carries when it landed past a stop — one entry per
limit (`task_limit` / `subtask_limit` / `customer_floor` / `suspended` / `task_not_active`), each
naming the scope, the trip time, the stop episode (customer scope), and whether the event *tipped*
the limit (`arrived_after: false`) or arrived after it. Written once at record (sync) / settle
(async) inside the recording transaction; never from tenant tags or metadata. Soft-floor crossings
never tag events. (`apps/metering/usage/services/stop_context.py`)
_Avoid_: back-writing it onto an existing event — it is set at creation and immutable with the row.

**Past-limit report**:
The per-customer answer to "exactly what was spent past the limit and why" in one call
(`GET /api/v1/customers/{id}/past-limit-report`): episodes — customer-floor stops from the signal
ledger's history, task/subtask limit kills, soft-floor crossed/cleared marker rows — each with the
tripping limit, trip/resume times, itemized tagged events, and totals per limit in both
denominations. (`api/v1/past_limit.py`)
_Avoid_: itemizing events under a soft-floor row — nothing is "past limit" under a soft floor.

**Backfill**:
Recording usage with a past `effective_at` inside the tenant's backfill window. Reaching into an
already-invoiced month is refused (`billing_period_closed`).

**Backfill dirty period**:
A marker that a backfilled event landed in a prior calendar month, signalling that month's margin
snapshot must be recomputed; produced here, consumed by subscriptions.
(`apps/metering/usage/models.py:BackfillDirtyPeriod`)

**Dimensional tags**:
Caller-supplied dimensions on a usage event (`product`/`service`/`agent` are reserved), used for
dimensional pricing matches and margin grouping. (`apps/metering/usage/models.py`)
_Avoid_: "group_keys" — renamed to `tags`.

**Async ingest / settle**:
The raw, at-least-once intake path: a raw event is accepted, then later *settled* exactly-once into
a durable priced usage event. (`apps/metering/usage/models.py:RawIngestEvent`)

**Estimate**:
The read-only arrival-time price reserved by a hold; never knowingly lower than what settle will
charge. Exact for caller-supplied, linear, and markup pricing.

**Settle sweep**:
The claim of pending raw events from the durable table itself — the accepted row *is* the queue
entry; the broker dispatch is only a doorbell, the beat sweep the guarantee.
_Avoid_: treating the broker message as the source of truth — a lost dispatch delays settlement,
never loses the event.

**Poisoned raw**:
A raw event that exhausted its settle attempts; parked `failed` with its hold released — an
operator incident, never a silent drop.

**Refund**:
A record linked one-to-one to a usage event, created only when billing emits `refund.requested`.
(`apps/metering/usage/models.py:Refund`)

## Cost & margin

**Provider cost (COGS)**:
The upstream cost of the usage, in micros — caller-supplied or summed from `cost` rate cards.
_Avoid_: "our cost" — this is what the upstream provider charged.

**Billed cost**:
What the customer is charged, in micros — from `price` rate cards when matched, else
`markup(provider_cost)`.

**Margin**:
Realized `billed_cost − provider_cost`, computed on read and never stored.
_Avoid_: conflating margin (the realized per-event difference) with markup (the configured rule).

**Markup**:
The configured uplift applied to provider cost to derive billed cost when no price card matches; no
markup configured → billed equals provider. (`apps/metering/pricing/models.py:TenantMarkup`)

## Pricing — the RateCard engine

**Rate**:
A single priced *line* — one metric's rate for a provider/event_type/dimension combination — living
in a RateCard, versioned via `lineage_id`. (`apps/metering/pricing/models.py:Rate`)
_Avoid_: calling a Rate a "rate card" — that name belongs to the container.

**RateCard**:
The versioned container (informally a "book") grouping many Rates, pinned to one provider +
currency; one may be the tenant default. (`apps/metering/pricing/models.py:RateCard`)
_Avoid_: "book"/"sheet"/"container" as the canonical name — it is `RateCard`.

**card_type**:
Whether a card derives provider cost (`cost`) or billed cost (`price`).

**pricing_model**:
The shape of a rate — `per_unit` or `flat`. (Tiered models — `graduated`/`package` — were deleted
end to end by ADR-0003: the MVP launches without tiered pricing.)

**lineage_id**:
The stable identity a Rate keeps across version supersessions, linking its whole price history.

**Pricing provenance**:
The audit trail stamped on each event — engine version, cost/price source, and rate-card ids.

## Read contract & events

**queries.py**:
Metering's plain-data read contract (period totals, revenue analytics, dimensional margin,
billing-owner billed total, backfill markers) — never returns ORM objects.
_Avoid_: importing metering models from another product; go through `queries.py`.

**usage.recorded**:
The event emitted on every recorded/settled usage event — the backbone consumed by billing
drawdown, subscriptions economics, and referrals rewards.

**usage.refunded**:
Emitted after a refund record is created.
