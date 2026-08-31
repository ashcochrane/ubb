# Metering

Usage recording, cost/margin tracking, and the pricing engine — *what happened, what it
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
The upstream cost of the usage, in micros — caller-supplied or summed from the rules in a cost book.
_Avoid_: "our cost" — this is what the upstream provider charged.

**Billed cost**:
What the customer is charged, in micros — from a matching pricing rule, else the markup rung, and
**`NULL` where neither answered** (#351, #356). `pricing_status` beside it says which. Those are the
only two sources: a caller cannot state one on the call, and since #365 a request carrying one is
refused rather than ignored.
_Avoid_: treating this as the symmetric twin of provider cost. **Cost is observed and price is
decided** — a caller may report what their supplier charged them, because that is an external fact
they saw, but what the tenant charges their own customer is a commercial decision UBB resolves and
holds. Do not reintroduce a per-event price field for convenience, under any name; #151 §9.2 records
that it will be re-proposed precisely because it is small and looks helpful. **The refusal is a set
assertion, not a deleted field** — `test_a_customer_price_comes_only_from_configuration.py`'s
`TheRequestCarriesNoAmountTheCallerDecidesTest` asserts that every amount the request carries is a
cost, so a price arriving under *any* new name turns it red with the argument in the docstring above
it. That is why this rule needs no ADR: the proposal cannot land quietly.

**pricing_status**:
Whether the customer price for a subject is settled, and if not, why not — the four ratified values
sitting beside the amount, so a `NULL` is never read as a zero. `known` is resolved. **`waived` is a
decision somebody made** — a margin rule with no supplier cost to take a margin over. **`unknown` is
information UBB does not have** — nothing matched and there is no markup rung. `not_applicable` is a
subject that generates no customer revenue at this level at all. The distinction between the middle
two is what a Resolution Run is built on: it repairs what UBB is missing and never touches what
somebody decided.
(`apps/metering/usage/models.py:Posting.pricing_status`; the cost half is `costing_status`, whose
`unresolved` value is the pair's equivalent)
_Avoid_: rendering any of the three non-`known` values as an amount — `unknown` must never render as
`£0.00`; and reading `waived` as a kind of missing — the whole point of the pair is that it is not.

**not_applicable_reason**:
Why a subject generates no customer revenue at this level, read **only** where `pricing_status` is
`not_applicable` and never on its own — a status saying a price does not apply without saying why
sends a reader looking for a number nobody wrote. Two mutually exclusive causes:
`fixed_task_pricing`, where the event belongs to a Task sold for one agreed price so the revenue is
the Task's; and `tenant_not_billing`, where the tenant meters and does not bill through UBB at all.
**Where both are true, POSTURE WINS** — a metering-only tenant is `tenant_not_billing` whatever the
work's regime, because the concept answers *why no CUSTOMER REVENUE arises* and for that tenant none
ever does, for a reason unrelated to how the work was sold. ⚠ The argument slice 4 recorded was that
*no Charge exists anywhere* for such a tenant; #416 made that false — a metering-only tenant's
delivered fixed-price work does produce a Charge, as a recorded revenue and margin fact rather than
a collection — so the ruling stands on the narrower ground stated here and the ticket that wires the
rule up should re-read it.
Coined and declared by slice 4 (#151 §17 owed it and nothing had ratified it). Its console consumer
is `apps/ui/src/lib/customer-price.ts`, not the legacy label adapter its four neighbours live in.
(`apps/metering/usage/models.py`; `apps/metering/pricing/tests/test_why_a_price_does_not_apply.py`)
_Avoid_: adding a third value without deciding its tie-break against these two — the pair is closed
and the posture rule only works because there are exactly two.

**Margin**:
Realized `billed_cost − provider_cost`, computed on read and never stored.
_Avoid_: conflating margin (the realized per-event difference) with markup (the configured rule).

**Markup**:
The percentage a tenant declares over what a call cost it, applied where no pricing rule matched — the
last rung of the ladder, and the path that produces most prices. A tenant declares one rung and may
withdraw it; **UBB seeds none**, so a tenant that has declared nothing has NO rung and its unruled
events resolve to `unknown` with no amount — never to zero and never to the supplier's own figure
(#356). A rung declared AT zero is a different thing: it is the tenant saying *charge exactly what the
call cost*, and it settles. It is the ladder's ONLY markup rung: #369 deleted the record that held a
customer's own override and the plan catalog's percentage column, and what replaced each is a rule in
a Pricing Book rather than a percentage on a configuration row.
(`apps/metering/pricing/models.py:TenantDefaultMarkup`)
_Avoid_: reading an absent rung as a zero one — that is the silently wrong price this slice deletes;
and calling the percentage a "margin", which names only the derived figure above.

**Markup provenance**:
Which rung supplied a percentage and which record held it, recorded on the Pricing Receipt beside the
percentage itself (#357). The percentage rides BY VALUE and the record only as a pointer, because a
markup record can be edited or withdrawn and the receipt is what a tenant shows a customer.
(`apps/metering/pricing/services/markup_service.py:ResolvedMarkup`)

## Pricing — the books, the rules and the ladder

**Rate**:
A single priced *line* — one measurement key's rate for a combination of the ten declared selector
columns — living in a book, versioned via `lineage_id`. An empty selector is a wildcard; among the
rates that match, the most-pinned (highest `specificity`) wins, **whichever book it came from**
(#356). It points at a **Pricing Book or a cost book, never both**, which is what makes its kind a
fact the database holds rather than a word a writer copied (#368;
`ck_rate_sits_in_at_most_one_book`).
(ADR-0005 clause 8, superseded; `apps/metering/pricing/models.py:Rate`)
_Avoid_: assuming a rule in any book at all can be reached — resolution reads only the books in play
for that event, and a rule in a book nobody selected is unreachable however well it matches;
expecting a rule to say which kind it is — read the book it is in.

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

**Pricing Book**:
The versioned container of what this tenant **charges** — many Rates, one of which may be the
tenant default. It is pinned to **neither a supplier nor a currency**: a tenant's price for a unit
of work does not change because they switched supplier, and a tenant has exactly one currency
(CUR-1), so a column repeating either was a copy of a decision made elsewhere. A book carrying a
customer is that customer's override book. (#368; `apps/metering/pricing/models.py:PricingBook`)
_Avoid_: "rate card" or "price card" — the container is a Pricing Book; expecting it to name a
provider — a rule that should price one supplier's work differently pins `provider` as a selector,
which is where that distinction belongs.

**Work-level price line**:
The SECOND kind of line a Pricing Book holds (#415): what one whole delivered unit of work of a
named kind sells for, as one agreed number. A Rate prices a measured QUANTITY; this prices a whole
piece of work, and the two are lines in the same book so a tenant has one place to look and one
place to change. It names a DECLARATION — `(kind, task_type)`, the identity `work.TaskType` gives
itself — rather than a bare word, which is what lets a line written against contained work be
refused at start while leaving a priced kind of work free to run as a step of ITSELF.
**The ladder inside a book is one step, not three**: a Rate's exact-then-broader-then-default ladder
is about events, and there is no narrower work-level line to out-rank a broader one and no book-wide
fallback beneath either. What ranks is which BOOK the line came from — the customer's own beats one
merely selected for them — and `valid_from` breaks the remaining tie.
It carries **no currency**, on the Pricing Book's own argument one line up.
(`apps/metering/pricing/models.py:TaskPrice`;
`pricing/services/pricing_service.py:resolve_the_agreed_price`)
_Avoid_: expecting a route to write one — prices are edited through the book's declare-then-publish
act and nothing writes this table yet, which the model records as a named residual rather than an
oversight; and reading it as a floor or a fee on top — an agreed price REPLACES metered revenue for
that unit of work.

**Charge**:
What one delivered piece of work sold at one agreed price is owed for, once and immutably (#416).
Only an explicit close DECLARING DELIVERY earns one; failed, cancelled, killed and expired earn
nothing, so exposure on work that did not deliver is bounded by the COGS ceiling the tenant chose.
It carries the work, the amount, **its own currency**, the line that answered and the book version
that held it, the resolution instant and the charge instant, a key DERIVED from the work rather than
supplied by a caller, and the ten Grouping Field values the work carried.
**It is offered to both postures and means something different in each**: for a tenant that bills
through UBB it is a real billable record, and for one that meters only it is a recorded revenue and
margin fact. No gate in the tree can tell those apart, which is why the second has its own test.
**Dated at delivery**, so delivered work is always billable — the accepted consequence being that
work crossing a month boundary has its cost in the earlier period and its revenue in the later one,
which the resolution instant on the row is what keeps margin exact through.
Every economic column is `FROZEN` and a trigger holds it, so **a correction is a compensating record
naming the one it corrects, never an edit** — the original still says what UBB originally charged.
(`apps/metering/pricing/models.py:Charge`;
`pricing/services/charge_service.py`; `pricing/migrations/0031`)
_Avoid_: reading the price pinned on the work as this record — that is the DETERMINATION, which is
mutable, carries no currency, and may exist and never become a charge; and expecting a posting —
the projection onto the rails is a later ticket's and is a projection OF this row.

**Cost book**:
The versioned container of what **one supplier charges this tenant** — pinned to that supplier and
to the currency they bill in, the currency being a DECLARED value the database refuses to leave
empty (`ck_cost_book_names_its_currency`). `provider_key = ""` is a stated value and means the book
applies whatever the supplier, which resolution reads alongside that supplier's own book. (#368;
`apps/metering/pricing/models.py:CostBook`)
_Avoid_: "cost card"; treating it as the same entity as a Pricing Book under a different label —
they are separate tables with different columns, which is the whole of what the split bought, and
nothing selects between them at runtime.

**pricing_method**:
How a resolved pricing rule DERIVES a customer price — `margin_over_cost`, a margin applied over what
the call cost, or `direct_event_price`, a price attached to the event and answerable to no supplier
figure. **One method per rule, and a rule never composes**: a rule that wanted both would be two
rules, and a margin rule may not also carry a per-unit rate or a fixed addend. That is a property of
the ROW rather than a sentence in a comment — `ck_rate_pricing_method` closes the value set and a
second check refuses the composed shape (#355), because both are true of a row at every instant,
which is exactly what a check evaluates.
Two values and not the four #148 §4.4 sketched: the registry is the oracle, and neither dropped value
lost a distinction anything makes.
(`apps/metering/pricing/models.py:Rate.pricing_method`;
`apps/metering/pricing/tests/test_a_rule_declares_one_method_and_never_composes.py`)
_Avoid_: confusing it with `rate_structure` below, which says which ARITHMETIC produced the amount,
not where the amount's authority came from; and reading a customer override as changing a number
inside an inherited method — an override replaces the whole rule, method included.

**rate_structure**:
The arithmetic shape of a rate — `per_unit`, an amount for each unit of quantity, or
`fixed_component`, an amount that applies once regardless of quantity. `Rate.compute` branches on
it, so it is what decides which arithmetic produced an amount rather than a label beside one. Not to
be confused with `pricing_method`, the column beside it, which says how a price is DERIVED (a margin
over cost, or a price of its own); the two used to sit one character apart, which is the collision
ADR-0006 §3 names. (Two values and not four: the tiered shapes were deleted end to end by ADR-0003,
so the MVP launches without tiered pricing.)
_Avoid_: any name ending in the framework's own noun — ADR-0006 §7, and the reason this column was
renamed.

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

**The one way a book changes**:
A publish, and there is no longer a second. The three routes that wrote rules directly — one to add,
one to retire and the immediate reprice — are deleted, and the audit actions they recorded went with
them in the same commits, because `record()` refuses an unregistered name and a route still writing a
deleted action fails loudly (#367, #368). **So a rule cannot appear in a book with no publish record
behind it**, which is what makes a price in force at any past moment traceable to a decision somebody
made rather than nearly always traceable.
_Avoid_: reading a draft as an alternative route into the book — declaring and publishing are two
steps of one act, not two ways in.

**Reversing a publish**:
A further publish, effective at the same instant. Nothing is deleted and no row is reopened, so the
reversed rule ends up with an empty window `[T, T)` that resolves for no instant at all, and both
decisions stay on the record with their actors. The mechanism the pricing-versions decision wrote —
delete the pending rows and reopen their predecessors — is refused by the database, because
`Rate.valid_to` is `SET_ONCE` and reopening is a value-to-`NULL` write. **ADR-0009 carries the
argument**, including the two alternatives that look strictly better until you read what they cost:
re-deciding the column's mutability class, and deriving the boundary instead of storing it.
(#360; `apps/metering/pricing/tests/test_a_scheduled_publish_is_reversed_by_a_further_publish.py`)
_Avoid_: calling it a cancellation — nothing is cancelled, a second decision is recorded; and
expecting an empty-window rule to be a defect — it is a rule that never took effect, said in rows.

**Customer override**:
One customer's own pricing rule, honouring a negotiated deal. It **replaces the whole rule it
inherits — its method, its terms and the selectors it pins — never a number inside one**, so a
customer on cost-plus and a customer on a flat price are both expressible and a rule can be read on
its own without tracing a chain (#151 §6). It lives in a Pricing Book carrying that customer, which
is what lets it be published, dated forward and reversed by exactly the machinery every other rule
uses; resolution reads that book at the ladder's customer's-own source. Declaring one and
withdrawing one are two governance acts with two registered audit actions, and both DECLARE a draft
— publishing it is what puts the deal in force.
(#361; `apps/metering/pricing/models.py:PricingBook.customer`;
`apps/metering/pricing/services/pricing_service.py:_override_book`)
_Avoid_: reading an override as an adjustment to the inherited rule — nothing is inherited into it,
so a body stating a price and no method opens a rule with no method rather than the inherited one's;
treating it as a substitute for a book — it is a rule at a rung *inside* resolution, and a customer
resolves a book besides; and expecting a withdrawal to revive anything — the rule the customer
inherits was there all along and simply stops being out-ranked.

**The inherited rule**:
What a customer would be charged for a rule if they had no override — the same ladder with their own
book taken out of the selection, which is what a client offers as the starting point when creating
one. A read, and the only caller that asks for it: every path that decides what a customer is
actually charged reads the whole ladder.
(#361; `apps/metering/pricing/services/pricing_service.py:the_rule_a_customer_inherits`)

**Pricing Receipt**:
The authoritative record of the ECONOMIC RESOLUTION behind one posting's amounts — what UBB
resolved, how, and as of when. Values are authoritative and pointers ride along: the costing and
pricing sections carry their method, status and detail BY VALUE, and the `provenance` section
carries cross-reference ids that nothing reads to reconstruct an amount. It is **not** a guarantee
that customer revenue exists and not evidence a customer was charged — a metering-only tenant has a
receipt for every event it records and bills nobody through UBB.
The record had three names and #370 settled them. This one is what the registry ratified, as
`pricing_receipt_subject_type`; the stored column's older spelling is a retired alias on that
concept and is not written here; and so is "audit trail", which is the name **this entry itself
used** until #370 and which already names the governance ledger the platform keeps
(`apps/platform`'s audit log). Two things sharing one word was the defect. The bare word
`provenance` survives — but only as the section name above.
(`apps/metering/pricing/receipts.py`; the column is `Posting.RECEIPT_COLUMN`, which is how
everything addresses it and why the rename reached its callers without touching one.)
_Avoid_: reading "pricing receipt" as "UBB charged my customer" — the qualification above is the
whole difference between a record a metering-only tenant trusts and one they raise a support ticket
about, and it belongs on the concept, on the schema description and in the console's own words;
rewriting a historical receipt written under the older spelling — old receipts are read, never
rewritten, and the cutover squash is what eventually removes the two spellings, not this work.

## Putting a resolution right

**Resolution Run**:
The one mechanism for completing what UBB could never resolve at the time — a supplier cost that
never arrived, a customer price no rule was written for. **Membership is the status itself**, built
from the pairs that name *not learned*, so a run cannot touch a number that already exists; take
every axis of its selector away and that is still true. It re-resolves each posting **at that
posting's own instant**, so only configuration carrying no effective moment of its own can change the
answer — the markup rung, a Plan, an Event Type's declarations — and nothing anywhere backdates a
rule. `waived` is outside it by that same construction. A run declares a selector on three axes (a
date range, a customer, an Event Type) and never an arbitrary predicate; **an ADMIN floor**, because
the completion is irreversible under the receipt's sealing rule and money-adjacent; and it is
idempotent, so running it twice answers an outcome rather than a refusal.
(#363, **ADR-0010**; `apps/metering/pricing/models.py:ResolutionRun`,
`apps/metering/pricing/services/resolution_run.py`)
_Avoid_: adding a guard above it for "nothing to do" — that turns the second call into an error
forever while every acceptance criterion still reads as satisfied; and building a fourth recovery
mechanism — four documents each described one and none owned building it, which is what ADR-0010
exists to stop happening a fifth time.

**Projected adjustment**:
What recovering a filter would be worth, per customer, with the receipts behind it — the run's own
arithmetic with the writing taken out. **It is a projection and not an instruction.** No invoice,
credit note, charge or refund follows from reading it, and UBB will not bill anybody for it: Stripe
owns the billing engine and a UBB-owned adjustment surface would be reimplementing it. The response
carries that sentence itself (`queries.PROJECTED_ADJUSTMENT_BASIS`) rather than leaving it to a
comment, because a projection read as a receivable is the failure mode. The figure is a floor and
says so — what it could not value, and what one pass did not reach, are counted beside it.
(#364, **ADR-0010**; `apps/metering/queries.py:get_projected_adjustment`)
_Avoid_: adding the supplier-cost half into the figure — learning what a call cost is not money a
tenant can go back to a customer for; and reporting waived charges here — what waiving has cost is
`get_waived_loss`, taken over supplier cost, because a waived charge never carried a price to forgo.

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
