> ⚠️ SUPERSEDED (usage push mechanism only): the "pending InvoiceItems roll into the subscription invoice / one clean invoice" model was REVERSED. Usage is now pushed on its OWN standalone finalized invoice, two-phase (`Invoice.create` draft → `InvoiceItem.create(invoice=<draft>)` → finalize) — see `2026-06-10-wave45-postpaid-hardening-design.md` (C1) and `2026-06-10-wave55-prelaunch-hardening-design.md` (B1). The mode-aware drawdown/gate, period-close aggregation, and `CustomerUsageInvoice` model remain current. Master truth: `2026-06-10-program-current-state.md`.

# Stage 4 — Postpaid Usage Billing (Detailed Design)

**Date:** 2026-06-05
**Status:** Draft for review
**Parent:** `2026-06-05-ubb-repositioning-design.md`
**Depends on:** Stage 1 (durable `UsageEvent` ledger), Stage 2 (`StripeSubscription` mirror), Stage 3 (budget gate). **Blocks:** none — final stage of the program.

## Objective

Make `billing_mode` **behavioural** and add the **postpaid** usage path: for `billing_mode=postpaid` tenants, usage is metered now and **invoiced monthly** as Stripe line items, rather than drawn from prepaid credits. Subscription (access fee + seats) continues to flow through the customer's Stripe Subscription untouched. This completes the three usage-billing modes and the 5-stage program.

## The mental model (whole system, after this stage)

An end customer's bill has three independently-controlled streams:

| Stream | Mechanism | Owner |
|---|---|---|
| **Access fee + seats** | Stripe **Subscription** (recurring) | Stripe bills; UBB reads for margin (Stage 2) |
| **Usage — prepaid** | drawn from topped-up credits in real time, gated | UBB (Stage 3) |
| **Usage — postpaid** | metered now, **pushed to Stripe as invoice line items at month close** | **UBB (this stage)** |

`billing_mode` (per-tenant) selects the **usage** path: `meter_only` (no money), `prepaid` (Stage 3), `postpaid` (Stage 4). Subscription is always separate. Today `billing_mode` is only *validated* (`tenants/models.py:57`); Stage 4 wires it into the drawdown handler and the gate.

## Scope

**In scope:** mode-aware drawdown + gate; period-close aggregation of postpaid usage; idempotent Stripe line-item push (pending items on the subscription invoice, standalone-invoice fallback); a per-tenant line-item granularity config; API/SDK + a `usage.invoice_pushed` webhook; a reconcile/retry task.
**Out of scope (YAGNI):** per-subscription-cycle period anchoring (calendar month is used; noted as a future refinement); credit/refund of pushed usage (Stripe owns refunds); per-customer `billing_mode` overrides (it stays per-tenant per the program).

## 1. Mode-aware drawdown

`handle_usage_recorded_billing` (the `billing`-gated outbox handler) currently always deducts the wallet. Make it read `tenant.billing_mode`:
- **prepaid** → the existing wallet block (deduct → suspend on min-balance → `BalanceLow` for auto-top-up). Unchanged.
- **postpaid** → **skip the entire wallet `transaction.atomic` block** (no prepaid balance exists). Usage remains durable in `UsageEvent`; it will be aggregated at month close.
- Both modes still run the post-block `TenantBillingService.accumulate_usage` (UBB's platform fee on the tenant, independent of how the tenant bills *its* customers) and `BudgetService.record_usage_spend` (the spend counter — see §3).

The mode check wraps only the wallet block; everything else is unchanged.

## 2. Postpaid period-close → Stripe push

A monthly task (`close_postpaid_usage_periods`, on the 1st) for each **postpaid** tenant, for each end customer with usage in the **prior calendar month**:

1. **Aggregate on-demand** from the `UsageEvent` ledger (the durable truth): `Σ billed_cost_micros` for the customer in the period, grouped by the tenant's configured dimension (default: none → one total). **The line items MUST sum to the customer's total billed usage** — so unlike the Stage 2 dimensional *analytics* (which drops events lacking the dimension), the invoicing aggregation routes events with an empty/missing dimension into an explicit `Usage (other)` line. The invariant `Σ line_item.amount == total_billed_micros` is asserted before any Stripe call. No new hot-path accumulation.
2. **Claim** a `CustomerUsageInvoice` row (`status pending → pushing`) inside a transaction (`select_for_update`), skipping if already `pushed`.
3. **Push to Stripe outside any transaction** (no DB locks during network I/O), on the **tenant's connected account** (`stripe_account=tenant.stripe_connected_account_id`), for the customer's `stripe_customer_id`:
   - For each line (one, or one per dimension value): `stripe.InvoiceItem.create(customer=…, amount=<cents>, currency=…, description=…, stripe_account=…, idempotency_key=f"usage-item-{record.id}-{slug}")` **with no `invoice=`** → a *pending* item that Stripe rolls into the customer's **next Subscription invoice**.
   - **If the customer has no active `StripeSubscription`** (Stage 2 mirror), the pending items would never be collected — so additionally create a **standalone invoice**: `Invoice.create(customer=…, auto_advance=False, stripe_account=…, idempotency_key=f"usage-invoice-{record.id}")` (pulls in the pending items) → `finalize_invoice(idempotency_key=f"usage-finalize-{record.id}")`; store its id on the record.
4. **Record** (`status → pushed`, `pushed_at`, line items, optional `stripe_invoice_id`) in a new transaction; emit `usage.invoice_pushed`.
   - On Stripe failure → revert `pushing → pending` (next run retries); stale `pushing` rows (>30 min) reclaimed. **Exactly the two-phase, crash-safe, stale-reclaim pattern of `tenant_billing._create_tenant_invoice`** — reused, not reinvented.
   - Customer with **no `stripe_customer_id`** → `status skipped` + flagged (visible via API), never silently dropped. Zero usage → `skipped`.

**Idempotency** is anchored on `CustomerUsageInvoice` (unique `(customer, period_start)`) + deterministic Stripe idempotency keys derived from `record.id`, so re-runs and retries never double-bill.

## 3. Mode-aware spend control (the postpaid guardrail)

The real risk a postpaid tenant fears is a **runaway agent → surprise five-figure invoice**. So the Stage 3 **budget cap applies to postpaid**: it is a per-period spend *ceiling* independent of any credit balance. `RiskService.check` becomes mode-aware:
- **prepaid** → existing credit-affordability check (`balance < -min_balance → insufficient_funds`) **then** the budget-cap check.
- **postpaid** → **skip** the credit-affordability check (no prepaid balance), **keep** the budget-cap check (`budget_exceeded` when enforcing + over cap).

So a postpaid tenant gets real-time "stop at $X / customer / month" protection even though billing is deferred. The budget counter is already incremented for all billing tenants (§1), so no extra wiring beyond the gate branch.

## 4. Period & timing

**Calendar month**, aligned with the margin snapshots (Stage 2) and the budget period (Stage 3) — one period concept system-wide. The close task runs on the **1st** and processes the **prior** month `[first_of_prior_month, first_of_this_month)` by `effective_at`. Because usage is pushed as *pending* items, the exact Stripe invoice date is decoupled — Stripe attaches them to the customer's next subscription invoice. (Per-subscription-cycle anchoring is a future refinement; calendar month keeps the system coherent.)

## 5. Data model

`apps/billing/invoicing/models.py` (the home of customer-facing invoice records):

| Model | Fields |
|---|---|
| `CustomerUsageInvoice` **(new)** | `tenant` FK, `customer` FK, `period_start` (Date), `period_end` (Date), `total_billed_micros` (BigInt), `currency` (CharField, default from tenant), `status` (`pending` \| `pushing` \| `pushed` \| `skipped` \| `failed`, db_index), `stripe_invoice_id` (CharField, blank — standalone path only), `skip_reason` (CharField, blank), `pushed_at` (DateTime, null). Unique `(customer, period_start)`. |
| `UsageInvoiceLineItem` **(new)** | `usage_invoice` FK → `CustomerUsageInvoice`, `dimension` (CharField — "" for the single-line case, else the dimension value), `amount_micros` (BigInt), `stripe_invoice_item_id` (CharField, blank). |
| `PostpaidUsageConfig` **(new)** | `tenant` OneToOne; `usage_line_item_group_by` (CharField, default `""` → single line; or `"product_id"`, or `"tag:<key>"`). |

(`apps/billing/invoicing/` already holds the top-up `Invoice` model; these are added beside it.)

## 6. API & SDK (all `billing`-gated)

- `GET /api/v1/billing/customers/{customer_id}/usage-invoices` → period rows (`period_start`, `status`, `total_billed_micros`, `stripe_invoice_id`, line items).
- `GET /api/v1/billing/tenant/usage-invoices?period=YYYY-MM` → tenant-wide view of one close (incl. `skipped` customers + reasons).
- `GET|PUT /api/v1/billing/postpaid-config` → read/set `usage_line_item_group_by`.
- SDK: `get_usage_invoices(customer_id)`, `get_postpaid_config()` / `set_postpaid_config(group_by="")`.
- New webhook **`usage.invoice_pushed`** (payload: tenant, customer, period, total, line_item_count, stripe_invoice_id?) via the existing outbox → tenant-webhook path.

## 7. Keep / reframe / new

- **Reframe:** `handle_usage_recorded_billing` + `RiskService.check` → mode-aware (`prepaid`/`postpaid`).
- **New:** `CustomerUsageInvoice` / `UsageInvoiceLineItem` / `PostpaidUsageConfig`; `PostpaidUsageService` (aggregate + Stripe push); `close_postpaid_usage_periods` + `reconcile_postpaid_usage` tasks + beat entries; budget + usage-invoice API/SDK; `usage.invoice_pushed` contract.
- **Reuse:** `stripe_call` wrapper + idempotency-key pattern; `tenant_billing`'s two-phase crash-safe close; Stage 1 dimensional aggregation (`get_per_customer_cost_totals` / `get_dimensional_margin`); Stage 2 `StripeSubscription` mirror (subscription-presence check).

## Stage-4 Decision Log

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | `billing_mode` semantics | **Behavioural: selects the usage path** (meter_only/prepaid/postpaid); subscription always separate | Matches the customer's "split" mental model. |
| 2 | Postpaid drawdown | **Skip the wallet block; usage stays in the ledger** | No prepaid balance in postpaid. |
| 3 | Stripe push | **Pending `InvoiceItem`s on the subscription invoice; standalone invoice fallback** | One clean invoice (access+seats+usage) for the end customer; nothing orphaned. |
| 4 | Aggregation | **On-demand from `UsageEvent` at close** | Durable ledger is truth; no hot-path accumulation. |
| 5 | Granularity | **Single "Usage — {month}" line by default; `group_by` opt-in** (`product_id`/`tag:<key>`) | Simple default; per-seat/per-feature billing when wanted. |
| 6 | Postpaid spend control | **Budget cap applies; gate skips credit-affordability, keeps budget** | Guards against a runaway-agent surprise invoice. |
| 7 | Period | **Calendar month, close on the 1st for prior month** | System-wide period coherence; pending items decouple the Stripe date. |
| 8 | Idempotency/crash-safety | **`CustomerUsageInvoice` unique `(customer, period)` + two-phase close, mirrored from `tenant_billing`** | Proven pattern; never double-bills. |

## Risks & mitigations

- **Double-billing on retry/concurrency.** Mitigated by the unique `(customer, period)` anchor, deterministic Stripe idempotency keys, and the two-phase claim/record. Tests assert a re-run produces no new Stripe calls / no duplicate line items.
- **Orphaned pending items (subscription-less customer).** Mitigated by the standalone-invoice fallback that collects pending items and finalizes.
- **Stripe failures mid-close.** Two-phase pattern: `pushing` rows revert to `pending`; stale ones reclaimed; reconcile task retries. Money side is safe (Stripe is idempotent on our keys).
- **Mode mis-set / wallet drawn for a postpaid tenant.** The mode branch is the single guard; a test asserts a postpaid tenant's wallet is never touched by the drawdown handler.
- **Stripe coupling in tests.** All Stripe calls go through `stripe_call`; tests mock it (the suite's established approach) and assert idempotency keys + arguments.

## Acceptance criteria

- A `postpaid` tenant's usage event → wallet is **not** deducted; the `UsageEvent` + budget counter are recorded.
- The gate for a postpaid customer **never** returns `insufficient_funds`, but **does** return `budget_exceeded` when an enforcing budget cap is exceeded.
- Month-close for a postpaid customer with usage + an active subscription → pending `InvoiceItem`(s) created on the connected account with the right amount + idempotency key; `CustomerUsageInvoice.status == pushed`; `usage.invoice_pushed` emitted.
- A subscription-less postpaid customer → a standalone finalized invoice collects the items; `stripe_invoice_id` set.
- `group_by="product_id"` → one line item per product with correct per-product amounts summing to the total.
- A second close run for the same period → no new Stripe calls, no duplicate line items (idempotent).
- Customer without `stripe_customer_id` → `skipped` + reason, visible via API; never errors the whole close.
- SDK usage-invoice + postpaid-config methods round-trip; migrations apply on a fresh DB; full platform + SDK suites green.
