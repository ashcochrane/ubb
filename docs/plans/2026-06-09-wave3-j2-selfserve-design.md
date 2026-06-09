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

## 2. Stripe Connect onboarding — STANDARD OAuth (DECIDED; M)
**The tenant connects their OWN existing Stripe account via Standard OAuth** ("Connect to Stripe"). This is the industry standard (Metronome/Orb/Lago/m3ter/Chargebee all integrate with the merchant's own account; none provision Express sub-merchants — that's the marketplace model). It keeps the tenant as **merchant-of-record** with **Stripe-branded invoices**, leaves KYC + dispute/chargeback + negative-balance liability with the tenant and Stripe (minimal UBB burden — UBB is a connected app, NOT a payment facilitator), and "improves as Stripe improves." **The codebase already passes `stripe_account=<connected_account>` on every call → ZERO charge-path code changes; only onboarding differs.** (Research brief: `docs/plans/2026-06-09-wave3-stripe-connect-research.md` if saved; summary in this design.)

- **Config:** `STRIPE_CONNECT_CLIENT_ID` (the operator's Stripe Connect platform-app client id) + the configured redirect URI. Preflight: error clearly if `STRIPE_CONNECT_CLIENT_ID` is unset.
- **Migrations (2, additive):** `Tenant.charges_enabled = BooleanField(default=False)`; a `ConnectOAuthState` model `(tenant FK, state CharField unique/indexed, return_url, created_at, expires_at, used BooleanField)` — the single-use CSRF/identity nonce for the browser-initiated callback.
- **Service** `apps/billing/connectors/stripe/connect.py` (platform `stripe.api_key`, NOT `stripe_account=`): `build_authorize_url(tenant, return_url)` — create a `ConnectOAuthState` (unguessable `secrets.token_urlsafe` state, short expiry), return `https://connect.stripe.com/oauth/authorize?response_type=code&client_id=<id>&scope=read_write&state=<state>`; `complete_oauth(code, state)` — validate the state (exists, unused, unexpired) → `stripe.OAuth.token(grant_type="authorization_code", code=code)` → `stripe_user_id` (the connected `acct_`) → persist onto THAT state's tenant only → mark state used → `Account.retrieve(stripe_account=acct)` to set `charges_enabled`.
- **Endpoints** new router `/api/v1/connect/` (mounted before the catch-all `api/v1/`):
  - `POST /connect/start` (**ApiKeyAuth**) `{return_url}` → `{authorize_url}` (scoped to `request.auth.tenant`).
  - `GET /connect/callback?code=&state=` (**NO auth** — browser redirect from Stripe; the single-use `state` is the identity+CSRF guard) → completes the exchange, then HTTP-redirects to the state's `return_url` (success/failure query param). Validate state strictly (unknown/used/expired → error, never mutate).
  - `GET /connect/status` (**ApiKeyAuth**) → `{account_id, charges_enabled, onboarded}` (reads Tenant; live `Account.retrieve` fallback if `charges_enabled` is False so a missed webhook can't stick). NOT gated behind `ProductAccess('billing')` (a meter_only tenant may connect first).
- **Webhooks** (add to `WEBHOOK_HANDLERS`): `account.updated` → match `Tenant` by `stripe_connected_account_id == event.account`, set `charges_enabled = bool(acct.charges_enabled)`, idempotent; `account.application.deauthorized` → the tenant revoked the connection → clear `stripe_connected_account_id` + `charges_enabled=False`.
- **Charge gating:** add a `charges_enabled` check at the charge choke points (`charge_saved_payment_method`/`create_checkout_session`/postpaid finalize) so UBB never charges a connected account that isn't charge-ready.
- **Security:** `/start` + `/status` scoped to the tenant's own key; the callback is identified solely by the single-use, expiring `state` (CSRF + identity); UBB stores only the non-secret `acct_` (no long-lived API secret — the OAuth token model); USD preserved.
- **SDK:** `start_connect_onboarding(return_url) -> {authorize_url}`, `get_connect_status() -> dict`.
- Wave-4 note: charge model will be **direct charges on the connected account** (already in place via `stripe_account=`); subscription/price/invoice creation on the Standard connected account works identically — that orchestration is Wave 4.

## 3. SDK markup (S, no server change — endpoints already exist)
Server `metering_endpoints.py:163-216` + `schemas.py:146-153` confirmed present (`ProductAccess('metering')`; `1_000_000 micros == 1%`). Add `@dataclass(frozen=True) TenantMarkup {markup_percentage_micros, fixed_uplift_micros}` (`types.py`), and on `MeteringClient` (keyword-only money args, tolerant construction): `get_markup()` (GET `/pricing/markup`, never 404s, `{0,0}` unset), `set_markup(*, markup_percentage_micros=0, fixed_uplift_micros=0)` (PUT), `get_customer_markup(customer_id)` (GET, **404s on unknown customer**, returns the *resolved* value), `set_customer_markup(customer_id, *, ...)` (PUT). Four `UBBClient` delegates. Document `get_customer_markup` returns the *resolved* value (`{0,0}` doesn't prove an override).

## 4. Decisions (RESOLVED)
- **A — Connect model: STANDARD OAuth** (the tenant connects their own Stripe). Chosen over Express because Express would make UBB the platform-of-record (KYC owner, dispute/fraud responsibility, negative-balance backstop → payment-facilitator burden) — the opposite of the owner's "minimize our regulatory burden, Stripe-branded invoices, improve-as-Stripe-improves" stance, and against the industry standard. Zero charge-path changes (already `stripe_account=`).
- **B — Tenant signup: DEFERRED.** Self-config only; a new tenant still gets its first key via admin/seed. Wave 4 doesn't need it.
- **C — `products` is TENANT-SETTABLE** (self-serve). UBB monetizes via the per-usage `platform_fee`, not by gating products, so self-enablement leaks no revenue and keeps onboarding zero-friction. Revisit if paid product tiers are ever introduced.
- **D — SDK markup return type: typed dataclass** (`TenantMarkup`), consistent with the `CustomerRevenue` sibling. (Engineer's call.)

## 5. Build sequence + capstone
1. SDK markup (S) — pure additive; de-risks the SDK piggyback pattern. 2. Tenant-config API (S) — no migration. 3. Stripe Connect (M) — `charges_enabled` migration + `connect.py` + `/connect/` router + `account.updated` webhook + charge gating.

**Capstone (SDK-only, proves self-serve config + OAuth onboarding):**
```python
c = UBBClient(api_key=tenant_key)
c.set_markup(markup_percentage_micros=20_000_000)
c.update_tenant_config(billing_mode="prepaid", products=["metering","billing"])
assert c.get_tenant_config()["billing_mode"] == "prepaid"
res = c.start_connect_onboarding(return_url="https://tenant.example/done")
assert res["authorize_url"].startswith("https://connect.stripe.com/oauth/authorize")  # the "Connect to Stripe" URL
# tenant authorizes → Stripe redirects to /connect/callback?code&state → we exchange + persist acct_;
# (test drives the callback directly with stripe.OAuth.token mocked) then account.updated webhook flips charges_enabled
assert c.get_connect_status()["onboarded"] is True
```
Proves a tenant self-configures billing + margin AND connects its own Stripe via OAuth with zero operator/DB action — the exact D+ gaps closed and the exact preconditions Wave 4 needs (`billing_mode`, `products`, a real `stripe_connected_account_id`, `charges_enabled`). **Scope boundary:** Wave 3 makes config self-serve; it does NOT create `Subscription`/`SubscriptionItem` on the connected account — that's Wave 4.
