# Competitive backend review — 2026-06-12

**Scope:** the full UBB backend (`ubb-platform/` + `ubb-sdk/`) at branch `tl-changes-05-06-26` HEAD, reviewed fresh against the question: *is this a competitive usage-based billing backend, and what actually makes it different?*

**Method (and why you can trust it):** this review was produced by eleven independent fresh-eyes auditors instructed to trust **only the code at HEAD** — design docs and docstrings were treated as claims to verify, never as evidence. Every code statement in these documents carries a `file:line` anchor. Every competitor statement traces to a URL fetched on 2026-06-12 and recorded in the evidence registry (`03`); anything that could not be sourced is listed there as *do not assert*. Two fact-checkers then sampled **202 claims** across the drafts against source code and re-fetched citations; 13 problems were found and corrected (including one auditor claim that was itself wrong — the docs note where). No production code was modified by this review.

## The documents

| File | What it answers |
|---|---|
| [`01-capability-inventory.md`](01-capability-inventory.md) | **What a customer can actually do** — the tenant decision tree (every choice and default), a 60+ capability catalog with endpoints/SDK/options/anchors, four worked end-to-end journeys, and an unusually long honest list of what a customer *cannot* do. |
| [`02-backend-audit.md`](02-backend-audit.md) | **The 12-category audit** — scorecard, per-category evidence, sourced competitor comparison, gaps with severities, and a consolidated Tier 0/1/2 action plan. |
| [`03-competitor-evidence.md`](03-competitor-evidence.md) | **The evidence registry** — sourced facts only, for Metronome, Orb, Lago, OpenMeter, Amberflo, and Stripe-native UBB, plus the explicit could-not-verify list. |

---

## Part 1 — What we built (the one-paragraph answer; detail in `01`)

UBB is a usage-based **rating, margin, and spend-control layer that runs on the tenant's own Stripe account**. A tenant connects Stripe via Standard OAuth, picks a mode per tenant (`meter_only` / `prepaid` / `postpaid`) and per customer (`revenue_mode`), and then: records immutable, exactly-once usage events (single or 100-item batch, caller timestamps back to a tunable 0–60-day window) that are **priced at ingest by a two-card engine — provider COGS and billed price — with per-unit, flat, graduated, and package models**, dimensional matching, per-customer overrides, versioned cards, and a full per-event pricing-provenance audit trail; runs prepaid wallets with hosted top-ups, auto-top-up, **expiring paid/promo credit grants** with clawback cascades and lot-aware refunds; enforces spend in real time via a pre-check gate, enforcing budget caps, balance-floor suspension, and a **per-run cost ceiling that kills an AI agent session mid-flight**; and bills postpaid usage onto Stripe invoices monthly (standalone two-phase by default, opt-in consolidation onto the subscription renewal), orchestrating one Stripe subscription per business with access-fee + per-seat items, lifecycle verbs, grandfathered plan-price versioning, and webhook+poller AR tracking — exposing all of it through a typed Python SDK, an end-customer `/me` API behind widget JWTs, signed (replay-bounded v2) outgoing webhooks across 26 registered event types (explicit opt-in: tenants subscribe to specific types or `["*"]`), and a one-call **sandbox** sibling-tenant mode. Per-customer/per-business **gross margin** (accrual basis) is the product's reporting centerpiece.

The equally important other half: what a customer **cannot** do — §5 of `01` lists every limit found, the largest being: no volume/percent-of-revenue/minimum-commit pricing models, no multi-currency (one 2-decimal currency per tenant, locked once money exists), calendar-month-UTC billing periods only, no trials/coupons (deliberate — Stripe's levers), Python-only SDK, no UI, no self-serve tenant signup, and a synchronous-only ingest path.

## Part 2 — The audit verdict (detail in `02`)

| Layer | Verdict |
|---|---|
| **Domain layer** (money correctness, idempotency, tenant isolation, self-healing) | **Genuinely strong — in places stronger than the documented competitor postures.** Unbounded DB-constraint idempotency (vs Metronome's 34-day / Orb's grace-window / Stripe's ≥24h windows — sourced in `03`); a 25-job reconcile lattice that self-heals money against Stripe; constraint-encoded invariants (partial-unique idempotency keys, grant-conservation checks, fuzz-tested `Σ remaining ≤ max(balance,0)`); per-item-isolated batch semantics that beat Lago's all-or-nothing batch; tested true-concurrency races on real Postgres. |
| **Operational layer** (deploy, observe, back up, scale, throttle, comply) | **Largely absent.** No app container, no deploy pipeline, CI written but never executed, no backups (RPO today = *everything*), no error tracking/metrics/paging (every tripwire ends in unwatched stdout), no rate limiting on the ingest chokepoints, three single points of failure, one unguarded `cache.set` on the auth path that turns a Redis outage into a full API outage, no SOC 2 runway. Scorecard: 6 of 12 categories **weak**, 6 **adequate**, 0 **strong** — because operational readiness is half of every category. |

The audit's unifying sentence: *competitors are weakest where UBB is strong and strong where UBB is weak.* The Tier 0 blockers (push the branch + run CI, backups, a Dockerfile, Sentry+paging) are days of work, not architecture.

### Net-new defects this review found (no code was changed; these are flagged for fixing)

1. **Non-USD tenants are mischarged on top-ups** — checkout sessions and receipts hardcode `currency: "usd"` (`apps/billing/connectors/stripe/stripe_api.py:59`, `receipts.py:64`) while `default_currency` is now writable and wallets/grants carry the tenant currency: an EUR tenant's top-up charges USD and credits it as EUR micros. Highest-priority finding of the review.
2. The auth hot path's unguarded `cache.set` (`core/auth.py:19`) makes Redis a hard SPOF for the entire API despite the deliberately fail-open gate/budget design.
3. Ingestion endpoints have **zero rate limiting** (the only limiter guards the optional pre-check path).
4. `request_id` accepts 500 chars at the API but the column is varchar(255) (`api/v1/schemas.py:27` vs `apps/metering/usage/models.py:17`) — DB-layer 500s.
5. Creating a duplicate active rate card returns an unhandled 500, not a 422 (`api/v1/metering_endpoints.py:588-604`).
6. `UBBClient.withdraw`/`refund_usage` SDK facades silently bypass the real `/withdraw`/`/refund` safety semantics (`ubb-sdk/ubb/client.py:501-514`).
7. No unsuspend/reactivate API exists — a suspended customer requires a manual DB edit; topping up does not clear suspension.
8. `POST /debit` has no balance floor and emits no overage/suspension events; tenant webhook secrets are stored in plaintext; plan `interval` is unvalidated past the DB column width.

---

## Part 3 — What actually makes us different (the honest answer)

Strip away everything competitors also have, everything we merely claim, and everything that is table stakes. Four differentiators survive contact with the evidence; each is verifiable in code today.

**1. We rate cost, not just price — and we do it per event, at ingest, with provenance.**
Every event is priced twice — provider COGS and billed amount — through the same versioned, dimensional, override-aware card engine, and the event permanently records *how* (`pricing_provenance` with engine version, card ids, tier-band breakdowns). Per-customer and per-business gross margin is computed from that, on an accrual basis. In the documentation sets fetched for this review, neither Metronome, Orb, nor Lago documents native provider-COGS rating as a billing-engine input — their engines rate revenue. The honest caveats: **Amberflo explicitly positions on "Metering, Cost Attribution, and Billing" with Cost Guards** (amberflo.io, `03 §5`) — captured at its AI-gateway hop rather than from billing-side rate cards — and **Stripe's token-billing preview** auto-meters LLM provider costs with a markup dial (docs.stripe.com/billing/token-billing, `03 §6`). The COGS-truth position is real and ours is the most general (any provider, any metric, your own rate cards, no gateway required), but the ground is contested and the Stripe–Metronome combination (acquisition completed 2026-01-14, `03 §1`) is moving toward it. This is a 12–24-month head start, not a permanent moat.

**2. We enforce spend synchronously; they observe it.**
The pre-check gate, enforcing budget caps with hard-stop percentages, balance-floor auto-suspension, and — uniquely as far as the fetched documentation shows — the **Run primitive**: snapshot a cost ceiling and wallet floor for an AI-agent session and kill it mid-flight, under row locks, the moment either breaches. Metronome's documented levers are billing-side (thresholds, invoicing); Orb's grace-period/alerting model and Lago's premium-gated progressive billing are likewise not synchronous gating (`03`). OpenMeter does ship real-time entitlement enforcement (`03 §4`) — but as quotas/feature-flags, not a session-scoped kill with money semantics. For agentic-AI tenants, "your agent cannot overspend" is a sentence none of the big three can say.

**3. Correctness is a product feature here, not an ops aspiration.**
This is the strangest and most defensible difference: the things vendors put on trust pages, UBB has as *executable artifacts*. Idempotency that never expires (a permanent unique constraint, vs their 24h–48h–34-day windows — every one sourced in `03`); a self-healing lattice of 25 scheduled reconciles that repair money against Stripe exactly-once; invariants encoded as database constraints and proven by fuzz tests and real-Postgres race tests; tiered pricing whose per-event marginal amounts provably telescope to the closed-form period total, so the wallet, the invoice, and the math can never disagree. "Risk-free for the customer" is the stated north star — in the domain layer, the code delivers it to a standard the audit could not break.

**4. The money stays yours: your Stripe, your data, your infrastructure.**
Standard OAuth on the tenant's own Stripe account (UBB never holds funds, is never merchant of record), and the stack is self-hostable. Metronome and Orb are SaaS-only per their own security pages (`03 §1–2`); Lago matches us on self-hosting (AGPL, `03 §3`) but paywalls invoice grace periods, dunning, and SSO as premium, and ships **no sandbox/test mode at all** (`03 §3`) — where UBB's sibling-tenant sandbox with Stripe test-mode isolation is one API call.

**And the honest other side of the ledger.** We are *not* different — we are behind — on: ingestion scale (Metronome publishes 100k events/sec, Orb 250k+/sec; our synchronous priced-in-transaction path is orders of magnitude below — `02 §10`); pricing breadth (no volume, percent, minimums, commitments); operational trust (they lead with SOC 2 + status pages + published uptime; we have none of it); SDK reach (their 4–6 languages vs our Python-only); UI (none); and multi-currency. None of those is what we sell, but every enterprise procurement will ask.

**The one-sentence answer:** *UBB is the only backend in this comparison set that treats per-event cost-truth, synchronous spend enforcement, and provable money-correctness as the product — running on the customer's own Stripe — and it is currently a domain-layer engine without an operational shell.* The buyer it is genuinely different for is an engineering-led AI/LLM company that needs to know its margin per customer and needs its agents physically unable to overspend — and that buyer can verify every claim above in this codebase, which is itself a difference no competitor offers.

**Is it competitive?** In the domain layer: yes, demonstrably, today. As a sellable service: not until Tier 0 of `02`'s action plan is done (push + CI green, backups, a deployable artifact, error tracking) and the one standing launch gate is cleared — the gated live-Stripe test has still never been run against a real Stripe account, so J2 remains ledger-proven rather than Stripe-proven.
