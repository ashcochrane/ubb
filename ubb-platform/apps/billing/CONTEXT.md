# Billing

The money layer for prepaid and postpaid tenants — the prepaid credit ledger, real-time spend
control, auto-top-up, and the period-close Stripe line-item push. Billing owns everything up to
invoice line items / credit drawdown; Stripe owns collection, tax, dunning, refunds, and disputes.
Code anchors are relative to `ubb-platform/`.

## Prepaid wallet & credit ledger

**Wallet**:
A customer's single prepaid credit account holding a spendable balance in one currency; one per
customer. (`apps/billing/wallets/models.py:Wallet`)

**Ledger entry**:
An append-only row recording one balance movement (its signed amount and resulting balance), made
exactly-once per idempotency key. (`apps/billing/wallets/models.py:WalletTransaction`)
_Avoid_: mutating a balance without writing a ledger entry.

**Drawdown**:
The wallet debit applied when a `usage.recorded` event is processed.
_Avoid_: "charge" — a charge is a Stripe collection; a drawdown is a ledger debit.

**Credit grant (lot)**:
A layer of (often expiring or promo) credit stacked on the wallet with its own remaining balance;
base money is the non-grant remainder, derived not stored.
(`apps/billing/wallets/models.py:CreditGrant`)

**Grant kind**:
Whether a lot is `paid` (from a top-up, withdrawable) or `promo` (never withdrawable); promo is
consumed before paid.

**Consumption order**:
The deterministic order lots are drawn down — soonest expiry first, promo before paid — with the
remainder charged to base money.

**Clawback**:
Restoring the credit invariant after a dispute loss or Stripe refund by voiding/consuming lot
remainders.

**Min balance (wallet floor)**:
The negative-balance floor a wallet may reach before its owner is suspended.
_Avoid_: "credit limit".

## Spend control

**Start-gate (spend gate)**:
The durable pre-run check — suspension, stop flag, rate/concurrency limits, affordability, budget —
run before a Run is created. (`apps/billing/gating/services/risk_service.py`)

**Live ledger (Tier-2 counter)**:
The billing-owner-keyed Redis counter decremented synchronously at record time so the API response
can carry a real stop verdict; reconciled against the durable ledger.
(`apps/billing/gating/services/live_ledger_service.py`)

**Customer-wide stop flag**:
The cooperative, owner-keyed flag set when the live counter crosses the wallet floor or budget cap;
it blocks new runs until recovery.

**Enforcement mode**:
`off` / `advisory` / `enforcing` — when `off`, spend control is a no-op and behavior is unchanged.
_Avoid_: a second enable flag — this is the single switch (mirrors the tenant's `enforcement_mode`).

**Budget**:
A per-tenant (optionally per-customer) monthly spend cap with alert levels.
(`apps/billing/gating/models.py:BudgetConfig`)

**Estimate-hold-settle**:
The async-ingest accept-time reservation of an *estimated* cost on the live counter, later settled
against the actual. (`apps/billing/gating/services/hold_service.py`)

**Task cost cap**:
A tenant-wide per-task billed ceiling enforced across all runs sharing a `task_id`.

## Auto top-up

**Auto top-up**:
Automatically charging the saved payment method to refill the wallet when the balance falls below a
trigger threshold. (`apps/billing/topups/models.py:AutoTopUpConfig`)

**Top-up attempt**:
A persisted charge attempt created *before* calling Stripe (to supply deterministic idempotency
keys); status walks `pending → succeeded/failed/requires_action/superseded`.
(`apps/billing/topups/models.py:TopUpAttempt`)

**requires_action**:
A top-up that needs SCA (Strong Customer Authentication) before it can complete.

## Period close / usage invoicing (postpaid)

**Period close**:
The monthly job pushing each postpaid customer's prior-month usage to Stripe as invoice line items.
(`apps/billing/invoicing/tasks.py`)

**Usage invoice**:
A postpaid customer's usage for one calendar month, pushed to Stripe as line items; one per
(customer, month). (`apps/billing/invoicing/models.py:CustomerUsageInvoice`)
_Avoid_: confusing it with a Stripe invoice — UBB pushes the lines; Stripe owns the invoice.

**Line-item push**:
The claim → Stripe → record flow that aggregates usage into lines and finalizes the Stripe invoice.

**Consolidation**:
Pinning usage lines onto the owner's subscription-renewal invoice instead of minting a standalone
one.

**failed_permanent**:
A usage invoice parked after exhausting its retries; emits `usage.invoice_push_failed_permanent`.

**Platform fee**:
UBB's own charge to the tenant, computed per-product at the tenant's own period close.
(`apps/billing/tenant_billing/`)

## Stripe connector kit (the ADR-001 §5 exception)

**stripe_call**:
The mandatory Stripe API wrapper — maps Stripe errors to domain exceptions, retries idempotently,
and requires an explicit `api_key` so a sandbox flow can never use the live key.
(`apps/billing/stripe/services/stripe_service.py`)

**StripeWebhookEvent**:
The single dedup table shared across both webhook endpoints, so a replayed Stripe event is
deduplicated no matter which endpoint receives it. (`apps/billing/stripe/models.py`)

**AR transition table**:
Stripe's legal invoice-status graph, shared by the webhook fast path and the hourly poller so they
can never diverge. (`apps/billing/connectors/stripe/invoice_routing.py`)

## Read contract & events

**queries.py**:
Billing's plain-data read contract — notably `is_usage_period_closed` (metering consults it before
accepting a backdated `effective_at`) and the live-spend ports.
_Avoid_: importing billing models from another product; go through `queries.py`/`ports`.

**Key events**:
Consumes `usage.recorded` (drawdown); emits `balance_low` (→ auto-top-up), `balance_overage`,
`customer_suspended`, `credit_grant_expired`, `budget.threshold_reached`, `stop.fired`.
