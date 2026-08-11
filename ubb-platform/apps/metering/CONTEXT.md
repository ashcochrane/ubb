# Metering

Usage recording, cost/margin tracking, and the RateCard pricing engine — *what happened, what it
cost, and what it's billed at*. Present on every tenant. Code anchors are relative to
`ubb-platform/`.

## Usage

**Usage event**:
The immutable, append-only record of one metered occurrence for a (tenant, customer), carrying its
priced provider and billed cost; never updated or deleted once written.
(`apps/metering/usage/models.py:Posting`)
_Avoid_: treating a usage event as a mutable row.

**Recording core**:
The recording body (price → create → accumulate → stop-context tag → dirty marker →
`usage.recorded` → kill registration on its own `on_commit`); `record_usage` is a thin input
adapter over it. It was extracted when there were two lanes to keep from drifting; only one
lane remains, and the core stays because the seam is where a recording side effect belongs.
(`apps/metering/usage/services/usage_service.py:UsageService._record_core`)
_Avoid_: adding a recording side effect to the adapter rather than the core — the adapter's job
is to turn a request into a `RecordingInput`, nothing more.

**effective_at**:
When the usage economically *happened* — caller-suppliable, bounded by the tenant's backfill window
— as opposed to when it *arrived*.
_Avoid_: conflating "effective" (when it happened) with "arrival"/"created" (when we received it);
queries take an explicit `basis`.

**Stop context**:
The immutable, system-owned array a usage event carries when it landed past a stop — one entry per
limit (`task_limit` / `subtask_limit` / `customer_wide_stop` / `suspended` / `task_not_active`),
each naming the scope, the trip time, the stop episode (customer scope), and whether the event
*tipped* the limit (`arrived_after: false`) or arrived after it. Written once at record, inside the
recording transaction; never from tenant tags or metadata. Soft-floor crossings never tag events.
(`apps/metering/usage/services/stop_context.py`)
_Avoid_: back-writing it onto an existing event — it is set at creation and immutable with the row;
a value's meaning can be renamed later (`customer_floor` → `customer_wide_stop`,
billing-surface-correctness task 1) but the historical row itself never changes, so a reader keyed
on a single current string will silently under-count older events — key on scope/intent, not on an
allow-listed literal.

Note: `stop_context` used to carry a unit-scoped `crossed_floor_snapshot` verdict too — a per-task
copy of the tenant's wallet-floor default, raced against the task's own frozen balance snapshot.
Deleted (billing-surface-correctness, task 1): it was blind to mid-task top-ups and independent of
the customer's real floor. Do not reintroduce a unit-scoped floor check in
`apps/metering/usage/services/stop_context.py` — the durable drawdown lane's `customer_wide_stop`
customer-scope tag is the one correct signal for a wallet-wide fact; see **Task floor snapshot
(removed)** in `apps/platform/CONTEXT.md` for the full reasoning.

**Past-limit report**:
The per-customer answer to "exactly what was spent past the limit and why" in one call
(`GET /api/v1/customers/{id}/past-limit-report`): episodes — customer-wide stops from the signal
ledger's history, task/subtask limit kills, soft-floor crossed/cleared marker rows — each with the
tripping limit, trip/resume times, itemized tagged events, and totals per limit in both
denominations. (`api/v1/past_limit.py`)
_Avoid_: itemizing events under a soft-floor row — nothing is "past limit" under a soft floor;
allow-listing a specific customer-scope `limit` string when bucketing events — deny-list the one
value that is taggable but never an episode (`suspended`) instead, so a renamed-but-still-episodic
value (or a historical string predating a rename) is never silently dropped.

**Backfill**:
Recording usage with a past `effective_at` inside the tenant's backfill window. Reaching into an
already-invoiced month is refused (`billing_period_closed`).

**Backfill dirty period**:
A marker that a backfilled event landed in a prior calendar month, signalling that month's margin
snapshot must be recomputed; produced here, consumed by subscriptions.
(`apps/metering/usage/models.py:BackfillDirtyPeriod`)

**tags**:
Caller-supplied, free-form labels on a usage event — never grouped, never priced, unbounded and
undeclared by design. Grouping and pricing are the declared `Dimension` registry's job (ADR-0005),
not tags'. (`apps/metering/usage/models.py`)
_Avoid_: "group_keys" — renamed to `tags`; "dimensional tags" — dimensions and tags are now two
separate mechanisms, not one.

**Recording**:
Turning one reported use into a durable priced `Posting` — price, create, accumulate the task's
totals, debit the live counter, emit `usage.recorded`. There is exactly **one** way in:
`POST /api/v1/metering/usage` and its batch sibling, both of which adapt a request item onto
`UsageService.record_usage`. (`apps/metering/usage/services/usage_service.py:UsageService`)
_Avoid_: "ingest", "accept", "settle" and "raw event" — the two-step accept-then-settle intake path
(a staging table drained by a beat sweep) was deleted in slice 1, producer first and then consumer,
and nothing replaced it. Its per-item adapters (`record_sync_item` and friends) sit in
`api/v1/metering_endpoints.py` beside the routes, because the endpoints are their only caller; the
recording work itself stays in `UsageService`, and that is the line to hold — an endpoint module
may map a request item onto the service and classify its errors, never grow pricing, kill or
ledger logic of its own.

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
A single priced *line* — one metric's rate for a combination of the ten declared selector columns
— living in a RateCard, versioned via `lineage_id`. An empty selector is a wildcard; among rates
that match within one book, the most-pinned (highest `specificity`) wins. (ADR-0005;
`apps/metering/pricing/models.py:Rate`)
_Avoid_: calling a Rate a "rate card" — that name belongs to the container; assuming specificity
ranks across every book — it only ranks within the one book a resolution tier selected (ADR-0005).

**Selector**:
One of the ten indexed columns (`provider`, `event_type`, `task_type`, `subtask_type`,
`dim1`..`dim6`) that both `Posting` and `Rate` carry — the single vocabulary a `Dimension` is
declared into and a `Rate` is matched against. `""` means "not set" on an event and "matches
anything" on a Rate. (ADR-0005; `apps/metering/pricing/models.py:Rate.SELECTORS`)

**Specificity**:
How many of a Rate's ten selectors are non-empty (pinned) — the tie-breaker among rates matching
the same event *within one book*: most-pinned wins, ties broken by latest `valid_from`. Does not
rank across books — book tier is resolved first (ADR-0005). (`apps/metering/pricing/models.py:Rate.specificity`)

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
The event emitted on every recorded usage event — the backbone consumed by billing drawdown,
subscriptions economics, and referrals rewards.

**usage.refunded**:
Emitted after a refund record is created.
