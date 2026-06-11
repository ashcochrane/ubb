# UBB Competitiveness Program (Stages F0–F6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four verified money/launch bugs on branch `tl-changes-05-06-26`, then build the four verified competitiveness gaps (tiered pricing, backfill + batch, credit grants, sandbox) plus high-leverage parity items — while preserving the verified differentiators (per-event COGS/margin, synchronous spend enforcement, run-kill primitive).

**Architecture:** Every stage keeps the platform's established invariants: integer-micros money, exactly-once via DB unique constraints (`(wallet, idempotency_key)`, `(tenant, customer, idempotency_key)`), pricing at the `record_usage` choke point, transactional outbox + self-healing reconciles, tenant-scoped everything. New mechanisms (resumable invoice push, residual ledger, period counters, grant lots, sibling sandbox tenants) are all expressed in those same primitives.

**Tech Stack:** Django 5 / Postgres / Redis / Celery (beat), stripe-python ≥15 (Basil pin), django-ninja API, pytest(-django), httpx SDK.

**Provenance:** every §0 verdict comes from a 20-agent re-verification of both consultant reports against the code (every anchor re-opened); every stage distills a file-anchored design produced against the live code; the assembled plan then survived a 3-lens adversarial panel (money-safety, feasibility/anchors, scope/sequencing) whose 5 must-fix and 8 should-fix findings are incorporated inline (marked "refuter-corrected/confirmed"). Migration numbers were verified free against the actual app directories (invoicing next=0005, usage next=0022, pricing next=0009, wallets next=0005).

---

## §0 What this plan is based on — verification verdict

A 20-agent re-verification of both consultant reports against the code (every claim re-opened, every anchor re-read). Summary of where the consultants were right, wrong, and what they missed:

| # | Consultant claim | Verdict | Correction / addition |
|---|---|---|---|
| 1 | "Bounded postpaid retry (B3)" is false; unbounded retry → duplicate finalized invoice past Stripe's ~24h key window | **CONFIRMED, and worse** | `tasks.py:98-99` retries `pending`+`failed` forever; the 24h bound is gated on `pending` only (`:104`) and `updated_at` is refreshed by every claim (`postpaid_service.py:86-87`). A Phase-2 failure flips the row BACK to `pending` (`:99`), so even `failed` doesn't stick. Nothing is persisted between claim and Phase-3; `stripe_invoice_id` is only saved after finalize (`:113-117`). **New finds:** (a) `reconcile_postpaid_usage` re-pushes `rec.customer` verbatim — a stale **seat**-keyed row + the business-keyed row can both bill the same usage (double-bill); (b) `skipped` rows (`not_charge_ready`, `no_stripe_customer`) are **never** retried → silent permanent revenue loss. |
| 2 | Branch silently drops main's SDK retry work; merge-base `5c9bcdf`; 4 conflicts | **REFUTED as framed** | `main == origin/main == c5a1a0e`, an **ancestor** of this branch (175 ahead, 0 behind). The 4 retry commits live only on `origin/feat/ubb-ui-dashboard`. A PR today deletes nothing. The real issue is bigger: that branch is a **fork** — its own pricing schema (Card/Rate/Group vs our RateCard), colliding migration numbers (pricing 0005-0008, usage 0016-0020), Clerk auth, camelCase API. SDK retry should be *ported* (3 clean cherry-picks + hand-derived wiring; the pick order is ff56cbd → 8a9ae58 → 4cd519b; 93423c8 is import-broken at its own commit and must be re-derived). |
| 3 | Stage-2 margin implementation doc is an un-bannered landmine | **CONFIRMED** (line numbers exact) | Plus 4 more un-bannered docs prescribing the deleted `ProviderRate` (worst: `2026-02-11-architecture-audit-action-plan.md:487-516`, prescriptive with backfill code). Better fix for the dead methods: **delete them** — `revenue_for_window`/`stripe_revenue_for_window` have zero callers anywhere, not even tests. `ubb-ui/` untracked repo: **REFUTED** — no such directory exists. |
| 4 | Basil pin `"2025-03-31"` likely invalid; live test doesn't pin the version | **CONFIRMED, and worse** | Installed stripe 15.2.0's canonical list contains only `"2025-03-31.basil"`; bare `2025-03-31` appears nowhere as a version. The SDK sends the header **verbatim, unvalidated** — production sends a likely-invalid `Stripe-Version` on every call; the live test runs on the SDK default `2026-05-27.dahlia` (empirically verified: `stripe_service` is not on its import chain), under which `Invoice.payment_intent` doesn't even exist. Ordering trap: `stripe_service.py:12` sets `stripe.api_key` at import — the test must import the service **before** setting its own key. |
| 5 | Analytics: non-sargable `__date` everywhere; `jsonb_path_ops` can't serve `has_key`; Python row-loops; strict-coverage $0 hole | **CONFIRMED (A1 partial)** | "Every" is wrong — 2 sites already sargable (`queries.py:141-142`, `wallets/tasks.py:67`); the ~15 analytics/margin/postpaid/budget sites are not. Safe rewrite proven: `TIME_ZONE="UTC"`, `USE_TZ=True`, zero `timezone.activate()` → `__date__gte=d` ≡ `__gte=<UTC midnight>`. **New finds:** margin list/summary N+1 (O(2N) revenue queries), `compute_business` O(seats×5), `usage_analytics` ~13 sequential full-window scans with optional dates. |
| 6 | Residual chain lock-free; AR over-blocks `uncollectible→paid`; only 2 concurrency tests | **CONFIRMED** | Out-of-order push double-counts P(n-1)'s residual AND strands P(n)'s forever (chain reads `order_by("-period_start").first()`). The hourly backstop loud-logs legal `uncollectible→paid` as a "regression" (`tasks.py:188-192`) while the webhook path writes `paid_at` without applying the status — two different wrong behaviors for the same fact. |
| 7 | Tests run with "the real `sk_test_` key from .env" | **PARTIAL** | The .env value is the 13-char placeholder `sk_test_dummy` — a missed patch 401s loudly, it does not silently mutate a Stripe account. Residual risk is real: `load_dotenv()` doesn't override shell env, so an exported real key would win silently. No autouse guard exists (confirmed). |
| 8 | ~17 cross-product imports; boundary dead | **PARTIAL (direction right)** | No counting rule yields 17. Actual: **14** unsanctioned import statements in `apps/` (+2 `apps→api` layer inversions; +9 sanctioned `queries.py` crossings). At main: **0** unsanctioned. The lazy-import circular-dep workaround has already been copy-pasted once (`invoicing/tasks.py:130-139`) — the erosion is propagating. |
| 9 | Four competitive gaps: tiers, backfill, grants, sandbox | **ALL CONFIRMED precisely** | With ready compose points: dead `tiers` JSONField (`pricing/models.py:57`); unused `as_of` hook in `PricingService.price` (`:38-40`); unused `ubb_test_` prefix (`tenants/models.py:101`); `CustomerCostAccumulator` unique-row + IntegrityError-retry pattern to clone for counters. |
| 10 | USD hardcoded on every charge path | **PARTIAL** | 4 of 6 paths hardcode; postpaid + plan provisioning already use `tenant.default_currency` (not writable via API). Cents (`*/ 10_000`) assumptions pervasive in both directions — zero-decimal currencies need a minor-unit helper. **New find:** outgoing webhook signatures have no timestamp binding → replayable forever; mixed-currency wallet debits unchecked; `"USD"` vs `"usd"` case inconsistency. |

**Bottom line:** consultant 1 was right on 3 of 4 must-fixes and wrong on the merge story; consultant 2's gap list holds completely. The single most dangerous artifact in the repo today is the postpaid retry loop (claim 1) — it is the opposite of its own comment and a genuine double-billing vector.

---

## §1 Strategy — what we protect, what we build, what we refuse

**The verified moats (do not regress, mention in every demo):** native per-event COGS + margin (absent in Metronome/Orb/Lago); synchronous spend enforcement (pre-check gate, enforcing caps, balance-floor suspension); the Run kill primitive (unique in the field); source-owned deployment on the tenant's own Stripe.

**The build list (this program):** the 4 must-fix bugs (F0), money/scale/boundary hardening that makes "absolutely perfect at what we have" true (F1–F3), then the 4 competitiveness gaps (F4) and demo-visible parity (F5).

**Deliberate non-goals (state openly in sales conversations; do NOT build):**
- Tax engine — `automatic_tax` flag passthrough only (F5.3); registration/filing is Stripe Tax's job per `docs/architecture/positioning.md`.
- Dunning/email — Stripe owns dunning for invoices; UBB emits webhooks; the tenant owns end-customer comms. No `EMAIL_BACKEND`, ever, in this program.
- Rev-rec / ASC 606, warehouse syncs, CRM/ERP integrations, SOC 2 tooling, SSO/RBAC — post-pilot.
- Volume pricing (whole-quantity re-rate) — not incrementally stable; deferred with rationale in F4.1. Graduated + package cover Stripe's own tier surface.
- Multi-currency FX — single currency per tenant only (CUR-1 in F5.6); no FX anywhere.
- Express/platform-of-record Stripe — decided, documented, stays rejected.

**Sequencing rationale:** F0 is the PR gate (money bug + launch gate + honesty fixes). F1/F2 before F3 so the boundary-contract functions are written once with sargable filters. F4.1 (tiers) before F4.2 (backfill) because backfill flips the tier-counter period source to effective-month. F4.4 (sandbox) last in F4 — it threads `api_key` through 23 `stripe_call` sites and should land after the postpaid/AR churn settles. F5 items are independent slices, cherry-pick by demo value.

---

## §2 Cross-design decision log (conflicts found and resolved)

1. **`failed` semantics.** Adopted: `failed` = *transient, attempted-and-errored, retried under a bound*; new `failed_permanent` = terminal (attempts ≥ 8 OR wall-clock > 20h from `first_attempted_at`, both inside Stripe's 24h key window). The alternative "make `failed` terminal by dropping it from the reconcile queryset" is **superseded** — with resume-not-recreate, bounded retry is strictly better than stop-on-first-error.
2. **Residual carry vs resume.** `carry_in_micros` is pinned on the claim row in Phase 1 (F1.1) and survives retries; a `failed_permanent` row keeps its pinned carry parked — never auto-returned to the ledger (the cent may already be on a finalized invoice). Manual adjudication via runbook + `repush_usage_invoice`.
3. **Tier counter key.** `(tenant, customer, lineage_id, period_start)` — lineage keying (not `metric_name`) so per-customer overrides, dimensional variants, and versions each get their own ladder, and version bumps (same lineage) keep ladder continuity. `period_start` = calendar month of `effective_at` (== arrival month until F4.2 lands; F4.2 flips the source and adds the closed-period 422 that keeps invoiced ladders frozen).
4. **Dead code: delete, don't banner.** `RevenueService.revenue_for_window` + `stripe_revenue_for_window` (`revenue.py:40-57`) have zero callers anywhere → delete outright (incl. the now-unused `Sum` import), and banner the stage-2 implementation doc anyway (it tells a reader to *re-create* them).
5. **Single-flight push.** `push_customer_period` early-returns on `status in ("pushed", "pushing")` — a fresh `pushing` row is an active claim; the 30-min stale reclaim is the designed recovery. Lands in F0.1 (cheap, kills the same-period double-create race).
6. **F2 before F3 ordering.** The five new `metering/queries.py` contract functions (F3) must be written with the **sargable** half-open ranges from F2, not the old `__date` casts.
7. **Consolidated invoice (F5.5) builds on F0.1.** It reuses the persist-target-id-while-`pushing` machinery and the unchanged `usage-item-{rec.id}-{i}` keys; do not start F5.5 before F0.1 is merged.
8. **Webhook `livemode` filter (F4.4)** is centralized in one helper Q-filter used by every `event.account` lookup, so new handlers can't forget it.

---

## Stage F0 — Pre-PR gate (~5 days). The branch must not be PR'd before this stage is green.

### Task F0.1: Bounded + resumable postpaid Stripe push

The core invariant set:
- **I1** — at most one finalized Stripe invoice ever exists per (billing owner, period), including across idempotency-key expiry.
- **I2** — resume-not-recreate: `stripe_invoice_id` persists the moment the invoice exists; every retry is retrieve-first.
- **I3** — automatic retries are bounded by `push_attempts` (8) AND wall-clock (20h from `first_attempted_at`), both inside Stripe's 24h key window; then terminal `failed_permanent` + outbox alert.
- **I4** — belt-and-braces: before any create, `Invoice.list(customer=…, created≥…)` with client-side `metadata["usage_invoice_id"]` match (deterministic; `Invoice.search` has freshness lag).
- **I5** — owner-first keying: the row, the unique constraint, and the `stripe_customer_id` check all key on `Customer.resolve_billing_owner()` (kills the seat/business double-bill).

**Files:**
- Modify: `ubb-platform/apps/billing/invoicing/models.py` (CustomerUsageInvoice: `push_attempts` PositiveIntegerField default 0, `first_attempted_at` DateTimeField null, `last_attempt_error` TextField blank default `''`, `push_phase` CharField(20) choices `''|invoice_created|items_pinned|finalized` default `''`; add `('failed_permanent','Failed permanent')` to `USAGE_INVOICE_STATUS` at `:46-49`; **widen `status` max_length 10→20** at `:60`)
- Create: `ubb-platform/apps/billing/invoicing/migrations/0005_bounded_resumable_push.py` (schema + data migration, below)
- Modify: `ubb-platform/apps/billing/invoicing/services/postpaid_service.py` (owner-first resolve; cap + claim; sticky `failed`; resume rework of `_push_to_stripe`)
- Modify: `ubb-platform/apps/billing/invoicing/tasks.py` (delete the broken 24h block + false comment at `:100-112`; keep 30-min stale reclaim `:96-97` and `status__in=["pending","failed"]` selection `:98-99`)
- Modify: `ubb-platform/apps/platform/events/schemas.py` (new event), `ubb-platform/config/settings.py` (`POSTPAID_PUSH_MAX_ATTEMPTS=8`, `POSTPAID_PUSH_MAX_AGE_HOURS=20`)
- Create: `ubb-platform/apps/billing/invoicing/management/commands/repush_usage_invoice.py`
- Modify: `ubb-platform/api/v1/billing_endpoints.py:547-575` + `api/v1/schemas.py` `UsageInvoiceOut` (expose `push_attempts`, `last_attempt_error`)
- Test: `ubb-platform/apps/billing/invoicing/tests/test_postpaid_resume_bounds.py` (new)

- [ ] **Step 1: Model + settings + event schema.** Add the four fields + status literal + width change; `UsageInvoicePushFailedPermanent` frozen dataclass (`EVENT_TYPE = "usage.invoice_push_failed_permanent"`; fields `tenant_id, customer_id, period_start, push_attempts:int=0, last_error:str="", stripe_invoice_id:str=""`) next to `UsageInvoicePushed` (`schemas.py:188`). **Register the event type in `apps/platform/events/apps.py:13-32`** — unregistered types dispatch to zero handlers (`registry.py:20-21`) and the alert silently never reaches webhooks; add a test asserting `registry.get_handlers("usage.invoice_push_failed_permanent")` is non-empty. Run `makemigrations` → `0005`. Verify `manage.py check` clean.
- [ ] **Step 2: Owner-first keying (I5).** At the top of `push_customer_period` (`postpaid_service.py:61`), before the `get_or_create` at `:66-68`:
```python
customer = customer.resolve_billing_owner()
```
The defensive re-resolve at `:137` becomes a no-op; keep it.
- [ ] **Step 3: Bounded claim (I3).** Inside the Phase-1 atomic block, after the early return (now `if rec.status in ("pushed", "pushing"): return rec`):
```python
if rec.status == "failed_permanent":
    return rec  # idempotent, no re-alert
if rec.status in ("pending", "failed") and (
    rec.push_attempts >= settings.POSTPAID_PUSH_MAX_ATTEMPTS
    or (rec.first_attempted_at
        and timezone.now() - rec.first_attempted_at
            > timedelta(hours=settings.POSTPAID_PUSH_MAX_AGE_HOURS))
):
    rec.status = "failed_permanent"
    rec.save(update_fields=["status", "updated_at"])
    write_event(UsageInvoicePushFailedPermanent(
        tenant_id=str(tenant.id), customer_id=str(customer.id),
        period_start=period_start.isoformat(),
        push_attempts=rec.push_attempts,
        last_error=rec.last_attempt_error[:500],
        stripe_invoice_id=rec.stripe_invoice_id,
    ))
    logger.error("billing.usage_push_failed_permanent", extra={...})
    return rec
rec.push_attempts += 1
rec.first_attempted_at = rec.first_attempted_at or timezone.now()
# add both to the update_fields of the claim save at :86-87
```
- [ ] **Step 4: Sticky transient failure.** Replace the Phase-2 exception revert (`:99`) with:
```python
CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(
    status="failed", last_attempt_error=repr(exc)[:500])
```
- [ ] **Step 5: Resume-not-recreate (I2/I1/I4).** Rework `_push_to_stripe` (`:130-178`):
  (a) if `rec.stripe_invoice_id`: `inv = stripe_call(stripe.Invoice.retrieve, id=…, stripe_account=…)`;
  (b) else `inv = _find_existing_invoice(rec, owner, connected)` — `stripe.Invoice.list(customer=owner.stripe_customer_id, stripe_account=…, created={"gte": epoch(rec.created_at - 1 day)}, limit=100)` auto-paged, client-filter `metadata.get("usage_invoice_id") == str(rec.id)`, **skipping `status == "void"` invoices** (so a void-rebill via Step 8 can mint a replacement);
  (c) if still none: `stripe.Invoice.create` with the **existing** key `usage-invoice-{rec.id}` PLUS `metadata={"usage_invoice_id": str(rec.id), "tenant_id": …, "period_start": …}`;
  (d) **Phase 2a — immediately persist:** `CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(stripe_invoice_id=inv.id, push_phase="invoice_created")`;
  (e) if `inv.status == "draft"`: list existing items (`stripe.InvoiceItem.list(invoice=inv.id, …)` auto-paged), index by `item.metadata.get("line_index")`, create only missing lines with the existing keys `usage-item-{rec.id}-{i}` + `metadata={"usage_invoice_id": str(rec.id), "line_index": str(i)}`; `update(push_phase="items_pinned")`; finalize with the existing key; `update(push_phase="finalized")`;
  (f) if `inv.status in ("open", "paid", "uncollectible")`: **adopt** — zero Stripe writes, recover item ids from the list (blank fallback allowed by `models.py:84`), `update(push_phase="finalized")`, proceed to Phase-3 recording;
  (g) if `inv.status == "void"` or deleted: `logger.error` + raise `StripeFatalError` (counts toward the cap → `failed_permanent` → manual).
- [ ] **Step 6: Reconcile cleanup.** Delete `tasks.py:100-112` (broken bound + false "terminal" comment — the bound now lives in the service and fires for ALL callers). Update the docstring: `failed` = transient-retried, `failed_permanent` = terminal.
- [ ] **Step 7: Migration 0005 data rules (I6), applied in this order.** (c) FIRST: `pending/failed` rows keyed on a pooled **seat** (`account_type='seat'`, parent pooled) → `status='skipped'`, `skip_reason='seat_superseded'`. (a) THEN: **all remaining legacy `failed` AND `pending` rows** → `failed_permanent` with `last_attempt_error='migrated: pre-metadata era — verify in Stripe (customer + period + amount) before repush'`. Rationale (refuter-confirmed): nothing was persisted between claim and Phase 3 under old code, so an attempted `pending` row (Phase-2 crash reverted at `:99`) is indistinguishable from a never-attempted one, its Stripe invoice — possibly finalized — has **no metadata** for the I4 lookup to find, and old reconcile refreshed `updated_at` hourly so such rows are typically already past the 24h key window. Quarantining never-attempted rows costs one manual repush each; resuming an attempted one costs a duplicate finalized invoice. Safe-by-default wins.
- [ ] **Step 8: Manual recovery.** `repush_usage_invoice <row-id>` management command: resets `push_attempts=0`, `first_attempted_at=None`, `last_attempt_error=''`, `status='pending'`. **Refuses rows whose `customer.resolve_billing_owner() != customer`** (a seat-keyed row can never be transitioned by the owner-first service — it would loop `pending` forever). **Duplicate-proof only for invoices created post-F0.1** (metadata present); for migrated legacy rows the operator MUST first search Stripe by customer + period + amount and record any found `stripe_invoice_id` on the row. Add `--rebill-void`: clears `stripe_invoice_id`/`push_phase` so a deliberately-voided invoice can be replaced (the list-match skips void per Step 5(b); within the 24h key window also rotate the create key with a repush-generation suffix).
- [ ] **Step 9: Skipped-row recovery (closes the silent-revenue-loss find).** In `reconcile_postpaid_usage`, additionally select `status='skipped', skip_reason__in=('not_charge_ready','no_stripe_customer')` rows whose precondition now holds (tenant charge-ready / owner has `stripe_customer_id`), flip them to `pending` — **excluding pooled-seat-keyed rows** (those flip to `seat_superseded` instead; a flipped seat row would loop forever since the owner-first service never writes it). Service belt: in Phase 1, if the passed customer ≠ resolved owner and a row exists keyed on the passed customer for this period, mark it `skipped/seat_superseded` in the same transaction. `skip_reason='no_usage'` and `'seat_superseded'` stay terminal.
- [ ] **Step 10: Tests** (`test_postpaid_resume_bounds.py`, mock pattern from `test_postpaid_hardening.py:26-46` + added `Invoice.retrieve`/`InvoiceItem.list`/`Invoice.list` patches):
  - crash-pair matrix: claim→create, create→persist (assert `Invoice.create.call_count == 0` on retry via the metadata list match), persist→items, items→finalize (`InvoiceItem.create.call_count == 0`), finalize→record (**R4 core**: retrieve returns `open` → zero create/item/finalize calls, Phase 3 records);
  - retry-after-key-expiry: `failed_permanent` row + `repush_usage_invoice` → resume only, `Invoice.create.call_count == 0`;
  - cap tests: attempts == 8 → terminal, exactly one outbox event across two passes; `first_attempted_at = now-21h` → terminal before any Stripe call;
  - reconcile selection: `failed_permanent`/`seat_superseded` untouched; stale `pushing` reclaim preserves `stripe_invoice_id`/`push_phase`;
  - seats: pooled seat passed directly → business-keyed row only; blank-seat-key + owner-has-key → NOT skipped; close task + service produce exactly one row per (owner, period);
  - migration assertions (incl. legacy `pending` → `failed_permanent`, seat rule (c) winning over rule (a) for seat-keyed `failed` rows); skipped-row recovery (charge-ready flip; seat rows excluded); repush refusal on seat-resolving rows; `--rebill-void` mints a replacement while the plain command on a void row terminal-fails again.
- [ ] **Step 11: Run** `pytest apps/billing/invoicing -q` then the full platform suite. Commit: `fix(postpaid): bounded + resumable push — persist-at-create, retrieve-first resume, attempts/wall-clock cap, owner-first keying`.

**Open item to verify against a Stripe test account when the live gate runs:** Basil shape of `InvoiceItem.list(invoice=…)` + item metadata round-trip (fallback: `Invoice.retrieve(expand=["lines"])`).

### Task F0.2: Fix the Basil pin + make the live test actually test Basil

**Files:**
- Modify: `ubb-platform/apps/billing/stripe/services/stripe_service.py:16`
- Modify: `ubb-platform/apps/billing/invoicing/tests/test_live_stripe_ar.py`
- Modify: `docs/plans/2026-06-10-program-current-state.md:71`, `ubb-platform/api/v1/tests/test_ar_reconcile.py:65` (comment strings)

- [ ] **Step 1:**
```python
STRIPE_API_VERSION = "2025-03-31.basil"   # canonical form; bare 2025-03-31 is not a valid version
stripe.api_version = STRIPE_API_VERSION
```
- [ ] **Step 2:** In each of the 3 live tests, BEFORE setting the key (ordering trap — `stripe_service.py:12` sets `stripe.api_key` at import time and would clobber a pre-set test key):
```python
from apps.billing.stripe.services.stripe_service import STRIPE_API_VERSION  # applies the global pin
assert stripe.api_version == STRIPE_API_VERSION
stripe.api_key = os.environ["STRIPE_TEST_SECRET_KEY"]
```
- [ ] **Step 3:** Update the two doc/comment strings to `2025-03-31.basil`. Run the AR + live-skip tests. Commit: `fix(stripe): pin canonical 2025-03-31.basil + live test asserts the pin`.

### Task F0.3: Autouse Stripe guard (sentinel key + network block)

**Files:**
- Modify: `ubb-platform/conftest.py` (the only conftest)
- Create: `ubb-platform/pytest.ini` (`[pytest]` + `DJANGO_SETTINGS_MODULE = config.settings`)

- [ ] **Step 1:** Add (verified against stripe 15.2.0 — `_APIRequestor.request_raw/_async` is the network choke point all resource calls funnel through; the sentinel must be **non-empty** or `stripe_call()`'s preflight at `stripe_service.py:47-51` changes behavior; must reset the **module global** `stripe.api_key`, captured at import in two places):
```python
@pytest.fixture(autouse=True)
def _stripe_guard(request, monkeypatch):
    if "test_live_stripe_ar" in request.node.nodeid:  # UBB_STRIPE_LIVE_TEST-gated module
        yield; return
    import stripe
    from django.conf import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_sentinel")
    monkeypatch.setattr(stripe, "api_key", "sk_test_sentinel")
    def _blocked(*a, **kw):
        raise AssertionError(f"Un-mocked Stripe network call in {request.node.nodeid}")
    monkeypatch.setattr("stripe._api_requestor._APIRequestor.request_raw", _blocked)
    monkeypatch.setattr("stripe._api_requestor._APIRequestor.request_raw_async", _blocked)
    yield
```
- [ ] **Step 2:** Full suite green (proves no test was accidentally live). Commit: `test: autouse Stripe sentinel + network guard with live-test carve-out`.

### Task F0.4: Docs honesty completion + dead-code deletion

**Files:**
- Modify: `docs/plans/2026-06-05-stage2-margin-intelligence-implementation.md:1` — banner (text below)
- Modify: `docs/plans/2026-02-11-architecture-audit-action-plan.md:1`, `2026-02-02-ubb-platform-redesign.md:1`, `2026-02-05-two-product-separation-design.md:1`, `2026-02-09-platform-architecture-restructure-design.md:1` — ProviderRate banners
- Modify: `ubb-platform/apps/subscriptions/economics/revenue.py` — delete `:40-57` + the `Sum` import (used only there)
- Modify: `docs/plans/2026-06-10-program-current-state.md` — §2 dead-code warning becomes "deleted in F0.4"; soften the `:5-7` "all contradicting docs carry banners" overclaim or make it true

- [ ] **Step 1: Stage-2 banner (line 1):**
```markdown
> ⚠️ SUPERSEDED (revenue wiring only): the cash-basis `RevenueService.revenue_for_window`/`stripe_revenue_for_window` built in Task 3 and wired into `MarginService.compute_live`/`snapshot_customer` + the margin API below were REPLACED by accrual `accrued_subscription_revenue` (manual + subscription nominal pro-rated) in `2026-06-08-pricing-stageB-revenue-source-implementation.md`, and the cash-basis methods were DELETED. Do NOT re-create them. Cost accumulator, snapshots, thresholds, margin webhooks remain current. Master truth: `2026-06-10-program-current-state.md`.
```
- [ ] **Step 2: ProviderRate banner (the 4 docs, line 1):**
```markdown
> ⚠️ SUPERSEDED (pricing model only): `ProviderRate` was deleted (migration `apps/metering/pricing/migrations/0005_delete_providerrate.py`) and replaced by the two-card `RateCard` + `PricingService` engine — see `2026-06-08-pricing-stageA-rate-card-engine-design.md`. Master truth: `2026-06-10-program-current-state.md`.
```
- [ ] **Step 3:** Delete the two dead methods + unused import; acceptance grep must be word-boundary-exact for the two deleted names (`\b(stripe_)?revenue_for_window\b` **excluding** `manual_revenue_for_window` — the kept live method contains the deleted name as a substring, so a naive grep always false-positives at `revenue.py:21,:87` and `test_economics.py:31,:37`). Suite green. Commit: `docs+cleanup: banner stage2 impl + ProviderRate docs; delete dead cash-basis revenue methods`.

### Task F0.5: Port SDK retry from `feat/ubb-ui-dashboard` (hybrid)

**Files:** cherry-picks land `ubb-sdk/ubb/retry.py`, `ubb-sdk/tests/test_retry.py`, `ubb-sdk/ubb/exceptions.py` (+1 line); hand-wiring touches `ubb-sdk/ubb/{billing,metering,subscriptions,referrals,client}.py`, `ubb-sdk/tests/{test_metering_client,test_billing_client}.py`, `ubb-sdk/README.md`.

- [ ] **Step 1:** `git switch -c tl-sdk-retry-port tl-changes-05-06-26`, then `git cherry-pick -x ff56cbd 8a9ae58 4cd519b` (**topological order — ff56cbd is the parent**; verified conflict-free: retry.py/test_retry.py are new files, exceptions.py byte-identical from fork through HEAD). Do **NOT** pick `93423c8` (import-broken at its own commit; bundles an unrelated BillingClient refactor).
- [ ] **Step 2:** Hand-derive the wiring commit from `git show 93423c8 -- ubb-sdk/ubb/*.py` as the reference: per client — `max_retries: int = 3` in `__init__` + `self._max_retries`; rename `_request` → `_request_once`; in the `>= 400` branch parse `Retry-After` into `err.retry_after` (catch `(ValueError, TypeError)` exactly); new `_request` = `request_with_retry(self._request_once, max_retries=self._max_retries, method=method, path=path, **kwargs)`. Apply at `billing.py:17+34`, `subscriptions.py:13+30`, `referrals.py:13+30`, `metering.py:19+36` **plus** `_request_usage` → `_request_usage_once` (`:106`) with the plain-429-vs-hard-stop split ported verbatim. Wire `UBBClient.__init__` `max_retries` through all four constructions (`client.py:51-68`) — every J1/J2 endpoint inherits retry because all route through the wrapped helpers.
- [ ] **Step 3:** Tests: take `TestClientRetryIntegration` from `git show 93423c8:ubb-sdk/tests/test_retry.py` (**not branch tip** — `8c463bd` camelCased the payload keys and would silently stop exercising our snake_case hard-stop path). Add `max_retries=0` to `tests/test_metering_client.py:13` and `tests/test_billing_client.py:13` setUps (their timeout/connect tests otherwise gain ~3.5s real backoff sleeps). New tests: `create_rate_card` retries 503→200; `set_budget` retries 429 with `Retry-After: 1.5` (assert `time.sleep(1.5)`); `UBBClient.create_customer` (platform piggyback) retries 502 — proves platform endpoints inherit retry; `record_usage` plain-429 retries but hard-stop 429 does not (exactly 1 call).
- [ ] **Step 4: Decision (recommended):** cap server-supplied `Retry-After` at 30s (`min(retry_after, 30.0)` in `backoff_delay`) — one-line divergence from their branch beats an SDK that sleeps an hour on a hostile header. Document in README ("Retries" note + `max_retries` in both constructor signatures, `README.md:139, 264`).
- [ ] **Step 5:** `pytest ubb-sdk/tests -q` (existing 180 + new green, no wall-clock regression), `git switch tl-changes-05-06-26 && git merge --ff-only tl-sdk-retry-port`. Commit messages: keep the cherry-picked ones; wiring commit `feat(sdk): wire retry into all product clients (re-derived from 93423c8)`.

**Stage F0 exit criteria:** full platform + SDK suites green; fresh-DB migrate clean. **PR gate (refuter-corrected): the PR opens after F0.1 + F0.2 + F0.3 (+ F0.4's banners, which are cheap and ride along).** F0.5 is NOT PR-blocking — main is a strict ancestor (0 behind / 175 ahead), so merging deletes no retry work; gating the double-billing fix behind an SDK port only delays it and fattens an already-oversized PR. Land F0.5 as its own small follow-up PR.

---

## Stage F1 — Money-race + AR hardening (~3 days)

> Line-number caveat for F1/F2 anchors inside `postpaid_service.py` and `tasks.py`: numbers are **pre-F0.1** coordinates (F0.1 deletes `tasks.py:100-112` and inserts ~20 lines into `push_customer_period`). Locate by function name (`_repair_usage_invoice`, `_repair_subscription_invoice`, the Phase-2 prior-row chain read), not raw line numbers.

### Task F1.1: Per-owner residual ledger (kills the carry race + strand)

Replace the order-sensitive prior-row chain read (`postpaid_service.py:91-94`) with a commutative per-owner accumulator. Three transactions span a Stripe call, so any lock-the-prior-row scheme releases at Phase-1 commit while consumption isn't durable until Phase 3 — the ledger take-and-zero + pin is the only shape that survives the actual transaction boundaries.

**Files:**
- Modify: `ubb-platform/apps/billing/invoicing/models.py` — new `PostpaidResidualLedger(tenant FK, customer OneToOneField → the serialization point, balance_micros BigIntegerField default 0, db_table "ubb_postpaid_residual_ledger")`; `CustomerUsageInvoice.carry_in_micros = BigIntegerField(null=True, default=None)` (NULL = not yet reserved)
- Create: `ubb-platform/apps/billing/invoicing/migrations/0006_residual_ledger.py` — schema + backfill: seed each customer's ledger from the `residual_micros` of their latest `status='pushed'` row (exactly what the old chain read would have returned)
- Modify: `ubb-platform/apps/billing/invoicing/services/postpaid_service.py`
- Test: `ubb-platform/apps/billing/invoicing/tests/test_concurrency_postpaid.py` (new)

- [ ] **Step 1: Phase-1 carry reservation** (inside the existing atomic block, before the claim save):
```python
if rec.carry_in_micros is None:
    ledger, _ = PostpaidResidualLedger.objects.select_for_update().get_or_create(
        customer=customer, defaults={"tenant": tenant})
    rec.carry_in_micros = ledger.balance_micros
    ledger.balance_micros = 0
    ledger.save(update_fields=["balance_micros", "updated_at"])
# else: retry after Phase-2 failure reuses the pinned value — never a second reservation
```
**`carry_in_micros` MUST be added to the claim save's `update_fields` list** (`:86-87` uses an explicit list — an unnamed field is silently dropped, and the in-process tests would still pass because the same `rec` object carries the value through Phase 2/3; the loss only shows on a retry that re-fetches the row, with the ledger already zeroed = residual destroyed).
- [ ] **Step 2:** Delete the chain read (`:91-94`); `carry_in = rec.carry_in_micros`. Phase 3: after `rec.save` (lock order rec-then-ledger, consistent with Phase 1), `select_for_update` the ledger and `balance_micros += residual_out`. Keep writing `rec.residual_micros` as the audit record.
- [ ] **Step 3: Concurrency tests** (TransactionTestCase + `threading.Barrier(2)` + `connection.close()` in finally, cloned from `apps/billing/tests/test_concurrency_races.py:32-93`):
  - `ConcurrentSamePeriodPush`: 2 threads, same period → 1 row, `Invoice.create.call_count == 1` (proves the `pushing` early-return from F0.1);
  - `ConcurrentAdjacentPeriodCarry`: seed ledger 9_000; push P1+P2 (2_000 usage each) concurrently → conservation: `total_cents_billed*10_000 + final_ledger == 13_000` exactly (current chain code bills 2 cents — fails loudly);
  - `OutOfOrderCarry` (sequential): P0, then P2 **before** P1, then P3 → conservation across all + P1's residual not stranded;
  - `CarrySurvivesRetryAcrossFetch`: Phase-2 exception → sticky `failed` → **fresh re-fetch** re-claim → assert `carry_in_micros` survived the round-trip and the ledger was NOT re-read (catches a missing `update_fields` entry, which the in-process tests cannot).
- [ ] **Step 4:** Existing `test_residual_carries_into_next_period` + `test_subcent_only_creates_no_empty_invoice` pass unmodified (in-order semantics identical). Run against docker-compose Postgres. Commit: `fix(postpaid): per-owner residual ledger — order-free carry, exactly-once reservation`.

**Deploy note:** quiesce billing workers (or deploy outside the monthly close window) — an in-flight old-code push finishing on new code double-carries one sub-cent once.

### Task F1.2: Stripe-legal AR transition table, shared by webhook + backstop

**Files:**
- Modify: `ubb-platform/api/v1/webhooks.py` (replace `TERMINAL` at `:193`)
- Modify: `ubb-platform/apps/billing/invoicing/tasks.py` (`_repair_usage_invoice` `:188-193`, `_repair_subscription_invoice` `:212-217`, delete `_TERMINAL_PAYMENT_STATUS` `:23`)
- Test: extend `ubb-platform/api/v1/tests/test_ar_reconcile.py`; create `ubb-platform/api/v1/tests/test_concurrency_webhooks.py`

- [ ] **Step 1:**
```python
AR_ALLOWED = {
    "": {"open", "paid", "void", "uncollectible"},   # also None
    "open": {"paid", "void", "uncollectible"},
    "uncollectible": {"paid", "void"},               # Stripe: uncollectible stays payable/voidable
    "paid": set(), "void": set(),                    # true terminals
}
def ar_transition_allowed(old, new): return new in AR_ALLOWED.get(old or "", set())
```
- [ ] **Step 2:** Both branches of `_reconcile_customer_invoice`: apply status only when allowed; `logger.warning("ar.transition_ignored", …)` otherwise; **move `paid_at`/`amount_paid_micros` writes inside the applied-state condition** (`row.status == "paid"` / `row.payment_status == "paid"`); keep `_refresh_urls` outside the guard. Cover the row-created-via-`invoice.paid` path (get_or_create defaults make it `paid` at birth — money fields must be set there too).
- [ ] **Step 3:** Backstop parity: both `_repair_*` use `ar_transition_allowed`; keep the loud `ar.reconcile_unexpected_regression` log only for genuinely illegal moves (`paid→open`, `void→*`). One semantic, two paths, by construction.
- [ ] **Step 4: Tests:** uncollectible→paid applies (+paid_at, +amount) on both row types — fails on current code; void→paid stays void with `paid_at is None` — proves the moved guard; paid-then-finalized stays paid with URLs still refreshed; backstop repairs uncollectible→paid (returns 1) and loud-logs paid→open (returns 0). Concurrency: parallel same-event delivery (1 `StripeWebhookEvent` row, handler runs once), parallel `finalized`+`paid` converge to `paid` in every interleaving.
- [ ] **Step 5:** Audit consumers of `payment_status` for "uncollectible = final bad debt" assumptions (none known; margin reads accumulators, not AR). Commit: `fix(ar): Stripe-legal transition table shared by webhook + backstop; money fields inside the guard`.

**Stage F1 exit:** suites green incl. the 2 new concurrency files against real Postgres.

---

## Stage F2 — Analytics scale hardening (~3 days)

Safe because `TIME_ZONE="UTC"` + `USE_TZ=True` + zero `timezone.activate()` ⇒ `__date__gte=d` ≡ `__gte=utc_day_start(d)` row-for-row; the rewrite is pure sargability.

### Task F2.1: Sargable day-windows

**Files:**
- Create: `ubb-platform/core/time_windows.py`:
```python
def utc_day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)
def utc_next_day_start(d: date) -> datetime:
    return utc_day_start(d + timedelta(days=1))
```
- Modify (rewrite rules: `__date__gte=X` → `__gte=utc_day_start(X)`; `__date__lt=X` → `__lt=utc_day_start(X)`; `__date__lte=X` → `__lt=utc_next_day_start(X)`):
  `apps/metering/queries.py:41-42, 89-91 (:91 is __lte), 153, 180-182, 213, 232-234`; `api/v1/metering_endpoints.py:235, 237 (__lte)`; `apps/billing/invoicing/tasks.py:77`; `apps/billing/invoicing/services/postpaid_service.py:26, 46`; `apps/billing/gating/tasks.py:23`. (Dead `revenue.py:49` is deleted by F0.4.)

- [ ] Steps: helper + unit test; mechanical rewrites; grep `__date__` over production code → zero hits; boundary-equivalence tests (events at `23:59:59.999999Z` / `00:00:00Z` straddling month edges, both exclusive-end and inclusive-end sites); SQL-shape regression (CaptureQueriesContext: no `AT TIME ZONE` / `::date` in WHERE); planner proof (`SET enable_seqscan = off`; explain mentions `idx_usage_tenant_effective` / `idx_usage_customer_effective`). Commit per logical group.

### Task F2.2: Tags GIN opclass swap

**Files:** Create `ubb-platform/apps/metering/usage/migrations/0022_swap_tags_gin_to_jsonb_ops.py` (`atomic = False`, vendor-guarded like 0011/0017):
- Forwards: `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_event_tags_ops ON ubb_usage_event USING GIN (tags);` **then** `DROP INDEX CONCURRENTLY IF EXISTS idx_usage_event_tags;` (create-before-drop so `@>` coverage never lapses). Backwards: reverse.
- jsonb_ops serves both `?` (all four `has_key` sites) and `@>` (the one containment site) — swap, don't add (keeps write amplification flat on the insert hot path).
- [ ] Runbook note: a failed CONCURRENTLY retry leaves an INVALID index satisfying IF NOT EXISTS — drop it concurrently and re-run. Round-trip test `migrate usage 0022` ↔ `0021` asserting opclass via `pg_index`/`pg_opclass`.

### Task F2.3: SQL pushdown for tag/dimension aggregation

**Files:** `apps/metering/queries.py:241-251` (get_dimensional_margin tag branch), `api/v1/metering_endpoints.py:278-297` (by_tag block). **Scope change (refuter-corrected):** the `aggregate_lines` pushdown (`postpaid_service.py:27-29, 48-55`) moves to **F3.2**, where the same logic becomes the `get_billed_totals_by_customer` / `get_customer_billed_breakdown` contract functions — written once as SQL pushdown, parity-tested once (§2.6's write-once rationale). If running the pilot cut-line (which excludes F3), `aggregate_lines` keeps its Python loops — acceptable: it is a monthly close path, not a request path.
- Pattern (already proven at `metering_endpoints.py:310-314`): `qs.filter(tags__has_key=k).annotate(v=KeyTextTransform(k, "tags")).values("v").annotate(Sum…, Count…).order_by()` — **the trailing `.order_by()` is mandatory**: `UsageEvent.Meta.ordering=["-effective_at"]` otherwise poisons the GROUP BY.
- Output contracts frozen: same dict keys, same sorts, `"(other)"` for missing/empty tag, `"(seat)"` fallback, lines-sum-to-total invariant in aggregate_lines.
- [ ] Tests: `django_assert_num_queries` pins each path to 1 grouping query (count invariant under 10× rows); byte-identical output vs hardcoded old-loop expectations; the GROUP-BY-ordering trap regression test. Pre-rollout data audit: `jsonb_typeof` scan for any non-string legacy tag values (cosmetic label divergence only).

### Task F2.4: Strict cost coverage — units without metrics hard-rejects

**Files:** `apps/metering/pricing/services/pricing_service.py:38-39, 59` + `apps/metering/usage/services/usage_service.py:66-69`.
- [ ] `price()` gains `units=None`; top of the no-caller-cost branch:
```python
if (units or 0) > 0 and not usage_metrics and getattr(tenant, "require_cost_card_coverage", False):
    raise PricingError("strict cost coverage: units > 0 with no usage_metrics — "
                       "no cost rate card can match; pass usage_metrics or provider_cost_micros")
```
`record_usage` passes `units=units`. The existing `PricingError→422` mapping (`metering_endpoints.py:81-83`) is the contract — no shape change. Semantics matrix: caller cost present → accepted; units 0/None + no metrics → accepted (marker events stay legal); flag off → old behavior. The 422 fires **before** event creation, so a corrected retry with the same idempotency_key succeeds (test this). Release-note for strict-mode tenants + one line in the SDK README uncosted section.

**Stage F2 exit:** suites green; staging EXPLAIN evidence captured (optional `explain_analytics` management command). Documented-not-fixed (follow-up batch): usage_analytics' ~13 sequential scans + unbounded `by_customer` payload + missing default windows; margin list/summary N+1; `compute_business` O(seats×5).

---

## Stage F3 — Boundary restoration + ADR-001 (~3.5 days)

Restore 13 of 16 unsanctioned crossings; sanction exactly three named channels; enforce with an AST test. All moves are behavior-identical (parity-tested before old code deletes). Erosion data for the ADR: 0 unsanctioned at main `c5a1a0e` → 14 statements + 2 layer inversions now, all from Stages D/E.

### Task F3.1: Kill the circular dep + layer inversions
- Create `apps/billing/connectors/stripe/invoice_routing.py` — `_invoice_subscription_id` + `_refresh_urls` moved verbatim from `api/v1/webhooks.py:153-169`; api re-imports from there (names stay importable). Replace the lazy imports at `connectors/stripe/webhooks.py:153` and `invoicing/tasks.py:139` with top-of-module sibling imports. Move `encode_cursor/decode_cursor/apply_cursor_filter` to `core/pagination.py` (api shim re-exports). Import-order smoke tests both directions.

### Task F3.2: Metering read-contract extension (5 functions)
- In `apps/metering/queries.py` (written **sargable**, per §2.6): `get_usage_event_effective_at(event_id)`; `get_customer_ids_with_usage(tenant_ids, start, end)`; `get_billed_totals_by_customer(tenant_id, customer_ids, start, end)` and `get_customer_billed_breakdown(tenant_id, customer_id, start, end, group_by)` — **written directly as the SQL pushdown** (the F2.3 scope moved here; preserves `tag:`/`product_id` branches + `"(other)"`, lines-sum-to-total); `iter_billable_usage_events(tenant_id, since, before, basis="effective")` (plain-dict iterator; the drawdown "anti-join" is really per-event `exists()` on billing's own table, so this is behavior-identical and Stage D's exactly-once key is untouched). **The `basis` parameter exists from day one** so F4.2's drawdown-repair flip to arrival basis is a call-site argument change (`basis="created"`), not a semantic rewrite of a "behavior-identical" contract function — and F4.2's edit target becomes this function's call site, not `wallets/tasks.py:65-67` raw lines.
- Swap the 6 bypass imports: `gating/tasks.py:14`, `invoicing/tasks.py:71`, `postpaid_service.py:18+:43`, `wallets/tasks.py:56`, `subscriptions/handlers.py:40`. Postpaid swap is parity-tested (seeded business+seats+tags fixture → byte-identical lines) before the ORM branch deletes.

### Task F3.3: Platform hooks + subscriptions ports
- `apps/platform/customers/hooks.py`: `register_seat_roster_listener(fn)` / `notify_seat_roster_changed(business)`; `apps/subscriptions/apps.py.ready()` registers `sync_seat_quantity_on_commit` (timing bit-identical — the fn itself defers via `transaction.on_commit`). Replace direct imports at `customers/models.py:69` (restores the decouple design's "No billing imports" target) + the two webhook suspend sites (`connectors/stripe/webhooks.py:226, 323`).
- `apps/subscriptions/ports.py` — the ONLY subscriptions module billing may import: `mark_invoice_payment_failed_for_subscription(...)`, `repair_subscription_invoice(...)` (bodies moved from billing's webhooks/tasks). Delete the model imports at `webhooks.py:155`, `invoicing/tasks.py:137`.

### Task F3.4: Enforcement + ADR
- `apps/platform/tests/test_product_boundaries.py`: AST-walk all non-test/non-migration modules under `apps/`; assert (i) no `apps/` module imports `api.*`; (ii) platform imports no product (allowlist: `seed_dev_data.py`); (iii) `core/` imports only `apps.platform`; (iv) product↔product edges only via `{*→metering.queries, billing→subscriptions.ports, subscriptions→billing.stripe.services.stripe_service, subscriptions→billing.stripe.models, *→platform.customers.hooks}`. Negative-control test with a synthetic violating module.
- `docs/architecture/2026-06-11-adr-001-product-boundaries.md` (Context: golden rule + measured erosion + the self-propagating lazy-import workaround; Decision: the dependency matrix + the named "Stripe connector kit" exception — `StripeWebhookEvent` is deliberately one dedup table across both webhook endpoints; Consequences: machine-checked boundary; hooks registry = synchronous coupling by another name, intentionally — outbox migration of seat sync recorded as next step). Addendum to `two-product-separation.md` (the `:426-435` "current state" example is already fixed; four products now) + supersede note on the decouple design's grep rules.

**Stage F3 exit:** boundary test green and in the suite; zero unsanctioned imports; all parity tests green.

---

## Stage F4 — The four competitiveness gaps

### Task F4.1: Tiered pricing — graduated + package on price cards (~5 days)

**The math that makes it safe:** define every tiered model as a cumulative closed form `T(q)`; price each event as the marginal difference `T(prior+units) − T(prior)`. Telescoping ⇒ `Σ event amounts ≡ T(period total)` **exactly**, for any event split — which is what lets tiers coexist with immutable UsageEvents and exactly-once prepaid drawdown. Volume pricing is not incrementally stable (band crossings retro-reprice already-debited events) → **deferred**, postpaid-only close-time rating if ever demanded. Cost cards stay per_unit/flat.

**Files:**
- Modify: `apps/metering/pricing/models.py` — `PRICING_MODEL_CHOICES += ("graduated","Graduated"), ("package","Package")` (`:40`); `validate_tiers(card_type, pricing_model, tiers)` (graduated: non-empty list of `{"up_to": int>0|None, "rate_per_unit_micros": int>=0, "unit_quantity": int>0 default 1_000_000, "flat_micros": int>=0}`, `up_to` strictly increasing, exactly the last is `None`, ≤20 tiers; package: `tiers==[]`, reuses `rate_per_unit_micros`=price-per-block, `unit_quantity`=block size, `fixed_micros`=period fee; per_unit/flat: `tiers==[]`; `card_type=='cost'` forbids both); `compute_cumulative(q)` (graduated: per-band `flat_micros + (units_in_band * rate + uq//2)//uq` — same half-up division as `compute()`; package: `T(0)=0, T(q>0)=ceil(q/uq)*rate + fixed`); `compute_marginal(prior, units)`; **`compute()` raises for tiered models** (no caller can price a tiered card without period context — also the cost-loop guard); new `PricingPeriodCounter(tenant, customer, lineage_id UUIDField db_index, metric_name, currency, period_start DateField, period_end, units_total BigIntegerField default 0, UniqueConstraint(tenant, customer, lineage_id, period_start))`
- Create: `apps/metering/pricing/migrations/0009_tiered_pricing.py`
- Create: `apps/metering/pricing/services/tier_counter_service.py` — `lock_and_advance(tenant, customer, card, units, as_of) -> (prior, new_total)`: get-or-create with the create wrapped in `with transaction.atomic():` (a savepoint) before the `except IntegrityError` fallback — **the correct exemplar is `apps/billing/handlers.py:60-68` (the Stage-D drawdown pattern), NOT `subscriptions/handlers.py:66-87`**, which is a bare try/except that only works because outbox handlers run outside an enclosing transaction; cloned verbatim inside `record_usage`'s `@transaction.atomic` it raises `TransactionManagementError` on the recovery query. Then `SELECT … FOR UPDATE`, read prior, advance. Calendar-month UTC bounds (same helpers as close).
- Modify: `apps/metering/pricing/services/pricing_service.py` — price loop iterates `sorted(usage_metrics.items())` (deterministic lock order → deadlock-free); tiered cards: `lock_and_advance` + `compute_marginal`; provenance entry gains `tier_breakdown` (`prior_units, units_total_after, cumulative_before/after_micros, period_start, lineage_id, bands[]`); cost loop: defensive `PricingError` on tiered cost card; `PRICING_ENGINE_VERSION = "2.1.0"`
- Modify: `apps/metering/usage/services/usage_service.py` — **move `PricingService.price` inside the inner savepoint** (currently `:66-69`, outside): a raced duplicate insert must roll back the counter advance; the UsageEvent unique constraint stays the single exactly-once authority. Highest-blast-radius edit of the stage — existing pricing tests must pass unchanged. Also harden the `except IntegrityError` handler (`:95-98`): it currently assumes IntegrityError ⇒ duplicate event and does an unconditional `.get(...)` — with counter writes now inside the savepoint, change to `.filter(...).first()` and re-raise when no duplicate exists, so a counter-machinery IntegrityError surfaces attributably instead of as a `DoesNotExist` 500.
- Modify: `api/v1/schemas.py` (tiers on RateCardIn/UpdateIn/Out), `api/v1/metering_endpoints.py` (validate→422 at create/batch/update; `tiers` in `_rate_card_to_out` and `_RATE_CARD_COPY_FIELDS` — **forgetting the copy-fields line silently drops tiers on every version bump**; version updates keep the same lineage ⇒ same counter ⇒ marginal continuity across mid-period price changes)
- Create: `apps/metering/pricing/tasks.py` — `verify_tier_rerate()` beat (1st 03:15, after close): per counter, assert (a) `counter.units_total == Σ event units`, (b) provenance chain continuity (`prior[i+1] == after[i]`, from 0), (c) `Σ micros == compute_cumulative(Σ units)` for single-version periods. **Alert only (`pricing.tier_rerate_drift`), never mutate.**
- SDK: `types.py` RateCard `tiers: list | None = None`; `metering.py` `create_rate_card(tiers=…)`; README note: **billed amounts are marginal** (an event can bill 0 inside an already-purchased package block — correct; Σ per period is exact)
- Tests: property test (~200 random configs × random event splits: `Σ marginal == cumulative(Σ)` exactly, monotone, ≥0); validator matrix; replay idempotency fast path AND race path (pre-insert duplicate after the pre-check → savepoint IntegrityError → counter unchanged — **the test that proves the restructure**); override/dimension/versioning composition; drawdown integration (Σ deductions == T(total); zero-marginal package event creates NO wallet txn via the `>0` guard); re-rate drift alert; full pricing/usage suites unchanged.

Policy notes (documented in `docs/plans/2026-06-11-tiered-pricing-design.md`, written as part of this task): per-seat ladders (not pooled — matches per-seat control; pooled is an open product question); a mid-period customer-override card starts a fresh ladder (fresh terms, documented); per-tier `flat_micros` charged on band entry.

### Task F4.2: Caller timestamps + bounded backfill + POST /usage/batch (~6-8 days)

**Validation (all at the choke point so single + batch share it):** `effective_at` optional ISO8601, tz-aware required; ≤ now+5min; ≥ now − `tenant.backfill_window_days` (new field, default 34, cap 60); **422 `billing_period_closed`** when the billing OWNER's `CustomerUsageInvoice` for that effective month has `status in (pushing, pushed, skipped, failed_permanent)` **OR `push_phase != ''` OR `stripe_invoice_id != ''`** (refuter-corrected: under F0.1's resume semantics, a `pending/failed` row that already touched Stripe has items pinned at the OLD aggregation; a backfill would change the recomputed total while the `line_index` diff never updates existing items and amount-sorted indices silently remap — finalized invoice ≠ recorded total. Only rows that have never touched Stripe, `push_phase=''`, stay open — for those, re-aggregation genuinely is safe). Typed codes: `effective_at_naive | effective_at_in_future | effective_at_too_old | billing_period_closed`.

**Model:** `effective_at` `auto_now_add=True` → `default=timezone.now` (state-only AlterField, NOT NULL preserved, no data migration) + new index `(tenant, created_at)` for arrival-basis scans. Pass `as_of=effective_at` into `PricingService.price` (the hook already exists unused at `:38-40`) → backdated events price on historical card versions.

**Batch:** `POST /usage/batch` (1..100), items **independent** (each is already its own atomic event+outbox commit; one mega-transaction would hold Run locks + 100 outbox rows and diverge from N-singles semantics). Per-item result array mirrors single-call error mapping byte-for-byte (incl. hard-stop kills the run, later items on it get `run_not_active`); HTTP 200 always with `succeeded/failed`; whole-batch replay returns original event_ids with zero new rows (idempotency constraint). Transport-error guidance: replay the whole batch.

**Downstream recompute map (the actual point of this task — every `effective_at` consumer classified):**
| Consumer | Policy | Change |
|---|---|---|
| Postpaid aggregation | correct only for periods that never touched Stripe; guarded by the extended 422 above for everything else | none beyond the guard |
| Analytics/timeseries/dimensional margin/referrals | naturally correct (recompute on read) | none |
| Cost accumulators | already buckets by event effective_at | prefer `payload["effective_at"]` fast path; widen reconcile to current+2 prior months (60d window spans 3) |
| Margin snapshots | need recompute | new `BackfillDirtyPeriod(tenant, customer, period_start, unique)` marker written in the record transaction for prior-month backfills + hourly `resnapshot_dirty_periods` (snapshot+emit are idempotent; delete-marker-after-success) |
| Budget live counters | budget = **effective-month** basis | skip the Redis increment when effective month ≠ current month (hourly rebuild already effective_at-filtered). **Documented enforcement bypass:** an enforcing-capped seat can keep recording by backdating into the prior month (no consulted counter increments; wallet floor/suspension still hold). Bounded by `backfill_window_days` — tenants needing airtight caps set it to 0 per tenant; state this in the budget docs |
| Drawdown repair window | DLQ horizon is an **arrival**-time concept | flip the `iter_billable_usage_events(…, basis=…)` call-site argument (F3.2) to `"created"` — or, on the pilot cut-line without F3, edit the inline filter in `reconcile_usage_drawdowns` (locate by function; pre-F0.1 anchor was `wallets/tasks.py:65-67`). Kills "backdated >7d invisible to repair forever" with zero window widening; needs the new `(tenant, created_at)` index in the same release |
| Wallet debits / gates / run hard-stop | intentionally **arrival** (balance is a "now" scalar) | none, documented |
| Tenant platform fee | **arrival** basis, made symmetric | `get_period_totals(basis="arrival")` param; `reconcile_period` passes it (kills the accumulate-by-wall-clock vs reconcile-by-effective_at drift asymmetry) |
| Tier counters (F4.1) | **effective**-month period; closed-period 422 keeps invoiced ladders frozen | counter period source flips to effective month |
| Usage list pagination | backdated events insert behind in-flight cursors | accepted + documented (standard time-ordered-feed behavior) |

**Outbox:** `UsageRecorded` gains `effective_at: str = ""` (backward-compatible; legacy queued payloads fall back to current behavior — deploy schema before/with handlers).

**SDK:** `record_usage(recorded_at=…)` (tz-aware datetime or ISO string; naive → client-side ValueError) mapping to wire field `effective_at`; `record_batch(events)` with per-item `recorded_at`; `BatchItemResult` dataclass; README (34-day default, typed 422 codes, replay strategy).

**Known race (documented, not fixed):** the closed-period check vs the close task's Phase-1 claim — milliseconds wide, once a month; the future adjustment-line mechanism is the real fix; do NOT lock `CustomerUsageInvoice` in the record hot path.

Tests: bounds matrix; historical pricing via as_of (provenance shows v1 card); closed-period guard incl. seat-backfilling-into-owner's-pushed-period; batch independence/idempotency/in-batch duplicate keys/hard-stop mid-batch; one test per consumer row in the table above; migration round-trip.

### Task F4.3: Expiring credit grants (paid vs promo) (~5-6 days)

**Shape:** `CreditGrant` lots + `GrantAllocation` rows; the existing wallet row lock (`locking.py:26`) is the grant mutex — no new locks. `Wallet.balance_micros` stays the spendable cache; **base is derived** (`balance − Σ remaining(active)`), never stored ⇒ cannot drift. Every grant mutation commits atomically with the balance mutation and the WalletTransaction whose `(wallet, idempotency_key)` constraint already provides exactly-once — grants ride the existing keys unchanged (`usage_deduction:{id}`, `auto_topup:{pi}`, `topup:{session}`).

**Consumption order:** soonest-expiry first (NULLS LAST), promo-before-paid on ties, `created_at` tiebreak. **Expiry is lazy + beat:** `expire_due` runs in-line at every consume under the wallet lock (correctness never depends on beat timing) AND an hourly sweep keyed `expiry:{grant_id}` writes a `GRANT_EXPIRY` debit + `billing.credit_grant_expired` webhook; 7-day warning via winning-update on `warning_sent_at`. **Register both event types in `apps/platform/events/apps.py:13-32`** or they never reach tenant webhooks.

**Files:** `apps/billing/wallets/models.py` (+`CreditGrant`, `GrantAllocation`, txn types `GRANT/GRANT_EXPIRY/GRANT_VOID` + drive-by `DEBIT` which `billing_endpoints.py:74` already writes outside the choices; `CustomerBillingProfile.topup_grant_expiry_days` nullable), migration `0005_credit_grants` (no data backfill — existing balances are base by definition; zero-grant tenants behave bit-identically), `apps/billing/wallets/grants.py` (`GrantLedger.expire_due / allocate / create_grant / promo_remaining`, all assert `in_atomic_block`), wiring in `handlers.py` (expire_due after lock, allocate in the winning branch only) + `wallets/tasks.py` (mirror in repair; new beat task; extend `reconcile_wallet_balances` with per-grant equation `granted == remaining + Σ allocations + expired + voided` and `Σ remaining(active) ≤ max(balance, 0)` loud-drift checks), `topups/services.py` (paid grant inside the existing savepoint with the TOP_UP row — covers charge task, webhook, AND `reconcile_topups_with_stripe` with zero changes to them), `connectors/stripe/webhooks.py` (checkout grant; dispute/refund clawback as a **cascade, not source-lot-only** — refuter-confirmed: voiding only the source lot's remaining breaks `Σ remaining(active) ≤ max(balance, 0)` whenever the disputed lot was partially consumed while other lots survive, and a later expiry of those lots then debits promo the customer no longer holds. Clawback = void the source lot's remaining FIRST, then consume remaining from other active lots — same order as drawdown — until the invariant holds again, all in the same transaction; `expire_due` additionally clamps its debit to `min(remaining, max(balance, 0))` as defense-in-depth), `billing_endpoints.py` (/debit + /withdraw route through the ledger; withdraw availability becomes `balance − promo_remaining ≥ amount` — release-note; new POST/GET `/customers/{id}/grants` + `/void`, owner-resolved, keyed `grant:{idempotency_key}`), `me_endpoints.py` (GET /grants; BalanceResponse += optional `promo_micros, expiring_micros, next_expiry_at`), SDK (`create_grant/list_grants/void_grant`, `CreditGrant` dataclass), event schemas.
**Edge rule:** `create_grant` into a negative-balance wallet immediately self-allocates `min(amount, -old_balance)` as `overage_recoup` so the invariant holds (product question flagged: promo-as-future-usage-only would need the invariant weakened).

Tests: allocation-order matrix; exactly-once expiry (double-run + Barrier race); lazy expiry (expired lot never consumed even before the sweep); replay-safe drawdown with grants; two new Barrier classes in `test_concurrency_races.py` with the existing two **unmodified** (back-compat proof); G3 property (no `GRANT_EXPIRY` ever crosses zero / triggers overage events); recoup; **dispute-of-partially-consumed-lot** (base 0; promo A=10 far-expiry; paid B=20 near-expiry; spend 15 → B remaining 5; dispute the 20 top-up → cascade voids B's 5 then consumes 10 from A → invariant holds, A's later expiry debits 0); repair-path consumption; corrupted-grant reconcile alarm; full suites green.

### Task F4.4: Sandbox via sibling tenant (~6 days; phase 1 = 3 days shippable without Stripe)

**Decisive code fact:** `ApiKeyAuth` already does `request.tenant = key_obj.tenant` and all ~27 domain models are tenant-scoped with tenant-embedded unique constraints — a sibling tenant gets isolation, idempotency, rate limits, and every beat job **for free**. A `livemode` column would have to touch every table, every exactly-once constraint, and every query helper; one missed filter = money-state leak. The `ubb_test_` prefix already exists unused (`tenants/models.py:101`) — this gives it a target.

**Phase 1 (no Stripe):** `Tenant.is_sandbox` + `parent_tenant` self-FK + `uq_one_sandbox_per_parent` (partial unique) + `ck_sandbox_iff_parent`; `sandbox_service.get_or_create_sandbox` (copies name/products/billing_mode/currency, NEVER Stripe ids; race-safe); **mint-time routing** — `create_key(is_test=True)` resolves to the sandbox sibling and enforces `is_test == tenant.is_sandbox` (verify-time mismatch check as defense-in-depth, zero extra queries); `request.sandbox` on auth; `POST/GET /api/v1/tenant/sandbox` (provision + mint, live key only); seed command; **reset**: `POST /api/v1/sandbox/reset` (403 unless sandbox key) → task re-verifies `is_sandbox`, quiesces via `is_active=False` (verify_key filters on it → all sandbox traffic 401s mid-wipe), FK-ordered wipe (**seats before parents** — Customer self-FK is PROTECT; queryset `.delete()` bypasses the insert-only save guard), `keep_config` preserves rate cards/plans/webhook configs, re-activate + `sandbox.reset_completed` event (**register the type in `events/apps.py`**).
**Phase 2 (Stripe test mode):** `STRIPE_TEST_SECRET_KEY/_WEBHOOK_SECRET/_CONNECT_TEST_CLIENT_ID` settings; `api_key_for_tenant(tenant)` (sandbox → test key, **refuse-live**: raise unless `sk_test_` prefix); **make `stripe_call` REQUIRE an explicit `api_key=` (or `tenant=` from which it resolves)** so a forgotten parameter is a `TypeError`, not a silent live-key call — `stripe.api_key` is set globally at import (`stripe_service.py:12`) and would otherwise be the fallback for every site added after this stage (F5.3/F5.4/F5.5 all add new Stripe calls); **enumerate the call sites by grep at implementation time** (the static count is 23 in 7 files today) and add a grep/AST CI check alongside the F3.4 boundary test; sandbox OAuth uses the test client id + test key; test webhook endpoints (`/webhooks/stripe/test`, livemode guards gated on the test secret being configured — preserves all-test dev setups); **the one genuine leak vector**: a Standard Connect `acct_` id is identical in test and live mode — add `tenant__is_sandbox=(not event.livemode)` to EVERY `event.account` lookup via one central helper Q-filter (12 enumerated sites) + collision test (two siblings, same acct id, livemode toggled); platform-fee exclusion (`_calculate_fees` returns `(0, [])` for sandbox + belt-and-suspenders raise in `create_tenant_platform_invoice`); outgoing webhook payloads gain `"livemode": not is_sandbox`.

Tests: routing, both-direction isolation, mismatch 401, one-sandbox-per-parent, fee exclusion, refuse-live key, OAuth test-mode, livemode anti-collision, reset scoping/hierarchy/keep_config, webhook marker.

**Stage F4 exit per task:** suites green + DB-validated (repo convention); each task ships its own design doc in `docs/plans/` (tiers and backfill docs are named in their tasks).

---

## Stage F5 — Demo-visible parity slices (independent; cherry-pick by demo value)

> Two cross-cutting rules for every F5 slice: (1) any new Stripe call site threads `api_key=`/`tenant=` per F4.4's required-parameter rule when F4.4 has landed (F5.3/F5.4/F5.5 all add new sites); (2) any new outbox event type (F5.3's `tax_config_error` tenant event included) is **registered in `apps/platform/events/apps.py`** or it never reaches tenant webhooks — same trap F0.1 Step 1 and F4.3 step 4 guard against.

| # | Slice | Size | Core decision |
|---|---|---|---|
| F5.1 | **/me usage summary** — `GET /api/v1/me/usage-summary` (month-to-date per-event_type units/billed/count via a new sanctioned `get_customer_usage_summary` in `metering/queries.py`; business tokens aggregate seats). Deliberately NO billing-owner gate: attribution is per-seat by design; a seat seeing its own usage leaks nothing. | S/1d | closes "end customer can't see what they consumed" |
| F5.2 | **Self-serve API keys** — GET/POST `/tenant/api-keys`, `/rotate` (atomic create-new-then-deactivate-old, raw key returned once), DELETE (soft revoke; 409 on last active key). Revocation is instant because auth is a per-request DB lookup — do NOT add a key cache. Outbox audit events. SDK methods. | S/1d | |
| F5.3 | **automatic_tax opt-in** — `Tenant.automatic_tax_enabled`; PATCH /config + preflight `stripe.tax.Settings.retrieve` (422 with Stripe's message if not active); applied at exactly two sites: `Subscription.create` + postpaid `Invoice.create`. **Excluded** from top-up checkout/receipts (wallet credit must equal charge). Tax failure during push → `failed` with `skip_reason='tax_config_error'` + tenant event (bounded by F0.1's caps). | S/2d | tax = Stripe's job; we pass the flag |
| F5.4 | **Subscription lifecycle + plan-price versioning** — orchestrator verbs `cancel(at_period_end|immediate)/pause/resume` (mirror updated synchronously; webhook stays confirm path; `pause_collection` leaves Stripe status "active" → explicit `paused` mirror flag); **the fee-edit fix**: `update_plan_prices` bumps `pricing_version`, creates a NEW Price on the same Product keyed `plan-price-{axis}-{plan.id}-v{n}` (fixes the version-less key at `service.py:125`), old subs keep old prices, `migrate_existing=True` walks items with `proration_behavior='none'`; `_persist_mirror` axis match must use item history (not current plan ids) **in the same change**. API + SDK verbs. Trials/coupons documented non-goals. | M/4d | kills C6 (silently ignored fee edits) |
| F5.5 | **Consolidated postpaid invoice (opt-in)** — when the owner has an eligible UBB-managed sub, pin the same per-line items to the subscription's **draft renewal invoice** (`invoice=draft.id`, found via `Invoice.list(subscription=…, status='draft')`), do NOT finalize (Stripe auto-finalizes ~1h post-anchor); persist the resolved target to `rec.stripe_invoice_id` while `pushing` BEFORE item creation; missed window → loud log + standalone fallback. **Safety addendum (refuter-confirmed must-fix):** F0.1's adopt-finalized path is only sound when finalization is self-controlled; here Stripe auto-finalizes regardless of our progress, so a crash mid-pin + retry-after-finalize would blindly adopt a **partial** invoice (silent under-billing). For `invoice_kind='consolidated'`: (a) item keys get a per-attempt namespace (`usage-item-{rec.id}-c{target_id}-{i}`) so a remainder can move to a fresh standalone without 24h key collisions; (b) the adopt path must DIFF `line_index` items against `cent_lines` — any lines missing on a finalized target are billed on a standalone remainder invoice, and the rec is marked `pushed` only when every line sits on exactly one finalized invoice; (c) pre-check time-to-auto-finalize before starting to pin (skip to standalone if the window is nearly closed). Move close beat 02:00 → **00:05 UTC**. Extend BOTH the webhook AND hourly reconcile to repair consolidated rows by subscription-invoice id (missing one leaves them permanently NULL payment_status). Stage-B revenue stays correct by construction (nominal basis). `invoice_kind` surfaced on reads. | M/5d | kills the two-invoices wart for the visible segment |
| F5.6 | **CUR-1: per-tenant currency integrity** — writable `default_currency` (lowercase allowlist, **2-decimal currencies ONLY until CUR-2 lands** — every conversion path hard-assumes minor-unit = 1/100, so allowlisting `jpy` today means 100× overbilling; reject zero-decimal currencies with a clear 422) with **409 once money exists** (provisioned Price currency is not stored → later cross-check impossible); choke-point 422 on event currency ≠ tenant currency; rate-card currency pinned to tenant; wallets created in tenant currency lowercase + data migration lowercasing existing `"USD"` rows; literal USD fallbacks replaced. CUR-2 (minor-unit helper across ~14 conversion sites for zero-decimal currencies) and CUR-3 (consistency sweep) staged separately, optional this program. | S/1.5d | stops new mixed-currency data now |
| F5.7 | **Webhook signature v2 + SDK verify helper** — sign `f"{ts}.{body}"` (Stripe-style `t=…,v1=…` header, old `X-UBB-Signature` kept during a deprecation window), tolerance check; SDK `verify_webhook(payload, sig_header, secret, tolerance=300)`. Closes the replay-forever hole; gives the SDK the verification helper competitors ship. | S/1.5d | |

---

## Stage F6 — Process / repo health (~2 days)

- [ ] **F6.1 Lockfile + CI.** `uv pip compile` (or pip-tools) lockfiles for `ubb-platform/requirements.txt` + SDK; CI job: install from lock, `manage.py check`, `makemigrations --check`, full platform suite vs Postgres service, SDK suite (the consultant's out-of-the-box repro failure was an env-pinning problem; make it impossible).
- [ ] **F6.2 `feat/ubb-ui-dashboard` decision (strategic, needs the user).** That branch holds: the UI scaffold, Clerk auth, platform endpoints, AND a **rival pricing schema** (Card/Rate/Group + camelCase API) with migration numbers colliding against the RateCard engine (pricing 0005-0008, usage 0016-0020). It cannot merge; it must be **rebased onto this branch with its pricing layer dropped/rewritten against RateCard**, or its UI work extracted. Until decided, treat it as a read-only source (F0.5 already extracts retry). Recommend: extract UI + Clerk + dashboard endpoints onto a fresh branch off post-F0 main; discard its pricing commits.
- [ ] **F6.3 Master doc refresh.** Update `2026-06-10-program-current-state.md` (Basil pin string; bounded push; deleted dead code; new §: residual ledger, AR table, tiers, backfill, grants, sandbox as they land); keep the file-anchored style.

---

## Effort + cut-lines

| Stage | Days | Cumulative |
|---|---|---|
| F0 pre-PR gate | ~5 | 5 |
| F1 money/AR | ~3 | 8 |
| F2 scale | ~3 | 11 |
| F3 boundaries | ~3.5 | 14.5 |
| F4.1 tiers | ~5 | 19.5 |
| F4.2 backfill+batch | ~7 | 26.5 |
| F4.3 grants | ~5.5 | 32 |
| F4.4 sandbox | ~6 | 38 |
| F5 (all seven) | ~15 | 53 |
| F6 | ~2 | 55 |

**Pilot-ready cut-line (≈28.5 days):** F0 + F1 + F2 + F4.1 + F4.2 + F5.1-F5.3 **+ F5.7**. That makes the money path safe, the rating engine credible (tiers), one bad integration day recoverable (backfill), the demo respectable (/me usage, keys, tax flag), and the tenant-webhook surface non-replayable (F5.7 — pulled in because a pilot rides on exactly that surface; shipping without it means tenants must treat deliveries as at-least-once AND replayable, which is not a story to tell in a pilot) — while every verified moat stays intact. On this cut-line, `aggregate_lines` keeps its Python loops (F2.3 scope note) and the drawdown-repair basis flip edits the inline filter (F4.2 table note).
**Competitive cut-line (≈41 days):** + F3 + F4.3 + F4.4 (grants for the AI-credits motion, sandbox for evaluation, boundaries for long-term health).
**Deferred-perf follow-up (named, unscheduled):** the F2-exit documented-not-fixed list (usage_analytics' ~13 sequential scans + unbounded `by_customer` payload + default windows; margin list/summary N+1; `compute_business` O(seats×5)) becomes its own batch when a tenant's data volume makes it bite.

---

## Self-review checklist (run at each stage close)

1. Full platform + SDK suites green against docker-compose Postgres; `makemigrations --check` clean; fresh-DB migrate clean.
2. Every new money mutation is inside a transaction with a `(…, idempotency_key)` unique constraint or row lock — name it in the PR description.
3. Every new beat task is idempotent and listed in `CELERY_BEAT_SCHEDULE` with a stated cadence rationale.
4. Docs: the stage's design doc exists in `docs/plans/`; the master current-state doc is updated; no new un-bannered contradictions.
5. The boundary test (post-F3) passes — no new unsanctioned imports.
