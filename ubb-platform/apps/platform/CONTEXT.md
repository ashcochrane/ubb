# Platform Kernel

The shared kernel every product builds on: tenancy, customers, tasks, the event outbox, and the
cross-cutting money and identity primitives. Anything may depend on it; it never depends on a
product. Code anchors are relative to `ubb-platform/`.

## Tenancy

**Tenant**:
A UBB customer organization — the top-level isolation boundary every domain row is scoped to,
carrying its product set, billing mode, and Stripe linkage. (`apps/platform/tenants/models.py:Tenant`)

**Sandbox**:
A tenant's test-mode sibling that inherits its shape but never any real Stripe linkage, so
`ubb_test_` keys can only ever reach test-mode Stripe. (`apps/platform/tenants/models.py:Tenant.is_sandbox`)

**Product**:
An enabled product app on a tenant, drawn from the registry's `tenant_product` concept —
`{metering, billing, referrals}` — which the model imports as `core.vocabulary.TENANT_PRODUCT_VALUES`
rather than restating (#240). `metering` is always present. Two flags were retired rather than
renamed: `subscriptions`, because plans and subscription lifecycle gate on `billing`, and the
async-ingest sub-feature flag, which was never a peer product and went with the lane it switched
(slice 1, #149 §6). (`apps/platform/tenants/models.py:Tenant.products`)
_Avoid_: "module", "service" when you mean an enabled product; a behavior posture as a product entry
— products gate ACCESS (403s), and a posture is a column of its own.

**billing_mode**:
A tenant's revenue posture — `meter_only` (default), `prepaid`, or `postpaid`; `prepaid`/`postpaid`
require the billing product. (`apps/platform/tenants/models.py:BILLING_MODE_CHOICES`)

**enforcement_mode**:
The single Tier-2 spend-control switch on a tenant — two positions: `off` (byte-for-byte
pre-enforcement behavior) or `enforcing` (the full signal suite + state changes).
(`apps/platform/tenants/flags.py`)
_Avoid_: adding a second flag or reading `metadata` — this is the one switch; a middle
"compute but never act" mode — the one honest question is whether the signal suite is on.

**API key**:
A hashed, prefixed tenant credential; `ubb_live_` on live tenants, `ubb_test_` routed to the
tenant's sandbox at mint time. (`apps/platform/tenants/models.py:TenantApiKey`)

## Customers & seats

**Customer**:
A tenant's end-user — the entity that incurs usage and, for billing tenants, holds a wallet; keyed
by tenant-scoped `external_id` and soft-deletable. (`apps/platform/customers/models.py:Customer`)

**external_id**:
The tenant's own identifier for a customer, unique per tenant — UBB's public handle for it.
_Avoid_: exposing the internal UUID as the public handle.

**account_type**:
What a customer represents — `individual`, `business`, or `seat` (a member of a business).
(`apps/platform/customers/models.py:ACCOUNT_TYPE_CHOICES`)

**Billing owner**:
The customer whose wallet/card actually funds a given customer — the parent business for a pooled
seat, otherwise the customer itself; pinned at task creation and never re-resolved.
(`apps/platform/customers/models.py:Customer.resolve_billing_owner`)
_Avoid_: "payer", "account holder".

**billing_topology**:
On a business customer, whether its seats draw from a shared wallet (`pooled`) or self-fund
(`allocated`). (`apps/platform/customers/models.py:BILLING_TOPOLOGY_CHOICES`)

**Seat roster**:
The live set of seats under a business; adding/removing a seat is a roster change, broadcast
synchronously to registered listeners. (`apps/platform/customers/hooks.py`)

**Customer status**:
`active`, `suspended`, or `closed`. Only a monetary suspension auto-clears on recovery — a top-up
never silently un-suspends an admin/fraud suspension.

## Membership & identity

**Tenant principal**:
The authenticated caller on a tenant route — a tenant API key or a Clerk-verified
Member. Both carry a role and resolve to exactly one tenant, and both arrive as a
single `Authorization: Bearer` token distinguished by its contents, not a second
scheme. (`core/auth.py:ApiKeyAuth`)
_Avoid_: treating an end-customer (widget) token as a tenant principal — it never
reaches tenant management.

**Member**:
A person who administers a tenant — kernel identity beside tenants and customers,
not a fifth product and never a stored password (Clerk owns credentials). Created
`pending` at invite, flips to `active` on first Clerk login (matched by email,
then bound to the Clerk user id). The Member table is ours, so identity survives
Clerk being replaced. (`apps/platform/membership/models.py:Member`)

**Invitation**:
The first-class, Admin-managed record of an outstanding invite by email + role —
`pending`, then `accepted` when its Member activates or `revoked` by an Admin.
Revoking a pending invite drops its pending Member; un-inviting an *active* member
is member removal (`DELETE /tenant/members/{id}`, guarded — see Last-active-Admin
guard). (`apps/platform/membership/models.py:Invitation`)

**Role**:
A tenant principal's authority — `admin`, `write`, or `read`. No owner tier, no
fourth role (#62). Carried by both a Member and a `TenantApiKey`; every existing
key migrated to `admin`. (`apps/platform/membership/roles.py`)
_Avoid_: "owner"; conflating the Member entity with the member *role*; Clerk
organization roles.

**Role floor**:
The minimum role a route requires — Admin ≥ Write ≥ Read. Bound on **every**
tenant route via `@role_floor(...)` in the composition layer (the #74 carve:
every GET → Read *including money*, except the invitations list; Write = day-to-day
data ops + customer top-ups; Admin = changes the rules or moves money). Enforcement
lives in the composition layer's auth module so products never consume membership
directly (ADR-001); the machine check that each route matches the carve is
`api/v1/tests/test_role_floors.py`. (`core/auth.py:role_floor`)
_Avoid_: putting a floor check inside a product handler; documenting floors in the
OpenAPI security (they are runtime behaviour, spec-invisible).

**Last-active-Admin guard**:
A tenant must always keep ≥1 active Admin, so it can never lock itself out —
demoting or removing the last active Admin (the member role, not an API key) is
refused (`last_active_admin`, 409). Only *active* Admins count; a pending Admin
invite does not. (`apps/platform/membership/services.py:_guard_last_active_admin`)

**Member token**:
A Clerk session JWT presented as a bearer token, verified server-side and offline
(no Clerk call per request); must carry an `email` claim so a first login matches
a pending Member. Unconfigured Clerk => member auth is off and the API is
API-key-only, byte-for-byte. (`core/clerk_auth.py:verify_member_token`)

## Event Type catalogue

**Event Type**:
A tenant-declared metered call, and the aggregate root the catalogue hangs off: its key, one
optional supplier, one optional category, how its supplier COGS is derived (`costing_method`),
which provider response shape its declared paths are written against, and a declaration lifecycle
(`declaration_status`, with a published revision). It lives in the kernel because metering rates
against it, billing reads what it declared and the Code Builder generates an integration from it —
no one product owns it. It carries **no grouping axes, no cost amount, and no account record below
the supplier** — three absences held to the tree by
`apps/platform/tests/test_event_type_declaration_invariants.py` rather than asserted here.
Operational variants (a batch endpoint versus a standard one) are separate Event Types, because
averaging two genuinely different supplier costs produces a number wrong for both.
(`apps/platform/event_types/models.py:EventType`)
_Avoid_: treating the free-text event-type string on a posting as this record — an unrecognised
string is quarantined for later resolution, not silently declared.

**Provider**:
The supplier behind a call — a per-tenant record, optional on an Event Type. It is a record and not
a string because supplier cost resolution keys on its identity: a tenant may correct `key` without
re-attributing historical cost, which parsing the supplier out of an Event Type key would have made
impossible. Retired, never deleted — `retired_at` stops new use and leaves the past readable.
(`apps/platform/event_types/models.py:Provider`)

**Event category**:
An optional, tenant-defined grouping for Event Types. One level, current rather than
effective-dated, and **never a monetary input** — it cannot reach a cost or a price by any path,
which is what makes the absence of dating safe rather than merely cheap. It carries no `retired_at`,
deliberately: retirement earns its place on a supplier because a supplier is load-bearing for
historical money attribution, and nothing here is. An Event Type with no category is a normal one.
(`apps/platform/event_types/models.py:EventCategory`)

**Measurement (declared quantity)**:
One declared quantity beneath an Event Type — a code and display name, a value type, a unit, whether
its absence blocks a complete cost (`required_for_costing`), and where the number comes from (a
source kind plus a structured `source_path`). Before it, measured quantities travelled in a bare
JSON bag and **a misspelled quantity was silently free**: it hit a `continue`, contributed nothing,
and told nobody. Only a declared quantity may participate in monetary calculation. Declarations are
**Event-Type-local** — the same code on two Event Types is two independent records that happen to
share a spelling, which is the correctness boundary, not a duplication to be cleaned up.
(`apps/platform/event_types/models.py:Measurement`)
_Avoid_: giving this record an amount or a currency — a reported supplier cost is money with a
currency and is declared as a *sibling* of these, not as one of them.

**Measurement concept (analytics grouping)**:
Two quantities a tenant has **said** mean the same thing, so one chart may add a supplier's
`prompt_tokens` to another's `input_tokens`. **Opt-in and analytics-only**: it carries no amount, no
currency and no rate, and no rating, cost-resolution or spend-ceiling module can see it. Both fences
are about what a *name* may not decide — a matching spelling never automatically proves equivalence
(UBB cannot tell a genuine duplicate from a collision, and a wrong guess silently merges two
unrelated quantities on someone's chart), and a differing spelling never prevents aggregation.
(`apps/platform/event_types/models.py:MeasurementConcept`)
_Avoid_: confusing it with a grouping field — that binds a tenant key to a physical slot and reaches
rate selection; this one relates two declared quantities and reaches nothing but analytics.

## Grouping fields

**Grouping field**:
A bounded, declared slicing axis usable for both analytics grouping and rate selection — the
tenant's `GroupingField` registry is the single vocabulary for both, so nothing may be grouped by
or priced on that was not declared. Unlike a `metadata` value, a grouping field's keyspace is capped
on write. (ADR-0005; `apps/platform/grouping_fields/models.py:GroupingField`)
_Avoid_: the pre-#155 noun for this axis — the registry, its records and its columns all carry this
one now.

**Grouping field value**:
One distinct value ever admitted under a declared key, one row per (tenant, key, value). It is what
backs the cardinality cap and what the values route serves into a filter dropdown; retiring a key
never sweeps it, so a historical row stays groupable *and* still resolves.
(`apps/platform/grouping_fields/models.py:GroupingFieldValue`)

**Slot**:
The physical column (`grouping_field_1`..`grouping_field_10`) a declared key is bound to on
`Posting`, `Task` and `Rate` — immutable once set, since re-slotting would silently change the
meaning of every historical row in that column. Ten since #276, widened because #273 closed the
free-form grouping escape hatch and the demand has to arrive declared or not at all. The stored
identifier IS the column name, which is why rewriting it is a data migration and not a relabelling,
and why a declaration bound to a slot outside the declared ten is refused rather than stored.
The rate write surface publishes all ten since #366, under the column names, so a rule pinned on any
slot can be written and repriced through the API. It published six until then, which was a
*functional* gap rather than a spelling one: a reprice body left the other four empty, and empty is
what matches a rule leaving a slot unpinned, so a rule pinned on the seventh slot could be written
server-side and then matched by no publish body at all. (ADR-0005)

**Scope**:
The level at which a grouping field's value is constant — `task`, `subtask`, or `event` — governing
inheritance down the task tree; immutable once declared, since re-scoping would make old and new
rows disagree about where a value came from. (ADR-0005)

**Task type**:
A tenant's declared kind of work, carrying server-side policy (a COGS ceiling,
`required_dimensions`) rather than being a bare label; immutable on a `Task` once created. **One
column carries it at either altitude** — a `Task` and a `Subtask` declare their kind in the same
place and `Task.parent` is the only thing that says which altitude a row is at.
(ADR-0005, whose Decision clause on what a `Task` carries is superseded on exactly this point;
`apps/platform/work/models.py:TaskType`)
_Avoid_: a second name for the contained case. The column that carried one was collapsed into this
one; a Subtask is the same record with a parent, never a second pricing entity.

**Task type kind**:
`task | subtask` on the declaration, saying which altitude a declared kind of work is MEANT for —
the one thing a `Task`'s single type column cannot carry, and what lets a declaration be refused
when it is made rather than when it is used. It is part of the declaration's uniqueness key, so one
word may name a kind of work at either altitude and the two are different declarations with
different policy. (`apps/platform/work/models.py:TaskType.kind`; registry concept `task_type_kind`)

## Tasks

**Task**:
The registered unit of agent work — a tenant+customer-scoped grouping of many postings into
one logical workflow execution, registered at the start-gate; lives in the kernel so metering and
billing can both reference it without crossing a product boundary. Carries both running totals
(billed + provider, denominationally explicit) and its signal points. Status
`active | completed | failed | cancelled | killed | expired` — six states, held by import from the
generated registry, of which `active` is the only non-terminal one and **terminal to anything is
never permitted**. Each of the five is told apart by WHO WROTE IT, which is what lets a money
decision key on one: `completed` means the tenant declared delivery and nothing else may write it,
`killed` means UBB stopped the work on a spend signal and nothing tenant-declared may land there.
(`apps/platform/work/models.py:Task`; registry concept `task_status`)
_Avoid_: "run" (the pre-rename name), and the retired label-era "task" sense (a `metadata` value) —
the open bag is labelling only and never attaches a limit.

**Subtask**:
A parent-linked child unit of work — **the same record with a parent**, not a second model and not
a separate pricing entity: a task registered under an active top-level task, declaring its kind in
the same column its parent uses, with its own COGS limit and lifecycle. Its spend rolls up into the
parent's totals (the parent's cap covers everything underneath it); crossing its own limit kills it
alone (`subtask.limit_exceeded`) while the parent keeps running; a parent's stop cascades downward
to its active subtasks — never upward — and **what the cascade writes is not always what the parent
got**: a kill cascades `killed` and an expiry cascades `expired`, but a CLOSE cascades `cancelled`,
because the tenant declared the delivery of the parent and declared nothing about each contained
piece. Two altitudes and no third: deeper structure is a
task-scoped Grouping Field value, which is already inherited down the tree and already
cardinality-capped. (`apps/platform/work/models.py:Task.parent`)
_Avoid_: "child task", "nested task", and the retired label-era "task" sense.

**Task limit (provider-cost limit)**:
A task's COGS ceiling — denominated in provider cost (what the job burns), never billed markup;
passed at start or defaulted from tenant config, snapshotted at creation. Only the provider total
races it; crossing it is a signal point (kill + `task.limit_exceeded`), never a billing wall.
(`apps/platform/work/models.py:Task.provider_cost_limit_micros`)
_Avoid_: "hard stop" — that vocabulary retired with the 429.

**Killed (task)**:
**UBB stopped this unit on a spend signal, and that is all it ever means** — a ceiling crossing, the
patrol, or a parent's kill cascade. Nothing tenant-declared may land here, which is what keeps the
past-limit report, the stop context and the announcement bookkeeping honest and makes *how often do
we blow ceilings* answerable without filtering on a reason string first. Late events still land,
bill, and count into the killed unit's totals (and its parent's, for a subtask); the flip is the
durable record that the signal fired, not a wall. Killing a parent cascades the flip to its active
subtasks; killing a subtask kills it alone.
(`apps/platform/work/services.py:TaskService.kill_task`)
_Avoid_: reading it as "terminated" in general — the reaper's stop is an **Expired (task)**.

**Expired (task)**:
**Nobody ever told UBB how this ended.** Both sweepers write it: the >1h safety net for work the SDK
never closed, and the stale reaper for work that went silent or ran past the absolute age ceiling.
It replaces a state the model could not honestly give — the safety net used to write `completed`
with a marker in metadata and the reaper used to write `killed`, so one silence was recorded two
ways and neither state meant one thing. An expiry can strike a live unit doing long atomic work, and
that is **not** a failure and must not be counted as one.
(`apps/platform/work/services.py:TaskService.expire_task`)

**Cancelled (task)**:
Deliberately stopped or withdrawn. Today its only writer is a parent's CLOSE cascade over still-
active contained work; an explicit close declaring cancellation joins it when the close carries an
outcome. It deliberately does **not** map onto `killed`: the kill path announces on the winning
transition and stamps an announcement id, so a withdrawal landing there would either fire a spurious
spend event at the customer's workers or become the only `killed` row with no announcement — which
already means *silently cascaded by a parent*.
(written by the close cascade in `apps/platform/work/services.py:TaskService.complete_task`)

**Heartbeat**:
A task's most-recent-event timestamp; its absence past the stale window is what the reaper expires
on. (`apps/platform/work/models.py:Task.last_event_at`)

**Stop reason**:
The closed vocabulary of why a stop signal fired — `task_limit`, `subtask_limit`,
`task_not_active`, `customer_wide_stop`, `stale`, `stale_max_age`, plus the kill-metadata-only
`parent_killed` (the KILL cascade's flip, never on an ack or event) and the stop-context-only
`suspended` (an owner suspended with no open floor episode — taggable, but never an episode reason,
so it is NOT in this closed vocabulary's `CROSSING_REASONS`). One source of truth for every producer
and consumer; rides the ack's `stop_reason`, never an HTTP error.
(`apps/platform/work/reasons.py`)
_Note_: the metadata key is still spelled `kill_reason` and now carries an **Expired (task)**'s
reason too — `stale` / `stale_max_age` on a row that says `expired`. The rename is `outcome_reason`'s,
in the ticket that wires that concept's consumers; every consumer of the key gates on
`status == killed` first, so nothing mis-reads it meanwhile. The close and expiry cascades record no
reason at all yet: the registry names `outcome_reason: parent_closed` and `reason_code:
silence_window` for them, each owed by the same later tickets.
_Avoid_: `customer_floor` — the retired per-task floor snapshot's reason string (see
**Task floor snapshot (removed)** below); it can never be emitted by current code, though
immutable pre-removal `Posting.stop_context` rows may still carry it forever.

**Task floor snapshot (removed)**:
A per-task copy of the tenant's wallet-floor default, compared at every `accumulate_cost` call
against the task's OWN frozen balance snapshot — an independent third floor alongside the
customer's real floor and the postpaid budget. Deleted (billing-surface-correctness, task 1):
it read a tenant-wide constant, never the customer's own
`CustomerBillingProfile.min_balance_micros`, and compared against a balance frozen at task start,
so a mid-task top-up was invisible to it and it could kill a task for a customer who had just
paid. The durable drawdown lane already detects the real floor crossing and fires
`customer_wide_stop`, the correct scope for a wallet-wide fact — do not reintroduce a per-task
floor check independent of it.
_Avoid_: adding a new reader of `Task.balance_snapshot_micros` for a floor comparison — it is kept
only as forensics on the task record.

## Events

**Outbox event**:
A domain event written in the same atomic transaction as the change that produced it — if the
transaction commits the event is guaranteed, if it rolls back it vanishes. The default cross-product
channel. The post-commit Celery dispatch is a DOORBELL, not the queue: the durable row is the
queue, the minutely sweep re-dispatches lost doorbells, and a dead broker at dispatch is swallowed
+ logged (never an error for an event that durably landed).
(`apps/platform/events/models.py:OutboxEvent`, `apps/platform/events/outbox.py:write_event`)
_Avoid_: "message", "signal"; treating a `.delay()` failure as a delivery failure.

**Handler**:
A product's subscriber to an event type, registered in `AppConfig.ready()`, optionally gated by
`requires_product`. (`apps/platform/events/registry.py`)

**Payload schema**:
The frozen dataclass contract for one event type — both halves of the seam live on the base
class: producers construct (ids as `UUID | str`, normalized to str at construction) then
`asdict()` into `write_event` (which asserts the caller's open atomic block); consumers
`SchemaClass.from_payload(payload)` — unknown keys filtered, defaults applied from the class,
absent required fields loud. The webhook catalog (`catalog.WEBHOOK_EVENT_TYPES`) DERIVES from
the registry the base class builds, so adding the schema class IS adding the event type (two
edits: the class + the emit); a missing or duplicate `EVENT_TYPE` is an import-time error.
(`apps/platform/events/schemas.py:EventSchema`)
_Avoid_: hand-parsing `payload["…"]` / `.get(…, restated-default)` in handlers, or hand-building
payload dicts in tests — both re-encode the contract the class already owns.

**Retry horizon**:
The wall-clock from an event's first failed dispatch to dead-letter when every retry fails —
`RETRY_HORIZON` (= sum of `BACKOFF_SCHEDULE`, ~2h43m). Repair jobs that must outwait the outbox
before treating absence as loss (drawdown reconcile GRACE, resnapshot marker age) assert against
it instead of restating the arithmetic as prose. (`apps/platform/events/tasks.py`)

**Dead letter**:
An event that has exhausted its retries and been marked `failed` — alerted, never auto-deleted.

**Outbound webhook**:
A tenant's subscribed HTTP delivery of events to their own endpoint, HMAC-signed and stamped with
`livemode`. (`apps/platform/events/webhook_models.py:TenantWebhookConfig`)

**Per-endpoint delivery checkpoint**:
The successful `WebhookDeliveryAttempt` for an (event, endpoint) pair — a retry pass skips
checkpointed endpoints and re-POSTs only the still-failing pairs, and a failing endpoint never
aborts the pass for its neighbours (failures are collected, then raised as
`WebhookDeliveryIncomplete` after every endpoint was attempted). Each pair succeeds, retries, or
dead-letters independently. Retryable = network errors, timeouts, 5xx, 429; permanent for the
pair = 3xx/4xx, blocked URLs, non-network errors.
(`apps/platform/events/webhooks.py:deliver_webhook`)
_Avoid_: treating the event-level `HandlerCheckpoint` as the delivery guarantee — it is per
handler, not per endpoint.

## Audit

**Audit record**:
A durable, append-only, tenant-scoped entry answering "who did what, when, to which resource" —
actor snapshot + action name + target resource + timestamp + correlation id + curated metadata.
Written in the same transaction as the change (a rolled-back mutation leaves no row) and never
updated thereafter. A LEDGER, not a queue: rows are never processed, retried, swept, or aged out
(retention floor ≥ 1 year, raisable never lowerable). Sibling to the outbox, deliberately NOT
inside `events/` — queue and ledger stay separate concepts (ADR-004).
(`apps/platform/audit/models.py:AuditRecord`)
_Avoid_: "log"/"activity log"; riding the outbox; storing automatic before/after snapshots —
only curated per-action metadata is kept, so secrets structurally cannot reach the table.

**Audit action**:
The named, `noun.verb` vocabulary of recordable actions (`api_key.created`, …) — a contractual
registry: additive-only, a rename is breaking (ADR-003 algebra). Deliberately decoupled from
routes (a route rename must never rewrite history's vocabulary) AND from the webhook catalog (an
audit action and a webhook event are independent names in independent contracts). `record()`
refuses an unregistered name. (`apps/platform/audit/actions.py:AUDIT_ACTIONS`)
**⚠ Additive-only governs RENAMES, and deleting an action whose ACT has ceased to exist is not one.**
Slice 4 removed seven names on that distinction, and it is worth stating because "additive-only"
reads as forbidding it: a rename carries an act forward under a new spelling and breaks a reader
watching for the old one, whereas these seven had no successor because the thing they recorded stopped
happening — a book kind that no longer exists, an assignment record that was deleted, an immediate
reprice that became a publish. **None of it drew on the one-time pre-production registry reset**,
which #154 §4.2 defines and #155 §14 allocates to slice 8 for the actions that genuinely are renamed.
What makes the deletion safe is a mechanism rather than care: `record()` refuses an unregistered name,
so a route still writing a deleted action fails loudly, which forces the route and the registry into
one commit and leaves no window in which a dead action is written.
_Avoid_: reusing a webhook `event_type` as the action name; renaming a shipped action; **and reading
the paragraph above as a licence to delete an action whose act continues under another name** — that
is the rename, and it is breaking.

**One action per record per kind of act**:
The rule that decides how many names an act needs, and it is applied at the moment splitting is free.
A correction to a declared thing is still a declaration, and a governance reader asking *when did this
stop existing* must not have to read an entry's metadata to find out — so declaring and withdrawing
are always two names, never one with a discriminator inside it. **Per RECORD as well as per act**: two
records with different columns, different products gating them and different readers take different
nouns, even where the acts are the same pair, because a shared noun sends a reader back to
`resource_type` to tell them apart. Splitting later is the rename ADR-004 §2 calls breaking, so the
split happens on the commit that creates the record.
(#358, #368; `apps/platform/audit/actions.py`, the rule stated above the registry)

**record()**:
The one surface for writing an audit entry — the `write_event` calling pattern: call it at the
mutation site inside the change's `@transaction.atomic`; the actor is read from the request-scoped
contextvar the auth seam captured, never passed by hand. No post-commit dispatch (a ledger has no
doorbell). (`apps/platform/audit/ledger.py:record`)

**Actor / actor kind**:
Who performed a recorded action, captured once at the auth seam (`core/auth.py` for tenant
principals, `core/widget_auth.py` for end customers) into a request-scoped contextvar. `actor_kind`
is an OPEN enum — four live from day one (`member`, `api_key`, `operator`, `end_customer`) with
`system` reserved for the deferred system-initiated actions. Every entry stores the actor id **plus
a display snapshot taken at action time**, so a later rename or deletion never corrupts history; an
`operator` always renders **"UBB operator"** (that staff acted, never which staffer). The
`RequestActorMiddleware` resets the contextvar at request end so a pooled thread never leaks one
request's principal into the next. (`apps/platform/audit/actors.py`)
_Avoid_: passing "who" from the mutation site; storing a live FK to the principal instead of the
snapshot; auditing reads or usage ingestion (telemetry, not governance).

## Plans

**Plan**:
A tenant's commercial offer, with two fee axes — access fee and per-seat fee — and the **Pricing
Book its customers are priced from**, which is what they pay for metered compute. A kernel concept
because subscriptions realizes the fee axes (as Stripe Prices) and metering realizes the book (at
rating time), and neither owns them.
_It had a third axis until #369_: a markup percentage and a per-event flat amount, stated on the
plan row. Both columns are deleted — a percentage on a catalogue row could not say what it applied
to, and the book can.
(`apps/platform/plans/models.py:Plan`)

**A Plan's Pricing Book**:
The book of pricing rules a plan's customers resolve their price from, named by a **required,
non-nullable** reference. Assigning a plan is therefore all it takes to price a customer.
_Why required_: a nullable reference produces an alert nobody can act on, because "this plan has no
book" cannot be told apart from "this plan does not price usage" — where the second is said honestly
by a book holding no rules. _What follows_: creating a plan **sequences book creation first**
(`BookService.the_book_a_plan_prices_from`, then `PlanService.create`, which takes the book's id and
so cannot be called before one exists), and metering reads the reference through `queries.py`
(`get_pricing_book_for_customer`) rather than off the model. Resolution ranks it at the
**selected-book** source, one rung below a customer's own rules — a plan's book is a catalogue
shared by everyone on the plan, so ranking it level with an override would let a catalogue reprice
out-rank a negotiated deal.
_Avoid_: treating a customer override as a substitute for a book (it is a rule at a rung inside
resolution, not a route to a book); a plan adopting a book that carries a customer or is the
tenant's default.
(`apps/platform/plans/models.py:Plan.pricing_book`)

**Usage-only plan**:
A plan whose fee axes are both zero, priced entirely from the Pricing Book it names. It has no
Stripe Product, Price, or Subscription at all — plan membership lives in `CustomerPlanAssignment`,
so such a customer is on a real plan with zero presence in Stripe Billing.
(`Plan.has_stripe_axes`)

**Repricing asymmetry**:
Fee edits are **grandfathered** (Stripe Prices are immutable, so a new versioned Price is minted and
existing subscribers keep the old one unless migrated). What a plan's customers pay for usage is not
edited on the plan at all: it is the rules in the book the plan names, changed through a **publish**
on that book, which is what gives a tenant a diff to read before a price moves.

**Markup precedence**:
`the tenant's declared default markup rung -> none`. One rung, and the last step of the ladder: it
prices what no rule matched. A tenant that has declared nothing has NO rung and its unruled events
resolve to `unknown` with no amount; a rung declared AT zero is the tenant saying *charge exactly
what the call cost*, and it settles.
_It had three rungs until #369_, and the two above it were a percentage on a configuration row: a
customer's own override, and the plan's own column. Both records are deleted, and what replaced each
is a **rule** — in the customer's own Pricing Book (#361), and in the book the plan names (#362) —
resolved further up the ladder, on a record that says which quantity it prices.
_The entry this replaces recorded a ratified behaviour that has now stopped being reachable_: a plan
with an explicit zero markup shadowed the tenant default and pinned the customer at provider cost.
It was ratified rather than a defect — but the zero came from a column's DEFAULT, so "the tenant has
said nothing" was served as "the tenant said charge cost". Deleting the column is what makes the
honest answer reachable.
(`apps/metering/pricing/services/markup_service.py`)

## Cross-cutting primitives

**micros**:
The universal money unit — one-millionth of a currency unit; all money is stored and computed in
micros.
_Avoid_: floats/decimals for money, and "cents" (a Stripe cent is 10,000 micros).

**Correlation ID**:
The per-request id threaded through logs and copied onto every outbox event the request produces.
(`core/logging.py`)

**Soft delete**:
The undelete-only policy — `deleted_at` hides a row from default queries; hard delete is
unsupported. (`core/soft_delete.py`)

**Lock ordering**:
The canonical global lock-acquisition order no code path may violate:
Task → Wallet → Customer → TopUpAttempt → Invoice → Posting; within Task, a parent before its
subtasks. (`core/locking.py`)
