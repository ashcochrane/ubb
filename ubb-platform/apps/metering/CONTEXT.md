# Metering

Usage recording, cost/margin tracking, and the RateCard pricing engine — *what happened, what it
cost, and what it's billed at*. Present on every tenant. Code anchors are relative to
`ubb-platform/`.

## Usage

**Posting**:
The immutable, append-only record of one metered occurrence for a (tenant, customer), carrying its
priced provider and billed cost; never updated or deleted once written. Renamed from the usage-event
noun with its table in #269 — it is an entry in the durable economic record, and it is what the
whole slice's vocabulary now hangs off. (`apps/metering/usage/models.py:Posting`)
_Avoid_: treating a posting as a mutable row. The published detail and list schemas still carry the
older noun; that is a contract surface a later slice moves, not a second concept.

**Posting measurement**:
What was measured on a posting — the child record, one-to-one with its parent, holding the detail
that may legitimately expire. Separate from the posting because two retention promises disagree by
years: the economic record is kept six years, bulky measurement detail prunes sooner, and as two
rows honouring both is a `DELETE` from here rather than a scheduled `UPDATE` against the system's
highest-volume table. **Absence is expressed by absence** — where a posting is a synthetic charge
there is no record here, not an empty one. (`apps/metering/usage/models.py:PostingMeasurement`)
_Avoid_: defaulting a child into being so that every posting can have one.

**Measurements status**:
Whether a posting's measurements are `available`, `pruned`, or `not_applicable` — **derived on read,
never stored**. It exists because a pruned posting otherwise reads exactly like one that never had
any: both answer an empty bag, so a consumer defaulting on emptiness renders a payload that expired
on schedule as a confident "no usage". The rule is the registry's, declared as `value_semantics` in
`domain-vocabulary/concepts/economics.yaml`; that no writable column of this name exists is gate
G10. (`apps/metering/usage/measurements.py:measurements_status_for`)
_Avoid_: reading it as analytics' `measure_status`. The near miss is accepted, not overlooked
(`economics.yaml` argues it against ADR-0006 §§2–3): `measure_status` says whether a NUMBER is
knowable at the grain asked for, this one whether the RECORD of what was measured is still there to
read a number from.

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
The immutable, system-owned array a posting carries when it landed past a stop — one entry per
limit (`task_limit` / `subtask_limit` / `customer_wide_stop` / `suspended` / `task_not_active`),
each naming the scope, the trip time, the stop episode (customer scope), and whether the event
*tipped* the limit (`arrived_after: false`) or arrived after it. Written once at record, inside the
recording transaction; never from the tenant's own metadata. Soft-floor crossings never mark events.
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

**Metadata**:
The ONE open bag on a posting: caller-supplied, free-form labelling — **filterable and readable,
never groupable** — unbounded and undeclared by design. Grouping and pricing are the declared
`GroupingField` registry's job (ADR-0005), never this bag's: an unbounded free-text keyspace that
can become a chart is one that can drive an invoice line label. Its keys are the tenant's own and
are stored and returned exactly as authored, never reworded into English nobody chose.
(`apps/metering/usage/models.py:Posting.metadata`)
_Avoid_: "group_keys" and the second bag's name, both retired — the second bag folded into this one
in #273 (slice 2) and its name went with the capability it advertised. Any phrasing that makes this
bag sound like a grouping axis: the declared registry and this bag are two separate mechanisms, and
only one of them can become a chart.

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
A record linked one-to-one to a posting, created only when billing emits `refund.requested`.
(`apps/metering/usage/models.py:Refund`)

## Cost & margin

**Provider cost (COGS)**:
The upstream cost of the usage, in micros — caller-supplied or summed from `cost` rate cards.
_Avoid_: "our cost" — this is what the upstream provider charged.

**Billed cost**:
What the customer is charged, in micros — from a matching pricing rule, else the markup rung, and
**`NULL` where neither answered** (#351, #356). `pricing_status` beside it says which.

**Margin**:
Realized `billed_cost − provider_cost`, computed on read and never stored.
_Avoid_: conflating margin (the realized per-event difference) with markup (the configured rule).

**Markup**:
The percentage a tenant declares over what a call cost it, applied where no pricing rule matched — the
last rung of the ladder, and the path that produces most prices. A tenant declares one rung and may
withdraw it; **UBB seeds none**, so a tenant that has declared nothing has NO rung and its unruled
events resolve to `unknown` with no amount — never to zero and never to the supplier's own figure
(#356). A rung declared AT zero is a different thing: it is the tenant saying *charge exactly what the
call cost*, and it settles. (`apps/metering/pricing/models.py:TenantDefaultMarkup`; the customer
override still lives on `TenantMarkup`, whose tenant-default row prices nothing and is deleted with
that record.)
_Avoid_: reading an absent rung as a zero one — that is the silently wrong price this slice deletes;
and calling the percentage a "margin", which names only the derived figure above.

**Markup provenance**:
Which rung supplied a percentage and which record held it, recorded on the Pricing Receipt beside the
percentage itself (#357). The percentage rides BY VALUE and the record only as a pointer, because a
markup record can be edited or withdrawn and the receipt is what a tenant shows a customer.
(`apps/metering/pricing/services/markup_service.py:ResolvedMarkup`)

## Pricing — the RateCard engine

**Rate**:
A single priced *line* — one measurement key's rate for a combination of the ten declared selector columns
— living in a RateCard, versioned via `lineage_id`. An empty selector is a wildcard; among the rates
that match, the most-pinned (highest `specificity`) wins, **whichever book it came from** (#356).
(ADR-0005 clause 8, superseded; `apps/metering/pricing/models.py:Rate`)
_Avoid_: calling a Rate a "rate card" — that name belongs to the container; assuming a rule in any
book at all can be reached — resolution reads only the books in play for that event, and a rule in a
book nobody selected is unreachable however well it matches.

**Selector**:
One of the fourteen columns (`provider`, `event_type`, `task_type`, `subtask_type`,
`grouping_field_1`..`grouping_field_10`) that both `Posting` and `Rate` carry — the single
vocabulary a `GroupingField` is declared into and a `Rate` is matched against. `""` means "not set"
on an event and "matches anything" on a Rate. Only the four reserved axes are indexed: the ten slots
carry no index of their own, because no query selects rows by one — every read of a slot groups by
it inside a tenant and time window (#276).
(ADR-0005; `apps/metering/pricing/models.py:Rate.SELECTORS`)

**Specificity**:
How many of a Rate's fourteen selectors are non-empty (pinned) — and **only that count** (#356). It
is one of the two ingredients the resolution ladder ranks on and says nothing about how they
combine: rules from every book in play compete in one ranking, specificity first and the source of
the rule as the tie-break inside a level, ties beyond that broken by latest `valid_from`. The
composite rule is stated once, at `ladder_rank`.
(`apps/metering/pricing/models.py:Rate.specificity`;
`apps/metering/pricing/services/pricing_service.py:ladder_rank`)

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

**PricingBookPublish**:
One change to a book, recorded once. Adding a rule, repricing one and retiring one are three kinds of
a single act, not three surfaces: a **draft** holds the intended changes and writes no rule, and
**publishing** is what closes each superseded rule and opens its replacement — both boundaries
written from the record's own effective instant, so with a half-open range there is exactly no gap
and exactly no overlap. Its two states are `declaration_status` ∈ `{draft, published}`, the closed
concept the registry already declared, and a published record is immutable: a trigger on its table
refuses every column, through `save()`, `QuerySet.update()` and raw SQL alike.
It carries its actor, its instant, its effective instant and the rule versions it opened and closed,
which is what makes a price in force at any past moment traceable to a decision somebody made.
(#358; `apps/metering/pricing/models.py:PricingBookPublish`,
`apps/metering/pricing/services/book_service.py`)
_Avoid_: reading a draft as a pending change to the book — it closes nothing, so discarding one
reopens nothing; treating a discard as an undo of a publish — the act that undoes a publish is a
further publish; and expecting anything to run at the effective instant — the rows are written when
the publish lands and the boundary is a value the resolver reads.

**The diff**:
What a declared change will do to the book, computed against the book **as it will stand at the
effective instant** rather than as it stands now. The two genuinely differ where the book already
carries a scheduled change, and the diff a tenant reads is the plan the publish executes — one
computation, not two that agree today.
_Avoid_: asking for the diff of a published record — it is a statement about a change that has not
happened, and what a published record did is the rule versions it names.

**The two ways a book changes**:
There are currently **two**, and only one of them leaves a record: the publish record above, and the
three immediate routes it replaces (`POST .../rates`, `DELETE .../rates/{rate_id}`,
`POST .../publish`), which still write rules directly. The immediate three and the three retired
audit action names they write are deleted by the ticket that retires the rest of this slice's
vocabulary; until then, a rule can appear in a book with no publish record behind it — and a draft
can be left stating a change one of those routes has since made impossible, which is why reading one
answers a reason rather than a diff.

**Pricing provenance**:
The audit trail stamped on each event — engine version, cost/price source, and rate-card ids.

## Read contract & events

**queries.py**:
Metering's plain-data read contract (period totals, revenue analytics, margin grouped by a declared
field via `get_dimensional_margin`, billing-owner billed total, backfill markers) — never returns
ORM objects. The function names still carry the pre-#155 noun; the rename is slice 7's, with the
row keys it serves.
_Avoid_: importing metering models from another product; go through `queries.py`.

**usage.recorded**:
The event emitted on every recorded posting — the backbone consumed by billing drawdown,
subscriptions economics, and referrals rewards.

**usage.refunded**:
Emitted after a refund record is created.
