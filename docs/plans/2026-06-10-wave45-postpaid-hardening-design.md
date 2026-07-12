# Wave 4.5 — Postpaid J2 Money-Critical Hardening (Design)

**Date:** 2026-06-10 · **Method:** Stripe-behavior-grounded research (WebSearch) + design. Triggered by the J2 stock-take (B−), which found two Critical money bugs + three Importants that the 812 mocked/cent-aligned tests hid. **Release-blockers before any real-money postpaid tenant.**

**Scope:** Five fixes, code-reasoned, tests stay MOCKED (no live Stripe — owner decision). No new features beyond these five (YAGNI).

## The honest finding behind C1
Stripe's documented behavior (research, cited below): a pending `InvoiceItem` only sweeps onto a subscription's renewal invoice if it exists **before** Stripe creates that invoice (at the anchor, 1st 00:00). UBB aggregates usage **at month-end and pushes after**, so the `subscription=`-pinned item lands on the **next** month's invoice — the off-by-one. You **cannot** add lines to a finalized (`open`) invoice; the only ways to truly land usage on the renewal are pin-to-draft via an `invoice.created` handler (within Stripe's ~1h finalize window) or own finalization (`auto_advance=false` + manual finalize — the Metronome pattern). **Therefore "one coherent bill" was an over-optimistic Wave-4 claim (the capstone mocked the timing); it is a FEATURE, not a one-liner.** Wave 4.5 fixes the *bug*; true single-invoice consolidation is deferred to Wave 5.

Sources: Stripe docs — subscription invoices, automatic invoice advancement, scheduled finalization, invoice edits, InvoiceItems API, How-Metronome-works-with-Stripe.

---

## C1 — usage rides the wrong cycle → **always bill usage on its own standalone invoice** (DECIDED)
**Fix:** drop the `subscription=`-pin attempt entirely for postpaid usage. Each period's usage is billed on its **own** finalized standalone Stripe invoice (the path that already exists in `_push_to_stripe`), created+finalized in the close — **correct-cycle, deterministic, robust regardless of Stripe's exact sweep timing.** No off-by-one, no silent slide.
- In `apps/billing/invoicing/services/postpaid_service.py` `_push_to_stripe`: remove the owner-subscription lookup + the `subscription=<sub_id>` pin + the `_subscription_cycle_closed` guard (now dead code — delete it). Always create the usage `InvoiceItem`(s) (no `subscription=`) then `Invoice.create` + `finalize_invoice` for that period (the existing standalone branch), persisting `stripe_invoice_id`.
- The subscription's own renewal invoice (access + seat) is unaffected and bills separately.
- **Accepted tradeoff, stated plainly:** a postpaid customer receives **two** Stripe invoices per month — the subscription renewal (access+seat, in advance) and the usage invoice (in arrears) — both correctly dated. True single consolidated invoice is **Wave 5** (owned-finalize / event-driven pin-to-draft).
- The `close-postpaid-usage-periods` beat schedule no longer needs the pre-finalization window; it can stay (or move) — timing no longer affects correctness since usage is its own invoice. (Leave the schedule as-is; the hourly `reconcile-postpaid-usage` remains the idempotent backstop.)

## C2 — sub-cent usage crashes the push → **floor to cents + carry residual forward + audit** (DECIDED)
**Root cause:** `micros_to_cents` raises `StripeFatalError` on `amount % 10_000 != 0`; UBB's rate-card engine emits sub-cent micros → throw → `pushing→pending` → hourly retry forever → silent revenue stall.
**Fix (at the aggregation boundary in `PostpaidUsageService`, NOT in `micros_to_cents` — that invariant guard stays for the cent-aligned platform-invoicing path):**
- New field `CustomerUsageInvoice.residual_micros = BigIntegerField(default=0)` (+ migration) — the sub-cent crumb deferred from this period.
- In `push_customer_period`: pull the prior unpushed residual (most recent `pushed` row's `residual_micros`) for the customer; fold it into the largest line; floor each line to whole cents for the Stripe push; accumulate `residual = Σ(line_micros - floored_cent_micros)`; persist `residual_micros = residual` (`< 10_000` by construction) on the new row.
- Per-line: `cent_micros = amount + carry; cents = cent_micros // 10_000; carry = cent_micros - cents*10_000; if cents <= 0: continue` (fold carry into the first/largest line — lines already sorted desc — so a tiny carry never resurrects a zero line). The per-line `micros_to_cents` now always receives cent-aligned input → never raises.
- **Truncate (floor), never round-up** — never over-bill the tenant's customer; **carry-forward, never discard** — revenue eventually captured in full.
- **Audit:** add `residual_micros` to the `UsageInvoicePushed` event payload; `logger.info("postpaid.residual_carried", ...)`; alert if `residual_micros >= 10_000` (carry-logic invariant breach). Conservation provable: `Σ(billed_cents·10_000) + ending_residual == Σ billed_cost_micros`.

## I1 — currency mismatch silently drops usage → **thread currency + fail loud**
Plan Price hardcodes `currency="usd"` (`orchestration/service.py`) while usage items use `tenant.default_currency.lower()`. A non-USD tenant's usage item is silently excluded by Stripe → revenue loss.
- Thread tenant currency into `Price.create`: `currency=(tenant.default_currency or "usd").lower()`.
- Assert at subscribe AND at push: if `(tenant.default_currency or "usd").lower() != (StripeSubscription.currency or "usd").lower()` → raise `StripeFatalError` (loud, reconcilable — no FX, a mismatch is a misconfiguration). Use the `StripeSubscription.currency` mirror as the source of truth at push time.

## I2 — stale margin mirror after set_seats → **refresh the mirror in-band**
`set_seats` updates only `CustomerSubscriptionItem.quantity`, leaving `StripeSubscription.amount_micros` (the accrual/margin source) stale until a webhook/sync. After `item.save`, recompute and persist:
`mirror.amount_micros = Σ(li.unit_amount_micros × li.quantity)` over the sub's `line_items`; `mirror.quantity = new_seats`; `mirror.last_synced_at = now()`. Idempotent + webhook-convergent (a later `customer.subscription.updated` overwrites with the same value).

## I3 — `unpaid` omitted from accrual window → **align the status filter**
`subscription_nominal_for_window` filters `["active","trialing","past_due"]` but the push includes `unpaid`. During a failed-payment window the access/seat charge is still accrued but nominal drops to 0 → understated margin. Change the filter to `["active","trialing","past_due","unpaid"]` (matches the push basis exactly).

---

## Test strategy (all MOCKED — no network; patch `stripe.*` via `stripe_call`, assert on call kwargs)
- **C1:** a postpaid customer WITH a subscription → assert every `InvoiceItem.create` has **no** `subscription=` kwarg, and a standalone `Invoice.create`+`finalize_invoice` is issued with `rec.stripe_invoice_id == inv.id`. (Update/retire the old Wave-4 tests that asserted the pin.)
- **C2:** a line of `1_234_567` micros → no `StripeFatalError`, `rec.status=="pushed"`, `InvoiceItem.create` got `amount=123`, `rec.residual_micros==4_567`; a second period folding the carry asserts exact arithmetic + the `postpaid.residual_carried` log; conservation holds.
- **I1:** `Price.create` mock kwargs `currency=="eur"` for a EUR tenant; a mismatched-currency push raises `StripeFatalError` (no `InvoiceItem.create`).
- **I2:** seat item `unit_amount_micros=2_000_000`, qty 2→5 with a `1_000_000` access item → `set_seats(5)` → `mirror.amount_micros == 11_000_000`, `mirror.quantity == 5`, `last_synced_at` advanced — no webhook.
- **I3:** an `unpaid` sub → `subscription_nominal_for_window` returns the prorated nominal (>0).

## Build sequence (quick + independent first, then verify)
1. **C2** (residual field + migration + floor/carry loop + audit) — removes the silent-stall blocker.
2. **I3** (one-line status filter).
3. **I2** (mirror refresh in set_seats).
4. **I1** (currency thread + assert).
5. **C1** (drop pin+guard, always standalone; update tests).
6. **Capstone update + final verification** (fresh-DB for the residual migration; full platform + SDK; update the Wave-4 capstone's pin assertion to the standalone-always reality).

## Explicitly deferred to Wave 5
True single consolidated invoice (owned-finalize `auto_advance=false` + manual finalize, or event-driven pin-to-draft via `invoice.created`); the AR-visibility loop (invoice.paid/payment_failed/voided per-axis reconcile, hosted_invoice_url, /me usage+subscription invoices). The C1 standalone-usage model is the honest interim: correct money, two documents.
