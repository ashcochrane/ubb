# Stage C — Auto-Top-Up Money-Safety Hardening (Detailed Design)

**Date:** 2026-06-09
**Status:** Approved (approach + SCA=flag-and-notify) — pending written-spec review
**Program:** Pricing Cards + Billing Integrity (Stages A–D). **A + B done.**
**Depends on:** Stage 3 prepaid drawdown/gate, the Stripe connector (auto-top-up), `WalletTransaction` idempotency constraint, the outbox.

## Objective

Make the off-session auto-top-up (charge a saved card → credit the wallet) **exactly-once and self-healing** under crashes, retries, lost webhooks, and SCA — using the canonical payment-reliability pattern: a **PaymentIntent-driven credit made exactly-once by one DB unique constraint**, reached by three convergent paths (synchronous task, webhook backstop, repairing reconcile sweep). This closes the four money-safety windows the audit + understanding sweep confirmed:

| # | Window | Root cause |
|---|---|---|
| **a** | **Paid-but-no-balance** (critical) | Stripe charges (`stripe_api.py:71-83`); credit commits later (`tasks.py:89-114`). Crash between + the 30-min expire cron flips the attempt to `expired` → charge abandoned. `reconcile_topups_with_stripe` filters `status='succeeded'` so it can't see it; it only logs, never repairs. |
| **b** | **Double-charge** (critical) | Stripe idempotency key `charge-{attempt.id}` is per-attempt; a re-emitted `BalanceLow` after the attempt leaves `pending` mints a new attempt → new key → second real charge. |
| **c** | **Lost-credit** (important) | Auto-top-up `WalletTransaction` has **no** `idempotency_key`, so `uq_wallet_txn_idempotency` is inert on this path (the checkout path sets `topup:{session.id}`). |
| **d** | **Off-session SCA** (important) | `authentication_required` → generic `failed`, no re-auth path; non-`succeeded` PI statuses wrongly marked failed; no `payment_intent.*` webhook exists. |

## Architecture: PaymentIntent-driven, exactly-once charge-then-credit

**Principle (Stripe-endorsed):** the credit is driven by the **PaymentIntent**, made exactly-once by a single DB unique constraint keyed on the PI id, so the synchronous task, a webhook, and a reconcile sweep all converge to **one** credit. Deterministic Stripe idempotency keys make at-least-once delivery safe; the **attempt-status machine stops being load-bearing for money** (it becomes UX/tracking only).

### 1. Stamp PaymentIntent metadata
`PaymentIntent.create(..., metadata={"topup_attempt_id": str(attempt.id)})` (`stripe_api.py`) so *any* path can resolve the attempt from the PI (and vice-versa). Keep the existing deterministic Stripe idempotency key `charge-{attempt.id}`.

### 2. One convergent credit function — `apply_topup_credit(attempt, payment_intent)`
A single service function used by **all three** credit paths. Under `lock_for_billing(customer)`:
- Resolve `pi_id` + amount + `latest_charge`; build `idempotency_key = f"auto_topup:{pi_id}"`.
- `SELECT` for an existing `WalletTransaction` with that key → if present, no-op (already credited).
- Else credit `wallet.balance_micros`, create the `WalletTransaction(type="TOP_UP", idempotency_key=…)`, set `attempt.status="succeeded"` + `stripe_payment_intent_id`/`stripe_charge_id`.
- Catch `IntegrityError` on the unique constraint as "already credited" (the **constraint is the exactly-once guarantee**; the SELECT is just an optimization). **Closes (c).**

### 3. `payment_intent.succeeded` webhook backstop
New handler on the **connected account** (added to `WEBHOOK_HANDLERS`, `api/v1/webhooks.py`): resolve the tenant by `event.account`, resolve the attempt by `payment_intent.metadata.topup_attempt_id`, call `apply_topup_credit`. Whichever of {task, webhook} wins applies the one credit; the other no-ops. **Primary fast-path fix for (a).** (Webhook-event dedup already exists via `StripeWebhookEvent`.) Also add `payment_intent.payment_failed` → mark the attempt `failed` (idempotently).

### 4. Stripe-driven, *repairing* reconcile sweep
Rewrite `reconcile_topups_with_stripe` to be **source-of-truth-driven**: for each connected account, `PaymentIntent.list(created>=cutoff)` filtered to auto-top-up PIs (by metadata), and for any **succeeded** PI with **no** `auto_topup:{pi_id}` `WalletTransaction`, call `apply_topup_credit` (**repair**) — independent of the local attempt status, so even a wrongly-`expired` attempt's money is recovered. Lookback **~4 days** (beyond Stripe's 3-day webhook-retry horizon, so it only repairs genuinely-lost events). Cadence **~hourly**. Retain the existing amount/refund audit as a secondary check. **Durable safety net for (a).**

### 5. Double-charge guard (b)
- At charge time, **under the wallet lock, re-check the balance**: if it is already ≥ the trigger threshold (a prior path funded it), mark the attempt `superseded` and **do not charge**.
- Keep the in-flight partial-unique (`uq_one_pending_auto_topup_per_customer`).
- Because the credit is PI-driven (steps 3–4), a paid attempt is **never abandoned** → the wallet is funded → no stale low-balance `BalanceLow` re-trigger → no second charge. `expire_stale_topup_attempts` no longer endangers money (reconcile recovers any charge regardless of attempt status); expiry is downgraded to a UX/cleanup concern.

### 6. SCA handling — flag + notify the tenant (chosen)
- Detect `StripePaymentError` with `code == "authentication_required"` in the charge task → set attempt status **`requires_action`** (not `failed`), persist the PI id, and **emit `auto_topup.requires_action`** via the outbox → tenant webhook, so the **tenant** prompts their end-customer to re-authenticate on-session. UBB does not build the re-auth funnel (the tenant owns the end-customer UX).
- Treat PaymentIntent status `requires_action`/`processing` (non-exception) as **deferred** (a non-terminal status), not `failed` — if it later settles, the webhook/reconcile credits it.

### 7. Hardening
- Dispatch the charge task via `transaction.on_commit` (true transactional-outbox handoff; determinism makes at-least-once safe).
- Charge the customer's `invoice_settings.default_payment_method` when set (fall back to the first card) instead of implicitly `data[0]`.

## New / changed surface

- **New status values** on `TopUpAttempt`: `requires_action`, `superseded` (additive to the choices).
- **New event** `auto_topup.requires_action` (`platform/events/schemas.py`) + delivery registration.
- **New service** `apply_topup_credit` in `apps/billing/topups/services.py` (`AutoTopUpService`), imported by the task, the webhook, and the reconcile sweep.
- **New webhook handlers** `payment_intent.succeeded` / `payment_intent.payment_failed`.
- **Rewritten** `reconcile_topups_with_stripe` (Stripe-driven, repairing); beat cadence ~hourly.
- **Changed:** the charge task (use `apply_topup_credit` + skip-if-funded + SCA branch + `on_commit` dispatch + PI metadata + default PM).
- **No new DB migration** is required: `TopUpAttempt.status` is a `CharField` (adding `requires_action`/`superseded` choices is not a schema change), and `stripe_payment_intent_id`/`stripe_charge_id` columns already exist (the task writes them today). Django emits a no-op `AlterField` for choices changes — generate it if `makemigrations --check` flags it, otherwise none.

## Decision Log

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Exactly-once mechanism | **DB unique constraint on `auto_topup:{pi_id}`** (the `WalletTransaction` key) | The constraint, not status checks, is the guarantee; all paths converge |
| 2 | Credit paths | **Task + `payment_intent.succeeded` webhook + repairing reconcile**, all via `apply_topup_credit` | Fast-path + durable safety net; survives task death + lost webhooks |
| 3 | Reconcile | **Stripe-driven (list PIs) + repair**, not local-row audit-only | Only a source-of-truth scan can find paid-but-uncredited |
| 4 | Attempt→PI link | **PI `metadata.topup_attempt_id`** | Lets any path resolve the attempt even if the task never wrote the PI id back |
| 5 | Double-charge | **Skip-if-funded under lock + PI-driven credit (never abandon paid)** | Removes the stale-low-balance re-trigger; credit independent of attempt status |
| 6 | SCA | **Flag + `auto_topup.requires_action` event to the tenant** | Platform surfaces the signal; tenant owns end-customer re-auth UX (user-chosen) |
| 7 | Reconcile cadence/lookback | **~hourly, ~4-day lookback** | Beyond Stripe's 3-day retry horizon → repairs only genuinely-lost events |
| 8 | Dispatch | **`transaction.on_commit`** | Transactional-outbox handoff; safe under at-least-once |

## Risks & mitigations

- **Mis-credit / double-credit** — the entire design's safety rests on `uq_wallet_txn_idempotency` keyed on `auto_topup:{pi_id}`; tests assert task+webhook+reconcile on the same PI produce exactly one credit, and a crash-then-reconcile recovers the credit.
- **Reconcile listing cost / rate limits** at scale — bounded lookback + per-account pagination; cadence hourly not per-minute; note as a future optimization if PI volume grows.
- **Stripe idempotency-key 24h TTL vs longer retry horizons** — the PI-id ledger constraint (not the Stripe key) prevents double-credit beyond 24h; a re-derived key past TTL only re-charges if the PI no longer exists, which the reconcile/credit constraint still de-dupes.
- **SCA event not actioned by tenant** — out of UBB's control by design (chosen scope); the `requires_action` status + event give the tenant everything needed; a fuller funnel is a documented future option.

## Acceptance criteria

- **Exactly-once:** task credits once; a `payment_intent.succeeded` webhook for the same PI no-ops; a reconcile pass for the same PI no-ops — **one** `WalletTransaction(auto_topup:{pi_id})`.
- **Paid-but-no-balance recovery (a):** simulate charge-success-then-crash (attempt left `pending`/`expired`, no credit); the `payment_intent.succeeded` webhook **or** the reconcile sweep credits the wallet exactly once.
- **Double-charge prevented (b):** a second `BalanceLow` after the wallet is already funded → the charge task **skips** (no second PaymentIntent).
- **Credit idempotency (c):** the auto-top-up `WalletTransaction` carries `idempotency_key=auto_topup:{pi_id}`; a duplicate credit attempt raises `IntegrityError` and no-ops.
- **SCA (d):** `authentication_required` → attempt `requires_action`, PI persisted, `auto_topup.requires_action` emitted; **not** `failed`. A `requires_action`/`processing` PI is not marked failed.
- Reconcile is Stripe-driven and repairs (asserted: a succeeded PI with no local credit is credited by the sweep).
- Full platform + SDK suites green; migrations (if any) apply on a fresh DB.
