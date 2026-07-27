# Plan as a kernel concept — design

**Date:** 2026-07-27 · **Status:** accepted, not yet implemented · **Pre-launch** (no production data)

Moves `Plan` out of `apps/subscriptions/` and into the platform kernel, gives it a third
commercial axis (markup), collapses the tenant-facing surface to one "Plans" page, and retires
the `subscriptions` product flag.

---

## 1. Problem

A plan, as tenants actually sell it, has **three** axes. Localscouta's real lineup:

| Plan | Access fee | Per seat | Markup on metered compute |
|---|---|---|---|
| Enterprise | $100/mo | $10/seat | 20% |
| Personal | $50/mo | — | 20% |
| Personal Lite | $0 | — | 50% |

Two axes are realized by Stripe (licensed Prices on a Subscription). The third —
markup — **Stripe structurally cannot represent**: it has no knowledge of provider cost.

Today `TenantBillingPlan` (`apps/subscriptions/models.py:84`) models only the two Stripe axes.
Markup lives in an unrelated model, `TenantMarkup` (`apps/metering/pricing/models.py:10`),
keyed by `(tenant, customer)`. Nothing links them. Four consequences, all verified against code:

1. **Personal Lite is unsellable.** `subscribe()` builds `items` from non-zero axes only
   (`apps/subscriptions/orchestration/service.py:179-183`) and then calls
   `stripe.Subscription.create` with no empty-check (`:192`). A $0/$0 plan produces `items=[]`,
   which Stripe rejects. The plan is creatable (`PlanIn` allows `ge=0`,
   `api/v1/schemas.py:882-883`) but no customer can be put on it.

2. **Markup silently falls back — a revenue leak.** `MarkupService.resolve` is
   `customer override → tenant default → None` (`apps/metering/pricing/services/markup_service.py:6-12`).
   The plan is invisible to it. Assign a customer to Personal Lite and omit the per-customer
   `TenantMarkup` row and they bill at the *tenant default* — 20% instead of 50% — on every
   event, with no error and no signal.

3. **The split leaks into the UI.** Access/seat fees are set on `/subscriptions`; markup is set
   on `/pricing` (`apps/ui/src/features/pricing/components/tenant-markup-card.tsx`). A tenant
   defines one commercial offer across **two pages**, and neither shows the whole thing. The
   subscriptions page ends with a dashed notice that the API cannot list plans back and that the
   tenant should "keep a record of" them elsewhere.

4. **The write surface is unauthenticated by product.** Plan creation, subscribe, seats, and
   cancel/pause/resume live on `platform_router` (`api/v1/platform_endpoints.py`), which has
   **zero** `ProductAccess` checks; `ApiKeyAuth.authenticate` (`core/auth.py:50`) performs no
   entitlement check either. Only the three *read* routes are gated
   (`apps/subscriptions/api/endpoints.py:35`). A tenant without the flag can create plans,
   provision real Stripe Prices, subscribe customers and cancel subscriptions — then receive
   403 `feature_not_enabled` when reading back what it just created.

### Root cause

`Plan` has two consumers — subscriptions (fee axes) and metering (markup axis) — and it was
filed under one of them. ADR-001 forbids the direct product↔product import that the missing
third axis would require, so the axis was simply never added.

---

## 2. Decision

**`Plan` becomes a platform-kernel concept.** Both products read it; neither owns it. This is the
same reasoning that already makes `Customer` "pure platform, zero billing imports" — multiple
products depend on it, none owns it.

```
apps/platform/plans/          Plan, CustomerPlanAssignment
        |                              |
  subscriptions                     metering
  realizes the Stripe axes          realizes the markup axis
  (Price provisioning, subscribe)   (markup precedence at rating time)
```

Any product may import `apps.platform.*` (ADR-001 rule 1), so this needs **no new cross-product
channel, no ADR amendment, and no cross-product read on the hot rating path.**

### Options rejected

- **(A) Markup as a field on `TenantBillingPlan`, copied into `TenantMarkup` on subscribe.**
  Creates a denormalized copy: editing a plan's markup leaves existing subscribers stale until a
  fan-out. This codebase runs eleven scheduled `reconcile-*` tasks precisely because unreconciled
  caches are its known failure mode; adding another is the wrong direction.
- **(B) Markup on the plan, metering resolves through `apps.subscriptions.queries`.** No copy and
  no drift, but requires adding `apps.subscriptions.queries` to `SHARED_READ_CONTRACTS`
  (`apps/platform/tests/test_product_boundaries.py:37`) and puts a cross-product read on the hot
  rating path, making subscriptions load-bearing for pricing.

---

## 3. Model

`apps/platform/plans/` follows the shape of the existing kernel module `apps/platform/dimensions/`
(`models.py`, `queries.py`, `services.py`, `admin.py`, `apps.py`, `migrations/`, `tests/`).

### `Plan`

| Field | Notes |
|---|---|
| `tenant` FK | |
| `key`, `name` | unique on `(tenant, key)` |
| `access_fee_micros` | ≥ 0; 0 = axis absent |
| `per_seat_micros` | ≥ 0; 0 = axis absent |
| `markup_percentage_micros` | `1_000_000 == 1%`, matching `TenantMarkup` |
| `fixed_uplift_micros` | matching `TenantMarkup` |
| `interval` | `month` \| `year`, validated (see §7) |
| `stripe_access_product_id` / `_price_id` | opaque binding |
| `stripe_seat_product_id` / `_price_id` | opaque binding |
| `provisioned_at`, `pricing_version` | |
| `archived_at` | null = active |

The Stripe id fields sit on a kernel model as an **opaque external binding the kernel stores but
never interprets** — only subscriptions reads or writes them. The alternative (a
`subscriptions.PlanStripeBinding` side-table) adds a join to every provision for no gain.

### `CustomerPlanAssignment`

`tenant`, `customer`, `plan`, `assigned_at`. Unique on `(tenant, customer)`.

This row is what makes Personal Lite work: a customer on a plan with **no Stripe presence at all**.

### `TenantMarkup` — retained

Unchanged. It becomes the *override* rung rather than the only rung, so a bespoke enterprise deal
does not require minting a one-off plan.

---

## 4. Ownership

| Concern | Owner | Rationale |
|---|---|---|
| Proration, invoicing, dunning, tax, retries | **Stripe** | Solved; never rebuild |
| Subscription status, amounts, periods | **Stripe** | One authority. UBB caches — see §9 |
| Seat *identity*, usage, provider cost, markup, margin | **UBB** | Stripe structurally cannot know these |
| Plan definition + assignment | **UBB kernel** | The only object spanning both engines |

**The governing rule.** Every piece of Stripe-owned state UBB stores is a cache: it has a refresh
path, a staleness bound, and it never decides money on its own. (The consolidation path,
`apps/billing/invoicing/services/postpaid_service.py:455-490`, already honours this — it uses the
mirror only to nominate a candidate, then re-queries Stripe and guards on live data.)

---

## 5. Markup precedence

One rung inserted into `MarkupService.resolve`:

```
customer TenantMarkup override  ->  customer's Plan  ->  tenant default TenantMarkup  ->  none
```

The signature and the `MarkupCache` contract (`apps/metering/pricing/services/markup_cache.py`)
are unchanged, so the hot path keeps its shape. Cache invalidation must extend to plan writes and
assignment changes, not only `TenantMarkup.save/delete` (`models.py:38-48`).

A `meter_only` tenant has no plan assignments, so the chain falls through to the tenant default
with no branch and no special case. Note that markup is the *last-resort* price source anyway —
the full precedence is `caller_billed → price rate card → markup`
(`apps/metering/pricing/services/pricing_service.py:130-151`).

**Rate cards are unrelated to plans** and stay that way. They describe what compute *costs*;
markup describes what the customer *pays on top*.

---

## 6. API surface

New kernel router at `/api/v1/plans`, full CRUD:

```
GET    /plans                          list
POST   /plans                          create
GET    /plans/{key}                    read
PATCH  /plans/{key}                    update
DELETE /plans/{key}                    archive (409 if assigned)
POST   /customers/{external_id}/plan   assign
```

Subscription lifecycle verbs (`subscribe`, `seats`, `cancel`, `pause`, `resume`) move off
`platform_router` to `/api/v1/subscriptions/`, where the reads already live.

Breaking change — free pre-launch. `openapi/v1.json` regenerates per ADR-002
(`scripts/export_openapi.py`), and the generated UI/SDK clients follow.

### Repricing semantics (deliberate asymmetry, must be documented in `CONTEXT.md`)

- **Fee axes are grandfathered.** Stripe Prices are immutable, so a fee edit mints a new versioned
  Price; existing subscribers keep the old one unless `migrate_existing=true`.
- **Markup is live.** It has no Stripe object. A markup edit applies to the next rated event for
  every customer on the plan.

---

## 7. Product flag

`subscriptions` is **retired** from `VALID_PRODUCTS` (`apps/platform/tenants/models.py:15`).

It is not a standalone product: it is a wrapper over Stripe Billing, valuable only next to
metering and margin. A tenant who does not want those has no reason to buy it. Supporting
evidence — `ProductAccess("subscriptions")` occurs **exactly once** in the codebase; the
subscriptions app's largest surface (13 margin endpoints) already gates on `metering`;
subscriptions structurally depends on billing's Connect flow and Stripe connector kit; and it is
not a pricing lever (`ProductFeeConfig.product` is a free CharField with no subscriptions
reference in `tenant_billing/services.py`).

| Surface | Gate |
|---|---|
| Plans (all three axes) | `billing` |
| Subscription lifecycle + reads | `billing` |
| Markup via tenant default / price cards | ungated |

Gating on `billing` costs nothing: `billing` in `products` does not force a `billing_mode`, so a
tenant wanting fees but not usage-billing sets `products=[metering, billing]`,
`billing_mode=meter_only`. This also collapses problem 4 — one flag, applied uniformly.

---

## 8. Tenant-facing surface

The tenant's mental model is **what I sell** / **who's on what** / **what it costs me**. None of
those is "subscriptions". The internal split must not appear in the UI.

| Today | After |
|---|---|
| `/subscriptions` (fees) | **`/plans`** — all three axes, one page |
| `/pricing` (rate books + markup card) | **`/pricing`** — provider cost only; markup card removed |
| Stripe connect status on `/subscriptions` | **Settings** — it is account config |

`/subscriptions` disappears as a tenant-facing concept.

**Plans page** — one table: Plan · Access · Per seat · Markup · Customers. Personal Lite reads as
a normal plan that charges no fees, not a broken case. Create/edit is one form, three fields.

**Customer page** — one "Plan & billing" panel: plan, seats, status, next renewal, and actions
(change plan, seats, pause, cancel). No "assignment" vs "mirror" distinction is surfaced.

**The one place the boundary shows.** If Stripe is not connected, the *fee* fields are disabled:
*"Connect Stripe to charge access or seat fees. Markup-only plans work without it."* It is
actionable, so it earns its place. Principle: **surface the boundary only where the tenant must
act on it.**

---

## 9. Bundled fixes

Same seam; shipping them together avoids five follow-up PRs.

1. **Wire the mirror reconciler.** `sync_tenant_subscriptions_task`
   (`apps/subscriptions/tasks.py:172`) is defined and referenced nowhere — it is dead code and
   never entered `CELERY_BEAT_SCHEDULE`. `CELERY_BEAT_SCHEDULE` carries eleven scheduled
   `reconcile-*` tasks; the Stripe subscription mirror — the one table that is purely a cache of
   another system's state — has none. Its only refresh paths are webhooks and a manual
   `POST /subscriptions/sync`, so a missed `customer.subscription.deleted` leaves a canceled
   subscription displayed as active indefinitely. Add it hourly.
2. **Zero-axis guard on subscribe.** Return cleanly instead of calling Stripe with `items=[]`.
3. **Validate `interval`.** `Literal["month", "year"]`; it is an unvalidated `str` today.
4. **Surface plan fee drift.** Show Stripe's live Price amount alongside the stored value on read,
   so a Stripe-dashboard edit is visible rather than silent.
5. **Rename `TenantBillingPlan` → `Plan`,** removing the collision with `tenant_billing`'s "what
   the tenant pays UBB".
6. **Correct the living docs.** `CLAUDE.md` and `docs/architecture/positioning.md` both assert
   "Stripe owns … subscription/seat lifecycle" and list "full subscription lifecycle" under *does
   not build*. That was the 2026-06-05 repositioning decision; it was reversed four days later by
   the J2 program and the reversal was recorded only in a dated plan doc
   (`docs/plans/2026-06-10-program-current-state.md`, marked AUTHORITATIVE). The two documents an
   agent reads first every session are the two that are wrong. Replace with the §4 ownership
   table.

---

## 10. Migration

Pre-launch, no production data — clean removal, no compatibility scaffolding (matching the
repositioning doc's "pre-production ⇒ clean removal"):

- New table `ubb_plan`; **drop** `ubb_billing_plan`. No `SeparateDatabaseAndState`.
- `CustomerSubscriptionItem.plan` repoints to the kernel `Plan`.
- Branch fresh off `origin/main`. The current branch (`feat/unified-dimension-model`) carries 10
  unmerged commits of independent work; PRs here are squash-merged, so mixing them would produce
  a misleading diff.

---

## 11. Testing

- **Boundary** — `test_product_boundaries.py` proves metering and subscriptions reach plans only
  via `apps.platform.plans`; no new entry in `SHARED_READ_CONTRACTS`.
- **Rating, per tier** — Personal Lite bills at 50%. The test must **fail** if resolution falls
  through to the tenant default; this pins problem 2 so the leak cannot silently return.
- **Zero-axis subscribe** — Personal Lite creates no Stripe Product, Price, Subscription, or
  Customer, and returns success.
- **Entitlement** — a tenant without `billing` receives 403 on every plan and lifecycle route;
  a `meter_only` tenant still rates events via tenant-default markup.
- **Repricing** — a fee edit grandfathers existing subscribers; a markup edit applies to the next
  rated event.
- **Reconciler** — a mirror row diverged from Stripe is repaired by the scheduled task.
- **Spec** — `openapi/v1.json` regenerated; CI drift/breaking/TS gates pass.

---

## 12. Non-goals

- Trials and coupons — Stripe owns these; unchanged.
- Linking plans to rate cards. Rate cards are cost sheets; the plan's price axis is markup.
- Tiered/graduated pricing — deleted end to end per ADR-0003; not reinstated.
- Rebuilding any Stripe billing behaviour (proration, dunning, tax, invoicing).

---

## 13. Consequences

- One commercial object spans both engines, so the UI can be organized around what tenants
  actually think in.
- A customer can be on a real plan, generating real margin, with zero presence in Stripe Billing.
- One product flag fewer; one uniform entitlement gate.
- `apps/subscriptions/` narrows to what it is: the Stripe subscription engine adapter plus unit
  economics.
- Fold the outcome into `apps/platform/CONTEXT.md` (new Plan vocabulary), `CONTEXT-MAP.md`, and
  `apps/subscriptions/CONTEXT.md` (Billing plan entry moves; repricing asymmetry documented), per
  the ratchet in `CLAUDE.md`.
