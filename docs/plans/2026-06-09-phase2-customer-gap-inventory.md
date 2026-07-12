# UBB Customer-Feature Gap Analysis — Decision-Ready Inventory

**Date:** 2026-06-09 · **Method:** 31-agent workflow across 10 customer-facing domains — code-grounded UBB capability map × market catalog (Stripe Billing, Metronome, Orb, Lago, Amberflo, m3ter, OpenMeter, Zuora, Chargebee, Togai) × honest delta. 103 gaps catalogued. North star: *what does the customer have access to on other platforms that they don't have here.*

## 1. Headline

UBB is **deep where it chose to fight and thin almost everywhere else** — and which "everywhere else" matters depends entirely on which of the two customer archetypes you optimize for. For the **cost-metering tenant** (meters provider COGS for visibility, never invoices an end-customer), UBB is close to complete today; almost none of the gaps bite them. For the **margin-billing tenant** (builds pricing cards, charges their own end-customers a margin), UBB hits a wall on day one for any deal more sophisticated than flat-or-linear per-unit pricing, and lacks most of the invoicing/AR, credit-lifecycle, and entitlements machinery competitors treat as baseline. The recurring pattern: many gaps are **self-inflicted "built-but-severed"** (the pricing engine's `usage_metrics` is unreachable from the SDK; the `tiers` field ships inert; `max_concurrent_requests` is displayed but never enforced; `uncollectible`/`void` are dead schema), and many others are **cheap to switch on precisely because UBB sits in front of Stripe** (tax, credit notes, hosted invoice URLs are latent in Stripe). The strengths are real and differentiated — money-safety, synchronous spend gating, per-customer margin — but ingestion ergonomics, pricing breadth, and the packaging layer sit a clear tier behind Orb/Metronome/Lago.

## 2. The Inventory

### (A) TABLE-STAKES MISSING — a typical customer expects this and UBB lacks it
| Capability | Who offers it | UBB today | Archetype | Effort |
|---|---|---|---|---|
| Caller-supplied event timestamp (`effective_at`) | Everyone | `auto_now_add` server wall-clock; no caller path; engine is time-aware (`as_of`) but endpoint never exposes it | Both (acute for margin w/ pipeline latency) | M |
| Tiered/graduated pricing | Everyone | `tiers` JSONField is a **dead stub**; `compute()` only does flat/per_unit | Margin | M |
| Volume / high-water-mark pricing | Everyone | Not implemented; no retroactive-rate path | Margin | M |
| End-customer usage/running-spend visibility (widget) | Metronome/Amberflo/m3ter/Orb/OpenMeter | Data+endpoint exist but only under **tenant API-key**; widget JWT can't reach it | Margin | M |
| Postpaid usage invoice on the `/me` surface | Stripe/Lago/Orb/Zuora | Only prepaid top-up **receipts** exposed; the real usage bill is invisible to the end-customer | Margin | M |
| RBAC / multi-user tenant access | All 10 vendors | No user/identity model; one API key = full tenant write | Both (acute margin) | XL |
| Published/hosted OpenAPI + API reference | Stripe/Orb/Lago/OpenMeter | Ninja auto-gen per-API JSON; nothing consolidated/hosted; no Postman collection | Both | M |
| Multi-language SDKs (TS/Node/Go/…) | Stripe(7)/Chargebee(7)/Orb(6) | Python only | Both (acute margin) | XL |

### (B) IMPORTANT (selected — full list in workflow output)
| Capability | UBB today | Archetype | Effort |
|---|---|---|---|
| `usage_metrics` reachable from the SDK | Built on platform, **omitted from SDK**; a test asserts its absence — flagship pricing unreachable | Margin | **S** |
| Batch / bulk event submission | Single-event POST only; no `/usage/batch` | Both (acute AI/LLM resale) | M |
| Event amendment / backfill (append-only correction) | Immutable by design; only money-refund, no data-correction/backfill | Both | L |
| Overage / included-units pricing | Not modeled; wallet not consulted by PricingService | Both | L |
| SDK `update_rate_card` + expired-card history read | PUT soft-versions on platform, but SDK can't update & **nobody can read the history** | Both | **S** |
| Named credit grants w/ expiry + sweep | No grant model, no `expires_at`, no expiry sweep | Margin | L |
| Multi-balance pools w/ drawdown priority | One `balance_micros`, one wallet/customer | Margin | L |
| Hard wallet-balance enforcement (stop-at-zero) | Record-then-deduct; can go negative; suspend only at `-min_balance` | Both (prepaid) | M |
| Tax calculation on invoices | Nothing — Stripe Tax could do it "for free" via connected account | Margin | M |
| Dunning / failed-payment recovery | Single-shot: payment_failed → **immediate suspend**, no retry/grace | Margin | M |
| Credit notes / credit memos | Wallet refund is money-correct but no AR document | Margin | M |
| Invoice delivery (hosted URL / PDF surfaced) | Finalizes Stripe invoices but doesn't surface `hosted_invoice_url`/`invoice_pdf` | Margin | **S** |
| Unit / quota entitlements (cap N units, not $) | Every gate is monetary micros; no unit counter | Both (acute margin) | L |
| Boolean feature-flag entitlements | Absent; no plan/tier object exists | Margin | M |
| Built-in alert delivery (email/Slack/webhook) | Exactly-once outbox events, **no delivery channel** | Both | M |
| Customer mutation API (update/suspend/reactivate/close) | Only POST create + GET; account immutable post-create | Both | M |
| `GET /customers` list/search/paginate | No list endpoint; must already know each `external_id` | Both | **S** |
| MRR/ARR roll-up + movement decomposition | Inputs exist; no roll-up or new/expansion/churn diff | Margin | M |
| Scoped / read-only API keys | All keys all-powerful; live/test prefix cosmetic | Both | M |
| Audit log (actor + action + target) | Strong event logs but no actor-keyed audit; blocked by no-user-model | Both (blocks SOC2) | M |
| Isolated sandbox / test-mode | `ubb_test_` prefix is **cosmetic** — no isolation, no test clock | Both | L |
| Webhook delivery inspection + replay | Data captured but **no read/replay endpoint** | Both | **S** |
| Encryption-at-rest for webhook signing secrets | Secret stored **plaintext** | Both | **S** |
| Operational multi-currency / FX | Stored not operational; USD hard-coded; mixed-currency analytics **silently mis-sum** | Margin (cross-border) | L–XL |

### (C) NICE-TO-HAVE (sample)
Package/block pricing (S) · stairstep (S) · minimum-spend true-up (M) · multi-phase plans (L) · credit rollover cap/reset (M) · concurrent-request limit — `max_concurrent_requests` is a **dead field** (S) · configurable budget periods (M) · RiskConfig CRUD (S) · server-side usage-list filters (S) · discounts/coupons (M) · async Python client + SDK batching (M) · MCP server / Terraform provider (L) · cohort/NRR/LTV (L) · revenue forecasting (M) · invoice customization (S).

### (D) IGNORABLE GIVEN POSITIONING
Multi-level (3+) hierarchy; multi-entity invoicing; per-seat license pricing; contact/identity on Customer (deliberately removed); percentage/take-rate & custom-formula pricing; contract-minimum commitments burn-down; alternate ingestion buses (Kafka/S3); 10k/s streaming; AR aging / GL-ERP connectors; ASC 606/IFRS 15 rev-rec + waterfalls; SSO/SAML/SCIM/MFA (no console to protect); SOC2/PCI/ISO attestations (operator responsibility for self-hosted); data residency/BYOK (self-hosting IS the answer); hosted billing portal + end-customer auth/login; CRM/Salesforce integrations. **Caveat:** multi-currency is "ignorable" only for US-first — the silent mixed-currency mis-sum is a latent *correctness trap*, not just a missing feature.

## 3. The "Easy Wins" (high value, low effort, fits fast/easy/risk-free — mostly "finish what's built")
1. **Add `usage_metrics` to the SDK `record_usage`** (S) — single highest value-to-effort fix; the flagship pricing engine is unreachable from every SDK consumer today. One signature change + flip one test.
2. **SDK `update_rate_card` + expired-card history endpoint** (S).
3. **Webhook delivery-inspection + replay endpoints** (S) — data already captured.
4. **Encrypt webhook signing secrets at rest** (S) — plaintext today; guaranteed security-review finding.
5. **`GET /customers` list/search/paginate** (S).
6. **Surface Stripe `hosted_invoice_url` / `invoice_pdf`** (S) — invoice delivery is latent in Stripe.
7. **Widget-scoped `/me/usage` + `/me/spend-status`** (M) — data + metering endpoint exist; closes the bill-shock-visibility gap.
8. **Decouple low-balance alert from AutoTopUpConfig** (S); **wire referral reward → wallet credit** (S); **RiskConfig CRUD** (S).
9. **Fix-or-remove dead fields** (S) — `max_concurrent_requests`, `uncollectible`/`void`. Stop implying capability the code lacks.
10. **Tier evaluator** (M, unlocks four shapes) — `tiers` field exists; implementing `compute()` yields graduated + volume + stairstep + package together. The highest-value *pricing* fix; well-scoped, not architectural.

## 4. The "Expensive but Maybe Necessary" (L/XL — necessity depends on WHO the customer is)
- **TS/Node SDK (XL)** — table-stakes for any margin-billing tenant on a non-Python backend; irrelevant to a Python cost-metering tenant. *Mitigation:* publish OpenAPI (M) first → self-generated clients converts XL→M for most.
- **Credit grants + expiry + multi-balance pools (L)** — the difference between "hold a prepaid balance" and "run a credits/trials growth program." Necessary IF targeting margin-billing self-serve funnels.
- **Event amendment / backfill (L)** — anyone running a real pipeline hits bad data; append-only supersede+re-rate preserves immutability. Interlocks with caller-timestamp + Stage-D reconciliation.
- **RBAC + user/identity model (XL)** — root cause of three "important" gaps (scoped keys, actor-audit-log, single-key blast radius). *Cheaper first step:* scoped read-only keys (M).
- **Operational multi-currency / FX (L–XL)** — broad surgery. Ignorable US-first; hard-blocking cross-border. Safe interim: reject/segregate non-USD events (S).
- **Overage / included-units pricing (L)** — how usage vendors monetize past the included bucket; cross-cuts tier engine + per-period allowance + wallet ledger.
- **Isolated sandbox with test clocks (L)** — partly mitigated for self-hosters; the `ubb_test_` prefix is a misleading promise today.

## 5. What UBB Is Genuinely AHEAD On (lead with these)
- **Money-safety as core competency** — exactly-once where the DB unique constraint IS the guarantee; immutable events; multi-path repairing reconciliation; now proven under real concurrency.
- **Synchronous pre-call spend gating** — single `RiskService.check()` choke point, Redis-fast + Postgres drift-repair. Only OpenMeter/Amberflo are in this leading minority; everyone else is post-ingestion.
- **Per-run / per-request hard cost+balance ceiling** — snapshotted, enforced under lock → 429 + run kill. **No surveyed competitor offers this natively.**
- **Per-customer margin / gross-margin analytics** — live + tenant-wide + dimensional + 36-month trend + business rollup + unprofitable/cost-spike alerting. Competitors treat margin as emerging; UBB is built around it.
- **Earned/accrual revenue-source disambiguation** — prevents postpaid double-count + metering-only invisible-COGS. The hard, valuable part, done right.
- **Two-card cost+price model in one call** + N-dimensional most-specific-wins matrix pricing + time-versioning + per-customer overrides. Matched natively only by Metronome/m3ter.
- **Above-weight webhook/security hygiene** — HMAC signing, outbound SSRF + DNS-rebind defense via IP pinning, outbox idempotency, backoff + dead-lettering, PII-redacting structured logging.
- **End-customer prepaid wallet visibility with an *actionable* top-up** — beats Orb (read-only) on the prepaid story.

## 6. Decision Questions for the Owner (the crux)
1. **Which archetype is the priority for the next two quarters — cost-metering or margin-billing?** Reclassifies ~half the inventory: nearly every "important" gap is margin-billing-only.
2. **US-first for the foreseeable future — yes/no?** If yes, FX deferred + only the small "reject non-USD events" safety step. If no, FX becomes a scheduled platform program.
3. **Do tenant staff touch UBB directly, or only via the tenant's own app?** If only via their app, RBAC/scoped-keys/audit can defer. If staff touch it directly or face SOC2 questionnaires → at least scoped read-only keys + actor-audit-log (presupposes a user model).
4. **Is "run a second instance via docker-compose" an acceptable sandbox story, or do customers expect in-product test-mode with isolation + test clocks?** A yes turns an L into a docs task.
5. **Is "publish OpenAPI, self-generate clients" acceptable for multi-language demand, or do we need a hand-written TS/Node SDK?** Converts the largest XL into an M — unless a marquee prospect demands a first-party TS client.
6. **Is immediate-suspend-on-first-payment-failure acceptable, or losing revenue/causing churn?** Arguably worse than no dunning; a grace-period + Stripe retry is an M that may be the highest-urgency margin fix regardless of Q1.
7. **Is per_unit + flat genuinely enough for target customers' first deals, or do we lose deals day-one without tiered/volume/overage?** If we lose deals, tier evaluator (M) + overage (L) move to the front.
8. **Do margin-billing tenants need a credits/trials growth program (grants + expiry + multi-balance), or is a single perpetual prepaid balance enough?** Decides whether the L credit-lifecycle body of work is in or out.
