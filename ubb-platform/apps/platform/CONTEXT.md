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
An enabled product app on a tenant, drawn from `{metering, billing, subscriptions, referrals}`;
`metering` is always present.
_Avoid_: "module", "service" when you mean an enabled product.

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

## Tasks

**Task**:
The registered unit of agent work — a tenant+customer-scoped grouping of many usage events into
one logical workflow execution, registered at the start-gate; lives in the kernel so metering and
billing can both reference it without crossing a product boundary. Carries both running totals
(billed + provider, denominationally explicit) and its signal points. Status
`active | completed | failed | killed`. (`apps/platform/tasks/models.py:Task`)
_Avoid_: "run" (the pre-rename name), and the retired label-era "task" sense (a `tags` value) —
tags are analytics-only and never attach a limit.

**Subtask**:
A parent-linked child unit of work — a task registered under an active top-level task, with its
own COGS limit and lifecycle. Its spend rolls up into the parent's totals (the parent's cap covers
everything underneath it); crossing its own limit kills it alone (`subtask.limit_exceeded`) while
the parent keeps running; a parent kill/close cascades downward to its active subtasks — never
upward. One containment level at launch. (`apps/platform/tasks/models.py:Task.parent`)
_Avoid_: "child task", "nested task", and the retired label-era "task" sense.

**Task limit (provider-cost limit)**:
A task's COGS ceiling — denominated in provider cost (what the job burns), never billed markup;
passed at start or defaulted from tenant config, snapshotted at creation. Only the provider total
races it; crossing it is a signal point (kill + `task.limit_exceeded`), never a billing wall.
(`apps/platform/tasks/models.py:Task.provider_cost_limit_micros`)
_Avoid_: "hard stop" — that vocabulary retired with the 429.

**Killed (task)**:
The stop signal fired for this unit — its limit or floor snapshot was crossed, or the reaper
terminated it. Late events still land, bill, and count into the killed unit's totals (and its
parent's, for a subtask); the flip is the durable record that the signal fired, not a wall.
Killing a parent cascades the flip to its active subtasks; killing a subtask kills it alone.
(`apps/platform/tasks/services.py:TaskService.kill_task`)

**Heartbeat**:
A task's most-recent-event timestamp; its absence past the stale window is what the reaper kills
on. (`apps/platform/tasks/models.py:Task.last_event_at`)

**Stop reason**:
The closed vocabulary of why a stop signal fired — `task_limit`, `subtask_limit`,
`customer_floor`, `task_not_active`, `customer_wide_stop`, `stale`, `stale_max_age`, plus the
kill-metadata-only `parent_killed` (a cascade flip, never on an ack or event). One source of truth
for every producer and consumer; rides the ack's `stop_reason`, never an HTTP error.
(`apps/platform/tasks/reasons.py`)

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
_Avoid_: reusing a webhook `event_type` as the action name; renaming a shipped action.

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
Task → Wallet → Customer → TopUpAttempt → Invoice → UsageEvent; within Task, a parent before its
subtasks. (`core/locking.py`)
