# Wave 3 — Make Journey-2 Self-Serve CONFIG (Design)

**Date:** 2026-06-09 · **Method:** 6-agent code-grounded design analysis (map tenant-config + Stripe-Connect + markup seams → design each item → competitor onboarding bar → synthesis).

**Goal:** A tenant can configure its own billing without an operator touching the DB — the **prerequisite** for Wave 4 (outbound Stripe subscription orchestration). Wave 3 is **CONFIG only**: (1) tenant-config API, (2) Stripe Connect onboarding, (3) SDK markup. It does NOT orchestrate access-fee/per-seat subscriptions — that's Wave 4.

## 1. Tenant-config API — SELF-CONFIG ONLY (S, no migration)
Tenant *creation*/signup is deferred (different auth domain — no API key exists before the tenant — and Wave 4 doesn't need it). Add to the existing `platform_api` (`api/v1/platform_endpoints.py`, `ApiKeyAuth`, `/api/v1/platform/`, SDK-reachable):
```
GET   /api/v1/platform/tenant/config  -> 200 TenantConfigOut
PATCH /api/v1/platform/tenant/config  -> 200 TenantConfigOut | 422 {error, code}
```
Operate on `request.auth.tenant` ONLY (never a tenant_id in path/body). PATCH so a tenant flips one field without restating `products`. **No `ProductAccess`** (config is the meta-layer that grants products — a product gate would be circular). `Tenant.clean()`/`save()` already enforce the invariants (metering-required, billing-required-for-prepaid/postpaid, dedupe, cache-bust) → thin handler: assign, `save()`, translate `ValidationError` → 422 (pass `message_dict` through).

**Field matrix:** `billing_mode` (tenant), `products` (tenant — *pending Decision C*), `require_cost_card_coverage` (tenant, with safety gate); operator-only: `platform_fee_percentage`, `is_active`, `stripe_connected_account_id` (Connect-flow only — never free-text or a tenant could point at another's `acct_`), `default_currency` (USD invariant).

**Load-bearing safety gate:** flipping `require_cost_card_coverage=True` with zero active cost cards makes `PricingService` 422 on EVERY `record_usage` — a silent foot-gun. The handler refuses to arm it without active cost cards (`RateCard.objects.filter(tenant, card_type="cost", is_active=True).exists()` → 422 `no_cost_cards`). Disabling is always allowed.

**SDK:** `get_tenant_config()` + `update_tenant_config(*, billing_mode=None, products=None, require_cost_card_coverage=None)` (drop None keys). All fields already exist on `Tenant` → no model change.

## 2. Stripe Connect onboarding (M, one field migration)
**Recommended: Express, UBB-managed, Stripe-hosted AccountLink** — self-serve KYC hosted by Stripe (UBB only issues a one-use link), fits the existing platform-charges-on-behalf model (`stripe_account=connected_account` everywhere), minimal new surface (reuses the webhook pipeline). *(Liability posture is Decision A.)*

- **Migration:** `Tenant.charges_enabled = BooleanField(default=False)` (the webhook is its only writer). Reuse the blank `stripe_connected_account_id`.
- **Service** `apps/billing/connectors/stripe/connect.py`: `create_or_get_connect_account(tenant)` — `Account.create(type="express", country="US", capabilities={card_payments, transfers}, metadata={ubb_tenant_id}, idempotency_key="connect-acct-{tenant.id}")` (NOT scoped with `stripe_account=` — it creates the account *on the platform*; the idempotency key guards retry-before-persist), persist `acct_` onto the calling tenant only; `create_onboarding_link(account_id, return_url, refresh_url)` — `AccountLink.create(type="account_onboarding")` → single-use ~5-min URL.
- **Endpoints** new router `/api/v1/connect/` (`ApiKeyAuth`, mounted before the catch-all `api/v1/`): `POST /connect/onboard {return_url, refresh_url} -> {onboarding_url, account_id, charges_enabled}`; `GET /connect/status -> {account_id, charges_enabled, onboarded}` (reads Tenant fields; live `Account.retrieve` fallback if `charges_enabled` is False so a missed webhook can't stick). Scoped to `request.auth.tenant`. NOT gated behind `ProductAccess('billing')` (a meter_only tenant may connect before flipping billing_mode).
- **Webhook:** `"account.updated": handle_account_updated` in `WEBHOOK_HANDLERS` — match `Tenant` by `stripe_connected_account_id == event.account`, set `charges_enabled = bool(acct.charges_enabled and acct.payouts_enabled)`, idempotent.
- **Charge gating:** add a `charges_enabled` check at the charge choke points (`charge_saved_payment_method`/`create_checkout_session`/postpaid finalize) so UBB never charges an account that started but hasn't cleared KYC.
- **Security:** caller = tenant's own key; `acct_` persisted to the calling tenant only; no Stripe secret ever returned (only the hosted URL + the non-secret `acct_`); AccountLink single-use/short-lived; USD preserved (`country="US"`). **Preflight:** platform Connect must be enabled on `STRIPE_SECRET_KEY` or `Account.create` fails — gate behind a config check with a clear error.
- **SDK:** `start_connect_onboarding(return_url, refresh_url)`, `get_connect_status()`.
- Wave-4 note: charge model will be **destination charges + `application_fee_amount`** (operator revenue) — but that lands in Wave 4.

## 3. SDK markup (S, no server change — endpoints already exist)
Server `metering_endpoints.py:163-216` + `schemas.py:146-153` confirmed present (`ProductAccess('metering')`; `1_000_000 micros == 1%`). Add `@dataclass(frozen=True) TenantMarkup {markup_percentage_micros, fixed_uplift_micros}` (`types.py`), and on `MeteringClient` (keyword-only money args, tolerant construction): `get_markup()` (GET `/pricing/markup`, never 404s, `{0,0}` unset), `set_markup(*, markup_percentage_micros=0, fixed_uplift_micros=0)` (PUT), `get_customer_markup(customer_id)` (GET, **404s on unknown customer**, returns the *resolved* value), `set_customer_markup(customer_id, *, ...)` (PUT). Four `UBBClient` delegates. Document `get_customer_markup` returns the *resolved* value (`{0,0}` doesn't prove an override).

## 4. Open owner decisions
- **A — Stripe Connect account type (liability posture).** *Recommend Express.* Express = UBB is platform-of-record → UBB carries dispute/negative-balance liability + must surface in tenant ToS; tenants get a limited Express Dashboard; UBB has strong control to drive PaymentIntents/Invoices (needed for Wave-4 orchestration). Standard+OAuth = tenants bear their own merchant liability + keep a full Stripe Dashboard, but adds an OAuth callback + app registration and weakens UBB's control. Endpoints/webhook/SDK/`charges_enabled` are identical either way.
- **B — Tenant signup scope.** *Recommend defer* (self-config only; a new tenant still gets its first key via admin/seed). Wave 4 doesn't need it.
- **C — Can a tenant grant ITSELF the `billing`/`subscriptions` product?** Commercial call: if products gate paid tiers / `platform_fee` terms → make `products` operator-only (tenant sets only `billing_mode` + `require_cost_card_coverage`; `billing_mode→prepaid/postpaid` returns 422 "enable billing first" until an operator grants it). If fully self-serve OSS → keep `products` tenant-settable.

## 5. Build sequence + capstone
1. SDK markup (S) — pure additive; de-risks the SDK piggyback pattern. 2. Tenant-config API (S) — no migration. 3. Stripe Connect (M) — `charges_enabled` migration + `connect.py` + `/connect/` router + `account.updated` webhook + charge gating.

**Capstone (SDK-only, proves self-serve config + onboarding):**
```python
c = UBBClient(api_key=tenant_key)
c.set_markup(markup_percentage_micros=20_000_000)
c.update_tenant_config(billing_mode="prepaid", products=["metering","billing"])
assert c.get_tenant_config()["billing_mode"] == "prepaid"
link = c.start_connect_onboarding(return_url=..., refresh_url=...)   # hosted KYC at link["onboarding_url"]
# account.updated webhook flips charges_enabled
assert c.get_connect_status()["onboarded"] is True
```
Proves a tenant self-configures billing + margin AND starts Stripe Connect onboarding with zero operator/DB action — the exact D+ gaps closed and the exact preconditions Wave 4 needs (`billing_mode`, `products`, a real `stripe_connected_account_id`, `charges_enabled`). **Scope boundary:** Wave 3 makes config self-serve; it does NOT create `Subscription`/`SubscriptionItem` on the connected account — that's Wave 4.
