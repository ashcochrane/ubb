# Platform Kernel

The shared kernel every product builds on: tenancy, customers, runs, the event outbox, and the
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
The single Tier-2 spend-control switch on a tenant — `off`, `advisory` (compute + emit, never
block), or `enforcing` (block live). (`apps/platform/tenants/flags.py`)
_Avoid_: adding a second flag or reading `metadata` — this is the one switch.

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
seat, otherwise the customer itself; pinned at run creation and never re-resolved.
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

## Runs

**Run**:
A tenant+customer-scoped grouping of many usage events into one logical workflow execution; lives
in the kernel so metering and billing can both reference it without crossing a product boundary.
Status `active | completed | failed | killed`. (`apps/platform/runs/models.py:Run`)

**Hard stop**:
A per-run spend ceiling — the per-run cost limit or the wallet balance floor — snapshotted from
tenant config at run creation, so config changes never affect an in-flight run.
(`apps/platform/runs/services.py:HardStopExceeded`)

**Heartbeat**:
A run's most-recent-event timestamp; its absence past the stale window is what the reaper kills on.
(`apps/platform/runs/models.py:Run.last_event_at`)

**Stop reason**:
The closed vocabulary of why a run stopped — `cost_limit_exceeded`, `task_limit_exceeded`,
`balance_floor_exceeded`, `customer_wide_stop`, `stale`, `stale_max_age`. One source of truth for
every producer and consumer. (`apps/platform/runs/reasons.py`)

## Events

**Outbox event**:
A domain event written in the same atomic transaction as the change that produced it — if the
transaction commits the event is guaranteed, if it rolls back it vanishes. The default cross-product
channel. (`apps/platform/events/models.py:OutboxEvent`, `apps/platform/events/outbox.py:write_event`)
_Avoid_: "message", "signal".

**Handler**:
A product's subscriber to an event type, registered in `AppConfig.ready()`, optionally gated by
`requires_product`. (`apps/platform/events/registry.py`)

**Dead letter**:
An event that has exhausted its retries and been marked `failed` — alerted, never auto-deleted.

**Outbound webhook**:
A tenant's subscribed HTTP delivery of events to their own endpoint, HMAC-signed and stamped with
`livemode`. (`apps/platform/events/webhook_models.py:TenantWebhookConfig`)

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
Run → Wallet → Customer → TopUpAttempt → Invoice → UsageEvent. (`core/locking.py`)
