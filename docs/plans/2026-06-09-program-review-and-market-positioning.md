# UBB — Program Review & Honest Market Positioning (multi-agent, code-grounded)

**Date:** 2026-06-09
**Method:** 39-agent workflow — 8 subsystem capability maps from source → 5 adversarial review dimensions (each finding independently verified) → 7 code-grounded platform comparisons → synthesis. 17 findings survived verification (1 Critical, 10 Important, 6 Minor).
**Controller verification:** the Critical (#1) was independently re-confirmed against the actual code by reading `apps/platform/events/tasks.py:51`. It is **pre-existing outbox infrastructure**, not introduced by Stages A–E/D.

---

## PART 1 — Honest Market Positioning

### Verdict
UBB is **not a usage-billing engine and should stop being benchmarked as one.** Against every dedicated platform (Stripe Billing, Metronome, Orb, Lago, Amberflo, m3ter, OpenMeter) it loses a head-to-head on rating richness, scale, multi-currency, credits/entitlements, and invoicing/AR — *by design*. It occupies an under-served adjacent slot: a self-hosted, source-owned **"COGS-vs-revenue margin + prepaid spend-control layer that sits in FRONT of Stripe."** In that slot it is differentiated and, in places, more rigorous than the commercial leaders. Every comparison converged on the same word: **complementary, not competitive.** The risk: the gaps a buyer probes first (tiered pricing, currency, hard enforcement, throughput) are UBB's weakest areas — so it must win on margin + money-safety or not at all.

### Defensible differentiators (skeptically claimed)
1. **Two-card COGS-vs-revenue model with persisted per-event `pricing_provenance` — STRONGLY DEFENSIBLE.** Independent `provider_cost_micros` (COGS) + `billed_cost_micros` (revenue) on each immutable event, plus a full provenance trail (engine_version, cost/price source, per-metric rate_card_id, uncosted_metrics). Revenue-centric engines (Stripe/Orb/Lago/OpenMeter) structurally don't do this; only m3ter/Amberflo do cost attribution and even they don't persist per-event explainability. The single strongest claim.
2. **Earned/accrual-basis margin with `revenue_mode` disambiguation — DEFENSIBLE** (model is differentiated; implementation has the accumulator gaps below).
3. **Pooled-money / per-seat-control hierarchy with event-time owner pinning — DEFENSIBLE with a caveat** (postpaid rolls seats up by `parent_id` regardless of topology, while the money resolver pools only when `topology=='pooled'` — divergent rollup rules).

**Honest down-grades:** the advisory gate is a *positioning* differentiator, not a capability one (leaders offer harder enforcement); the exactly-once wallet ledger is excellent but *table stakes* for a money mover — notable only because it's self-hosted + auditable.

### Parity (UBB vs the field)
| Capability | Position | Read |
|---|---|---|
| Metering (idempotent immutable events) | **AT PAR** on correctness; behind on throughput (sync Postgres vs ClickHouse/Kafka at 250K–1M ev/s) |
| Pricing/rating | **BEHIND (badly)** — only per_unit + flat; `tiers` is dead code; no graduated/volume/package/commitments/minimums |
| Prepaid/credits/wallets | **MIXED** — ahead on money-safety engineering; behind on credit grants/expiry/rollover/commitments/multi-balance |
| Gating/spend-control | **AHEAD on surface, BEHIND on hardness** — explicit pre-call gate + per-seat caps for agent control, but advisory/best-effort; bounds overspend, doesn't prevent it |
| Reconciliation/ledger integrity | **AHEAD in scope** — convergent repairing reconciles; behind on operational completeness (detect-only drift, accumulator not reconciled, full-table hourly) |
| Invoicing/Stripe push | **BEHIND** — a thin usage-line pusher; no tax/discounts/proration/credit-notes/multi-currency; one-directional (never reads Stripe back) |
| Accounts/seats | **AHEAD (differentiated)** — pooled-money/per-seat with event-time pinning; caveat: invariants only in one API handler, one-level, rollup divergence |

### Where UBB is genuinely behind — and the cost to close
1. **Pricing breadth (#1 gap)** — implement the stubbed `tiers` (graduated+volume), package, minimums/commitments. Bounded work; schema headroom exists. Without it, tenants must precompute `billed_cost_micros`, hollowing the engine.
2. **Multi-currency/FX** — currency-exact card resolution silently yields 0 COGS on a missing card; USD hard-coded; reconciles sum micros currency-blind. At minimum *reject* (don't silently zero) mismatches.
3. **Hard real-time enforcement** — gate is advisory; unbounded negative balance; `estimated_cost` ignored at gate; `max_concurrent_requests` dead. **The consultant explicitly endorsed advisory-only**, so this is a positioning choice — but it must be *documented* (UBB bounds, not prevents, overspend).
4. **Auto-repair of drift + aggregate convergence** — `reconcile_wallet_balances` detects but only logs; the `CustomerCostAccumulator` feeding margin is never reconciled to the ledger and assigns periods by wall-clock (not `effective_at`) → late events land in the wrong month. **Highest-leverage fix — it undermines the margin differentiator.** The pattern is already proven (wallet↔ledger); just not applied here.
5. **Bidirectional Stripe reconcile + trailing usage** — postpaid never reads Stripe back; late/backdated usage on a pushed period is dropped; `'failed'` declared-but-never-set.
6. **Operational/scale** — full-table hourly reconciles (no sharding/watermark); the Critical outbox bug; webhook delivery lacks per-endpoint idempotency/auto-disable; DLQ alerting is only a log line.
7. **Negative-margin guard** — for a margin product, no write-time `provider_cost <= billed` warning is a notable omission.

### Circling back to the consultant (did Stages A–E+D close the ~80% gaps?)
- **(1) Out-of-band, best-effort enforcement — CONFIRMED, correctly implemented.** Matches the prescription exactly.
- **(2) Ledger is the record you reconcile against, not the gate — CONFIRMED.** Postgres = truth; Redis expendable/degrades-open; balance is a cached SUM.
- **(3) Design for tolerable overspend; bound + observe — PARTIALLY CLOSED.** The bound is explicit (`min_balance` + ≤1 reconcile interval). **"Make it observable" is the weak point** — drift detected not repaired/alerted; no per-call gate-decision audit; no DLQ/lag metrics. Real remaining distance.
- **(4) TigerBeetle-vs-Stripe back-pocket — STRUCTURALLY READY, NOT NEEDED YET.** Correctly did *not* adopt TigerBeetle; the pooled hot-balance case is handled on Postgres via the `(wallet, idempotency_key)` constraint; `billing_owner_id` pinned on the event is the seam a dedicated ledger would later slot into. The full-table hourly SUM is the eventual scaling trigger.

**Did the named gaps close?** Pricing-cards: reinstated but thin (card mechanism closed; richness didn't — half). Money-safety (C): closed + rigorous (most complete stage). Overage/reconciliation (D): mostly closed, but cached-balance auto-repair + margin-accumulator convergence were *not* — the same reconcile discipline wasn't applied to those two derived aggregates (asymmetric).

**Bottom line:** the architecture is *sound for the stated positioning* and largely matches the consultant's prescription; the program moved meaningfully past 80% on money-safety + hierarchy. Remaining distance, in priority: (a) margin accumulator non-convergence (attacks the crown jewel — fix first); (b) detect-only drift contradicts "make leakage observable"; (c) the outbox `select_for_update` bug; (d) unify the pooled-vs-allocated rollup behind one shared resolver; (e) thin pricing / single-currency / one-directional Stripe reconcile are positioning-consistent deferrals. **Sell UBB as exactly what it is — a front-of-Stripe margin-and-spend-control layer — and don't chase Metronome/Orb/m3ter on rating breadth; that race is lost and not worth running.**

---

## PART 2 — Consolidated Code Review

### CRITICAL
**1. `process_single_event` calls `select_for_update` outside a transaction — crashes in production, masked by tests.** `apps/platform/events/tasks.py:51`. No enclosing `transaction.atomic()`; under autocommit (Celery, production) this raises `TransactionManagementError` before any status transition, caught only by `except OutboxEvent.DoesNotExist`. Net effect: **the live outbox path never runs in production** — live drawdown, auto-top-up BalanceLow, suspensions, budget alerts never fire; only the Stage-C/D repairing reconciles eventually apply wallet/top-up money. Tests pass because `@pytest.mark.django_db` provides an ambient transaction; the one `transaction=True` test mocks the function. **Fix:** wrap the SELECT + status-transition body in `with transaction.atomic():` (also makes the `skip_locked` lock span the status check). Add a `@pytest.mark.django_db(transaction=True)` un-mocked regression test. *(Controller-verified; pre-existing infra.)*

### IMPORTANT (money-path / security first)
**2. Partial/multiple Stripe refunds silently lose money.** `connectors/stripe/webhooks.py:260-302`. `handle_charge_refunded` debits cumulative `amount_refunded` but keys on `stripe_refund:{charge_id}` (one per charge); each partial refund is a separate event, so refund #2+ finds the existing row and returns early → never debited. Same shape in `handle_charge_dispute_closed` (`dispute:{charge_id}`). **Fix:** iterate `charge.refunds.data`, one txn per `stripe_refund:{refund.id}` with that refund's amount.

**3. Cross-tenant / cross-customer Run IDOR in `record_usage`.** `metering/usage/services/usage_service.py:71`. Caller-supplied `run_id` is passed to `RunService.accumulate_cost`/`kill_run` which `get(id=run_id)` with **no tenant/customer filter** → an authed tenant can inflate/kill another tenant's run (billing corruption + DoS); within-tenant, customer A drives customer B's run. Sibling `close_run` *does* scope by tenant. **Fix:** `get_object_or_404(Run, id=run_id, tenant=..., customer=...)`; 404 on foreign/missing.

**4. `(tenant, external_id)` unique ignores soft-delete.** `platform/customers/models.py:36-43`. No `deleted_at IS NULL` condition → re-onboarding a churned `external_id` 409s permanently; the OneToOne soft-deletable Wallet/AutoTopUpConfig breaks `get_or_create` on a restored customer. **Fix:** partial constraint on `deleted_at IS NULL`; use `all_objects`+`restore()`.

**5. Stripe usage line-item idempotency key from a lossy slug can collide → drop a billed line.** `invoicing/services/postpaid_service.py:117-128`. `usage-item-{rec.id}-{slug}` folds punctuation + truncates to 40 chars; colliding labels → Stripe returns the cached item, second line never invoiced, local ledger records both → silent under-billing. **Fix:** key on index or `sha256(label)[:16]`.

**6. Soft-deleting a seat drops its in-period usage from the consolidated business invoice.** `invoicing/services/postpaid_service.py:19-31`. `seats.all()` + the close's `Customer.objects.filter` both exclude soft-deleted; the seat's immutable billable `UsageEvent`s are neither invoiced nor rolled to the parent → silently uninvoiced revenue. **Fix:** aggregate via `Customer.all_objects` for closed periods.

**7. Run cost ledger double-counts on concurrent idempotent replay.** `metering/usage/services/usage_service.py:58-88`. `accumulate_cost` runs outside the `UsageEvent` create savepoint; a concurrent same-key retry increments the run twice (loser's increment isn't rolled back) → corrupts hard-stop accounting / false run kills. **Fix:** increment inside the create savepoint, or only after a winning create, or key on `usage_event_id`.

**8. Webhook SSRF guard is create-time only (TOCTOU / DNS rebinding).** `platform/events/webhooks.py:68`. No revalidation at delivery; up to 500 chars of an internal endpoint's body persisted on the attempt → blind-SSRF exfil. **Fix:** re-validate + pin the resolved IP at delivery, or egress-proxy/network-policy.

**9. No true-concurrency tests — every exactly-once invariant is exercised only sequentially.** `handlers.py:60-68` (representative). Zero threading/`TransactionTestCase`-with-threads in the suite; the `IntegrityError`-handling the whole money-safety story rests on is unverified and can regress green. **Fix:** add real two-thread races for the drawdown, `apply_topup_credit`, and reconcile-vs-live.

**10. Partial-refund path untested; the single-refund test gives false confidence.** `api/v1/tests/test_webhooks.py:424-453`. Counterpart of #2. **Fix:** test two sequential partial refunds net to the correct cumulative deduction.

**11. `reconcile_postpaid_usage` (re-push after partial failure) has zero tests.** `invoicing/tasks.py:77-92`. Safe only because Stripe idempotency derives from `rec.id` — the exact unproven property. **Fix:** test reclaim-of-stuck, retry-of-failed, leave-fresh-alone.

### MINOR
**12.** Outbox dedup is check-then-act → concurrent dispatch transiently double-counts the shared tail (platform-fee F()-incr, budget Redis incr); **self-heals** before any bill via `reconcile_tenant_billing_periods` + budget `reconcile_customer` (re-graded down). Falls out of the #1 fix. `events/dispatch.py:60`.
**13.** Unvalidated `period` param (`split("-")`) and missing-`run_id` → 500 instead of 4xx. `api/v1/billing_endpoints.py:565`.
**14.** `Customer.min_balance_micros` is an orphaned shadow field (live threshold is on `CustomerBillingProfile`); admin edits silently ignored. `customers/models.py:29`.
**15.** Lock-order docstrings disagree on whether `Run` is in the ordering (no live deadlock; future-drift risk). `core/locking.py:4`.
**16.** `Wallet.deduct()/.credit()` are non-idempotent dead code used only by tests; two reconcile tests assert nothing. `wallets/models.py:31-66`.
**17.** Tests share the dev/Celery Redis DB (db 1) and `cache.clear()` (FLUSHDB) it. `config/settings.py:107-115`. **Fix:** dedicated test Redis index.

### Overall verdict
The **core money-handling architecture is genuinely well-engineered and, on the write path, ship-quality in design**: exactly-once anchored on DB unique constraints (not app logic); immutable append-only `UsageEvent` ledger with independent COGS/revenue + persisted provenance; transactional outbox + convergent self-healing reconciles keyed on natural ids with grace>retry-horizon reasoning; disciplined product boundaries; solid Stripe integration (deterministic keys, signature+id dedup, I/O outside locks). **But not ship-ready yet:** the Critical (#1) means the primary dispatcher crashes in production while the suite can't see it. **Must-fix before scale, in order:** #1 (outbox atomic) → #2/#10 (per-refund keying) → #3 (run IDOR) → #5/#6 (postpaid revenue leaks) → #4 (soft-delete uniqueness). The rest is scale-and-observability hardening, not foundational rework.
