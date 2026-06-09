# UBB Functional + Competitiveness Review — Anchored on the Two Customer Journeys

**Date:** 2026-06-09 · **Method:** 15-agent deep code trace of all 12 sub-flows of the two journeys × head-to-head with the giants × synthesis. Three load-bearing claims independently re-verified by the controller (SDK rate-card 404; analytics reports billed-not-provider; no Stripe subscription orchestration).

**Bottom line up front:** UBB's *engine* is genuinely good and, for cost-attribution, conceptually ahead of the giants. But the **paved path (SDK + onboarding) is broken or absent at exactly the points that decide "easy to adopt,"** and **two of J2's three billing axes are not orchestrated at all** — the tenant builds them by hand in Stripe. A strong core wrapped in a client surface that 404s, drops to raw HTTP, or doesn't exist. The gap to "competitive" is mostly **plumbing + one real feature (subscription orchestration)** — not architecture.

## 1. Verdict per journey

### JOURNEY 1 — Cost-attribution metering — **Grade: C+ (B- engine, D paved path)**
A Type-1 tenant **can** get "which customer costs me what, and on what" — but only by abandoning the SDK and hand-rolling raw HTTP. The data model + pricing engine are correct and well-tested (`UsageEvent` carries customer + product_id + tags + multi-metric `usage_metrics`; the cost rate-card resolver does customer-specific-beats-default + most-specific-dimension-wins; `/analytics/usage` returns per-customer + dimensional breakdowns). **No competitor ingests true per-event COGS as a first-class input the way UBB does** — a real edge.

**On the owner's belief that "UBB already does per-customer cost-by-product/service/agent": PARTLY TRUE, materially overstated.**
- **TRUE:** the engine computes + stores it; the analytics endpoint can return it.
- **FALSE/overstated in three ways:** (1) **"agent" and "service" are not fields** — only `product_id` is first-class; agent/service are undocumented tag conventions the tenant must invent and mirror on *both* the card dimensions *and* every event, or the metric silently prices to **$0** (`require_cost_card_coverage` defaults off). (2) **The SDK cannot reach the cost engine** — `record_usage` forces caller-supplied `provider_cost_micros` and never sends `usage_metrics`, so configured rate cards are **inert via the official client**. (3) **The one correct read endpoint has no SDK method, and the breakdown columns report `billed_cost`, not `provider_cost`** — the wrong column for a flat-fee J1 tenant; the genuinely-correct per-customer COGS lives behind the *margin* endpoints, mislabeled for this use case. **The insight exists in the database; it does not exist on the paved path.**

### JOURNEY 2 — Multi-axis billing — **Grade: D+ (one axis works, two are absent)**
A Type-2 tenant **cannot** adopt the access-fee + per-seat + usage model coherently through UBB. Of the three axes, **UBB orchestrates exactly one (usage)** — and that one is genuinely good (two-card cost+margin at the choke point, clean prepaid drawdown vs postpaid Stripe-InvoiceItem push, money-safety). But **axes (a) flat access fee and (b) per-seat are 100% manual Stripe work** — UBB never calls `Subscription.create`/`Price.create`/`SubscriptionItem` (the subscriptions app is a read-only mirror *by design*). And a tenant **can't even self-serve the configuration**: no endpoint to set `billing_mode`, connect Stripe, or create a tenant — those are admin/DB/seed actions.

## 2. Where each journey breaks

### J1 break points (death by a thousand S-sized cuts)
| # | Wall | Failure | Effort |
|---|---|---|---|
| 1 | SDK can't price from cost cards | `record_usage` requires `provider_cost_micros`, omits `usage_metrics` (metering.py:67-79) | **S** |
| 2 | Rate-card SDK methods 404 | SDK→`/api/v1/pricing/rate-cards`; server→`/api/v1/metering/pricing/rate-cards`; mocked tests hid it | **S** |
| 3 | No agent/service axis; silent $0 on mismatch | tag convention the tenant must guess + mirror; typo → wildcard or $0, no error | **M** |
| 4 | Analytics breakdown reports the wrong column | `by_*` rows sum `billed_cost_micros`, not `provider_cost_micros` | **S** |
| 5 | No SDK wrapper for the working read endpoint; dead `get_economics*` 404 | tenant hand-builds query strings; SDK points at removed routes | **S** |
| 6 | No enum validation on `card_type`/`pricing_model` | `card_type='costs'` 200s + silently never prices → COGS=0 | **S** |
| 7 | Onboarding misleads | `seed_dev_data` prints curl to dead endpoints on wrong port; no SDK README; no UI | **S** |

### J2 break points
| # | Wall | Failure | Effort |
|---|---|---|---|
| 1 | No access-fee subscription orchestration | no `Subscription.create`/`Price.create`; tenant builds it in Stripe; UBB only mirrors | **L** |
| 2 | No per-seat orchestration | adding a "seat" Customer is a pure DB insert, zero Stripe calls; quantity/proration by hand | **L** |
| 3 | Sync silently drops the seat line | `sync` reads legacy `.plan`/`.quantity` (one item); a 2-line sub records as a single amount → corrupts margin | **M** |
| 4 | No self-serve config | no endpoint to set `billing_mode`, connect Stripe (no AccountLink/OAuth), or create a tenant | **M** |
| 5 | Postpaid invoice is fire-and-forget | `finalize_invoice` returns hosted_invoice_url/pdf but only `inv.id` kept; status caps at `pushed`, no paid/void, no webhook reconcile | **M** |
| 6 | `/me/invoices` omits usage invoices | end-customer can't view/pay their usage bill from UBB | **S–M** |

## 3. The coherence question (J2) — make-or-break
**No. UBB does not assemble a coherent multi-axis bill. It orchestrates the usage axis and free-rides on Stripe's native InvoiceItem sweep for the rest.** The "one bill" only emerges because **Stripe** merges pending InvoiceItems onto the subscription's next invoice — *if* the tenant has already, by hand, created the Stripe Customer + access-fee Product/Price + per-seat Product/quantity Price + the Subscription with both items. UBB's only contribution is pushing usage InvoiceItems and hoping Stripe sweeps them. **There is no UBB plan object binding the three axes**, no period-alignment control, and a real failure mode: if the tenant forgets to wire the subscription, UBB silently bills usage on a *separate standalone invoice* — splitting the bill. For **prepaid** usage there's no combined document at all (usage is a wallet drawdown outside Stripe). The promise "adopt the whole model coherently via UBB" is **one-third delivered.**

## 4. Ease-of-adoption reality check
- **J1 — conceptually easier to adopt, loses the last mile.** Time-to-first-event is genuinely smaller than the giants (COGS as a *direct input* + native margin column, no Stripe/plan/invoice required). But time-to-insight-in-front-of-a-human is worse: Metronome/Orb give embeddable themeable cost dashboards with time-series; UBB gives JSON with no rollup, no UI, and a broken SDK to fetch it. **Today the broken paved path cancels the conceptual edge.** Fix Wave 1 and UBB is legitimately easier than the giants for the warehouse-bound Type-1 profile.
- **J2 — harder as a whole, easier for the usage slice only.** For a tenant who *already* runs access+seats in Stripe and wants a cost-aware, real-time-gated, margin-visible usage layer in front, UBB is the **easiest + most fit-for-purpose** option (real-time pre-spend gate, cost+margin, pooled-wallet/per-seat-caps, exactly-once top-ups — not offered the same way by Orb/Lago/Metronome). For a greenfield tenant standing up all three axes "coherently," UBB is **harder than every alternative** (Orb/Lago/Stripe express all three in one plan→one invoice; UBB has no plan object).

**Are we at "so easy + risk-free we steal share"? Not yet.** The 5 things most blocking it: (1) the SDK doesn't reach your own engine; (2) no subscription orchestration (J2 a+b); (3) no self-serve onboarding; (4) no payment-status reconciliation + no UI; (5) silent-$0 / silent-mirror failure modes (robust requires *loud* failures).

## 5. Refined, journey-anchored roadmap (supersedes the generic Wave 1–6)
Stripe owns the document → all AR-side items are "integrate Stripe's existing fields," not "build invoicing."

**Wave 1 — Make J1's paved path actually work (all cheap, first):** fix SDK rate-card URL prefix + add a live-server integration test (S) · `record_usage` add `usage_metrics` + make `provider_cost_micros` optional (S) · add provider_cost columns to every `/analytics/usage` row (S) · wrap `/analytics/usage` in the SDK + delete dead `get_economics*` (S) · enum-validate `card_type`/`pricing_model` + flip `require_cost_card_coverage` to a loud default (S) · fix `seed_dev_data` + ship an SDK README with the J1 happy path (S).

**Wave 2 — Make J1 genuinely excellent (the differentiator):** first-class **service/agent** alongside `product_id` (or validated dimension keys) + matching analytics axes (M) · multi-key breakdown in one call (S–M) · native **time-series spend rollup** (hourly/daily per dimension) (M) · bulk rate-card create + SDK `update_rate_card` (S) · minimal embeddable cost dashboard (L).

**Wave 3 — Make J2 self-serve (config before orchestration):** tenant-config API for `billing_mode`/products (M) · Stripe Connect onboarding (AccountLink/OAuth) (M) · SDK `set_markup`/`get_markup` (S).

**Wave 4 — Make J2 coherent (the real feature):** **outbound subscription orchestration** — create Stripe Product+Price+Subscription for access fee + per-seat item; one tenant-facing "plan" abstraction binding all 3 axes (L–XL) · push **seat quantity + proration** to Stripe on seat add/remove + reconcile UBB↔Stripe (L) · fix sync to read **subscription items** not legacy `.plan`/`.quantity` (M).

**Wave 5 — Close trust/AR-visibility:** store `hosted_invoice_url`+`invoice_pdf` on `CustomerUsageInvoice` at finalize + add paid/open/void states (M) · wire `invoice.paid`/`payment_failed`/`voided` webhooks → reconcile + correct margin (M) · expose usage invoices on `/me/invoices` with the hosted link (S–M).

## 6. The honest bottom line
**J1 — one Wave (mostly S) away from genuinely competitive, and conceptually ahead.** The engine already does what the owner believes; the data is correct. What's missing is that **the paved path can't reach your own engine.** None of it is architectural. Ship Wave 1 → a Type-1 tenant has a *smaller, truer* adoption surface than Metronome/Orb/Lago for cost attribution (COGS-as-direct-input + native margin is a real, defensible edge no giant matches). Add Wave 2 and you can credibly claim the easiest cost-attribution onboarding on the market. **Critical path: Wave 1 (days).**

**J2 — not close, and the gap is a real feature, not plumbing.** Today UBB delivers one of three axes and can't self-serve even that. The usage slice is excellent + differentiated, but "adopt the whole model coherently" is **one-third true**, and the coherence only exists because Stripe sweeps your InvoiceItems. To make the J2 claim honest you must **orchestrate Stripe subscriptions + seat quantity (Wave 4)** and **let tenants self-configure + connect Stripe (Wave 3)**. Encouraging part: you *already* orchestrate Stripe for top-ups + usage pushes, so subscription/seat create+update is an **incremental L/XL, not new architecture.** **Critical path: Wave 3 → 4 (weeks).**

**Strategic recommendation:** sequence ruthlessly — **make J1 best-in-class first** (cheapest, highest ease-of-adoption ROI, no Stripe-write risk, already ahead), use it to win the Type-1 wedge — and **do not market J2 as "the whole model in one place" until Wave 4 ships** (today that claim is false; a sophisticated buyer finds the seam in the first demo). Until then, position J2 honestly as *"the cost-aware, gated, margin-visible **usage layer** in front of your existing Stripe subscriptions"* — true, differentiated, and the easiest option for that buyer.
