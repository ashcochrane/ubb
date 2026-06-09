# Wave 3 — Journey-2 Self-Serve Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a tenant configure its own billing with zero operator/DB action — set billing mode + markup, and connect its OWN Stripe account via Standard OAuth — the prerequisite for Wave 4's outbound subscription orchestration.

**Architecture:** A thin tenant-config API over the already-validating `Tenant.clean()`; SDK wrappers for the existing markup endpoints; and a Standard-OAuth "Connect to Stripe" flow (the tenant connects their OWN account → UBB stores the `acct_` id and acts via the existing `stripe_account=` pattern — zero charge-path change). USD-only.

**Tech Stack:** Django 6, django-ninja, Stripe (OAuth + `stripe_account=`, mocked in tests), pytest-django, the `ubb` SDK.

**Design refs:** `docs/plans/2026-06-09-wave3-j2-selfserve-design.md` + `...wave3-stripe-connect-research.md`. **Decisions:** Standard OAuth (not Express); `products` tenant-settable; signup deferred; SDK dataclass.

---

## ⚠️ Caveats / facts (verified)
- `Tenant.clean()` (tenants/models.py:48-61) enforces: metering required, valid products, `billing_mode∈{prepaid,postpaid}` requires `billing`. `save()` calls `clean()` + cache-busts. So the config handler just assigns + `save()` + translates `ValidationError` → 422.
- Markup endpoints exist: `GET/PUT /api/v1/metering/pricing/markup` (tenant default, `TenantMarkupIn`/`TenantMarkupOut`, metering_endpoints.py:163-216). `1_000_000 micros == 1%`. (Check whether a per-customer markup endpoint exists; if not, scope the SDK to tenant-default only + note it.)
- `WEBHOOK_HANDLERS` registry (api/v1/webhooks.py:201) + `event.account` routing already handle connected-account events; the Stripe webhook is mounted at `/api/v1/webhooks/stripe` (config/urls.py:28).
- Routers: `tenant_api` at `/api/v1/tenant/` (urls.py:19), `platform_api` at `/api/v1/platform/`; the catch-all `api` at `/api/v1/` (urls.py:29) — any NEW router must mount BEFORE it.
- `stripe.api_key = settings.STRIPE_SECRET_KEY` (stripe_api.py:16). Add `STRIPE_CONNECT_CLIENT_ID`.
- tenants migration head = `0010_tenant_require_cost_card_coverage` → new `0011`.

## Conventions
- Platform from `ubb-platform/`, `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <venv python>`. Baseline **764 platform green**. SDK from `ubb-sdk/` (unset DJANGO_SETTINGS_MODULE), **166 green**. Commit per task; `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No PR.

---

### Task 1: SDK markup (server already exists)

**Files:** Modify `ubb-sdk/ubb/types.py`, `ubb-sdk/ubb/metering.py`, `ubb-sdk/ubb/client.py`, `ubb-sdk/ubb/__init__.py`; Test `ubb-sdk/tests/test_metering_client.py`.

- [ ] **Step 1 — Confirm the server surface:** `git grep -n "pricing/markup\|customers/.*markup" ../ubb-platform/api/v1/metering_endpoints.py` — confirm `GET/PUT /pricing/markup` (tenant default). If a per-customer markup endpoint (`/pricing/customers/{id}/markup`) exists, wrap it too; if NOT, scope this task to tenant-default only and note it in the report.
- [ ] **Step 2 — Failing tests** (`ubb-sdk/tests/test_metering_client.py`, mock httpx): `set_markup(markup_percentage_micros=20_000_000, fixed_uplift_micros=0)` PUTs `/api/v1/metering/pricing/markup` with that body; `get_markup()` GETs it and returns a `TenantMarkup` with `markup_percentage_micros == 20_000_000`.
- [ ] **Step 3 — Implement.** `ubb-sdk/ubb/types.py`:
```python
@dataclass(frozen=True)
class TenantMarkup:
    markup_percentage_micros: int | None = None
    fixed_uplift_micros: int | None = None
```
`ubb-sdk/ubb/metering.py` (`MeteringClient`), tolerant construction (filter to `__dataclass_fields__`, as elsewhere):
```python
    def get_markup(self) -> TenantMarkup:
        r = self._request("get", "/api/v1/metering/pricing/markup")
        d = r.json()
        return TenantMarkup(**{k: v for k, v in d.items() if k in TenantMarkup.__dataclass_fields__})

    def set_markup(self, *, markup_percentage_micros=0, fixed_uplift_micros=0) -> TenantMarkup:
        r = self._request("put", "/api/v1/metering/pricing/markup", json={
            "markup_percentage_micros": markup_percentage_micros,
            "fixed_uplift_micros": fixed_uplift_micros})
        d = r.json()
        return TenantMarkup(**{k: v for k, v in d.items() if k in TenantMarkup.__dataclass_fields__})
```
(Import `TenantMarkup` in metering.py's types import. If per-customer endpoints exist, add `get_customer_markup(customer_id)`/`set_customer_markup(customer_id, *, ...)` to the right paths.) Add `UBBClient` delegates (`client.py`, via `self._require_metering()`) + export `TenantMarkup` from `__init__.py`.
- [ ] **Step 4 — Verify (from ubb-sdk/):** `<venv> -m pytest -q` → green. **Commit (repo root):** `feat(sdk): markup get/set (TenantMarkup dataclass)`.

---

### Task 2: Tenant self-config API

**Files:** Modify the tenant-self router (`api/v1/tenant_endpoints.py` if that's what `tenant_api` is — READ it; else `api/v1/platform_endpoints.py`), `api/v1/schemas.py`; SDK `ubb-sdk/ubb/client.py`; Tests.

- [ ] **Step 1 — Find the router.** READ what `tenant_api` is (`grep -rn "tenant_api = " api/v1/`). It should be `ApiKeyAuth` and tenant-self. Add `GET/PATCH /config` there → `/api/v1/tenant/config`. (If `tenant_api` isn't a clean ApiKeyAuth self-router, use `platform_api` → `/api/v1/platform/tenant/config`. Report which.)
- [ ] **Step 2 — Failing tests** (platform, mirror the router's auth/client setup): GET `/api/v1/tenant/config` → 200 with `billing_mode`, `products`, `require_cost_card_coverage`, `stripe_connected_account_id`, `is_active`; PATCH `{"billing_mode": "postpaid", "products": ["metering","billing"]}` → 200 and the tenant is updated; PATCH `{"require_cost_card_coverage": true}` for a tenant with NO active cost cards → **422** with code `no_cost_cards`; PATCH `{"billing_mode": "prepaid"}` for a tenant whose products lack `billing` → **422** (the `clean()` invariant).
- [ ] **Step 3 — Schemas** (`api/v1/schemas.py`):
```python
class TenantConfigOut(Schema):
    name: str
    billing_mode: str
    products: list[str]
    require_cost_card_coverage: bool
    default_currency: str
    stripe_connected_account_id: str
    is_active: bool

class TenantConfigIn(Schema):
    billing_mode: Optional[str] = None
    products: Optional[list[str]] = None
    require_cost_card_coverage: Optional[bool] = None
```
- [ ] **Step 4 — Endpoints:**
```python
@tenant_api.get("/config", response=TenantConfigOut)
def get_tenant_config(request):
    t = request.auth.tenant
    return {"name": t.name, "billing_mode": t.billing_mode, "products": t.products,
            "require_cost_card_coverage": t.require_cost_card_coverage,
            "default_currency": t.default_currency,
            "stripe_connected_account_id": t.stripe_connected_account_id, "is_active": t.is_active}

@tenant_api.patch("/config", response={200: TenantConfigOut, 422: dict})
def update_tenant_config(request, payload: TenantConfigIn):
    from django.core.exceptions import ValidationError
    from apps.metering.pricing.models import RateCard
    t = request.auth.tenant
    if payload.require_cost_card_coverage is True and not t.require_cost_card_coverage:
        if not RateCard.objects.filter(tenant=t, card_type="cost", valid_to__isnull=True).exists():
            return 422, {"error": "require_cost_card_coverage cannot be enabled with zero active cost rate cards",
                         "code": "no_cost_cards"}
    if payload.billing_mode is not None:
        t.billing_mode = payload.billing_mode
    if payload.products is not None:
        t.products = payload.products
    if payload.require_cost_card_coverage is not None:
        t.require_cost_card_coverage = payload.require_cost_card_coverage
    try:
        t.save()
    except ValidationError as e:
        return 422, {"error": "; ".join(f"{k}: {' '.join(v)}" for k, v in e.message_dict.items()),
                     "code": "invalid_config"}
    return 200, get_tenant_config(request)
```
(Adapt `get_tenant_config(request)` re-call to return the dict; verify the active-cost-card filter — `valid_to__isnull=True` = active. RateCard has no `is_active` field; "active" = `valid_to IS NULL`.)
- [ ] **Step 5 — SDK** (`UBBClient`): `get_tenant_config()` → GET `/api/v1/tenant/config`; `update_tenant_config(*, billing_mode=None, products=None, require_cost_card_coverage=None)` → PATCH dropping None keys. SDK tests.
- [ ] **Step 6 — Verify:** `$DJ -m pytest api/v1 apps/platform -q`; SDK green. **Commit:** `feat(platform): tenant self-config API (billing_mode/products/coverage) + SDK`.

---

### Task 3: Stripe Connect — model, migration, OAuth service

**Files:** Modify `apps/platform/tenants/models.py`; Create `apps/billing/connectors/stripe/connect.py`; Modify `config/settings.py`; migration `tenants/0011_*`; Test `apps/billing/connectors/stripe/tests/test_connect.py`.

- [ ] **Step 1 — Settings:** add `STRIPE_CONNECT_CLIENT_ID = os.environ.get("STRIPE_CONNECT_CLIENT_ID", "")` to `config/settings.py` (beside `STRIPE_SECRET_KEY`).
- [ ] **Step 2 — Models** (`apps/platform/tenants/models.py`): add `charges_enabled = models.BooleanField(default=False)` to `Tenant`; add:
```python
class ConnectOAuthState(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="connect_oauth_states")
    state = models.CharField(max_length=128, unique=True, db_index=True)
    return_url = models.CharField(max_length=2000, blank=True, default="")
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_connect_oauth_state"
```
`$DJ manage.py makemigrations tenants` (`0011`); `makemigrations --check`; `migrate`.
- [ ] **Step 3 — Failing test** `apps/billing/connectors/stripe/tests/test_connect.py`:
```python
import pytest
from django.utils import timezone
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant, ConnectOAuthState
from apps.billing.connectors.stripe import connect


@pytest.mark.django_db
def test_build_authorize_url_creates_state(settings):
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"
    t = Tenant.objects.create(name="T", products=["metering"])
    url = connect.build_authorize_url(t, return_url="https://x/done")
    assert url.startswith("https://connect.stripe.com/oauth/authorize")
    assert "client_id=ca_test" in url and "scope=read_write" in url
    st = ConnectOAuthState.objects.get(tenant=t)
    assert st.state in url and not st.used and st.expires_at > timezone.now()


@pytest.mark.django_db
def test_complete_oauth_persists_account(settings):
    t = Tenant.objects.create(name="T", products=["metering"])
    st = connect.build_authorize_url(t, return_url="https://x/done")  # creates state
    state = ConnectOAuthState.objects.get(tenant=t).state
    with patch("apps.billing.connectors.stripe.connect.stripe.OAuth.token",
               return_value=MagicMock(stripe_user_id="acct_123")) as mock_tok, \
         patch("apps.billing.connectors.stripe.connect.stripe.Account.retrieve",
               return_value=MagicMock(charges_enabled=True)):
        tenant = connect.complete_oauth(code="ac_1", state=state)
    tenant.refresh_from_db()
    assert tenant.stripe_connected_account_id == "acct_123"
    assert tenant.charges_enabled is True
    assert ConnectOAuthState.objects.get(state=state).used is True
    # replay/used state -> error
    with pytest.raises(connect.ConnectError):
        connect.complete_oauth(code="ac_1", state=state)
```
- [ ] **Step 4 — Service** `apps/billing/connectors/stripe/connect.py`:
```python
import secrets
from datetime import timedelta
from urllib.parse import urlencode
import stripe
from django.conf import settings
from django.utils import timezone

STATE_TTL = timedelta(minutes=15)


class ConnectError(Exception):
    pass


def build_authorize_url(tenant, *, return_url=""):
    from apps.platform.tenants.models import ConnectOAuthState
    if not settings.STRIPE_CONNECT_CLIENT_ID:
        raise ConnectError("Stripe Connect is not configured (STRIPE_CONNECT_CLIENT_ID unset)")
    state = secrets.token_urlsafe(32)
    ConnectOAuthState.objects.create(
        tenant=tenant, state=state, return_url=return_url,
        expires_at=timezone.now() + STATE_TTL)
    q = urlencode({"response_type": "code", "client_id": settings.STRIPE_CONNECT_CLIENT_ID,
                   "scope": "read_write", "state": state})
    return f"https://connect.stripe.com/oauth/authorize?{q}"


def complete_oauth(*, code, state):
    from apps.platform.tenants.models import ConnectOAuthState
    from django.db import transaction
    with transaction.atomic():
        st = (ConnectOAuthState.objects.select_for_update()
              .filter(state=state, used=False, expires_at__gt=timezone.now()).first())
        if st is None:
            raise ConnectError("invalid or expired state")
        resp = stripe.OAuth.token(grant_type="authorization_code", code=code)
        acct_id = resp.stripe_user_id
        tenant = st.tenant
        tenant.stripe_connected_account_id = acct_id
        try:
            acct = stripe.Account.retrieve(acct_id)
            tenant.charges_enabled = bool(getattr(acct, "charges_enabled", False))
        except Exception:
            tenant.charges_enabled = False
        tenant.save(update_fields=["stripe_connected_account_id", "charges_enabled", "updated_at"])
        st.used = True
        st.save(update_fields=["used", "updated_at"])
    return tenant
```
(VERIFY `stripe.OAuth.token` + `stripe.Account.retrieve` are the right calls for the installed stripe lib version; `stripe.api_key` is already set at module import via stripe_api.py — import that or set it. `Tenant.save(update_fields=...)` skips `clean()`/widget regen — fine here since we touch only these fields; but `save()`'s product-default + clean run only on full save. Using update_fields avoids re-validation, which is correct for these non-product fields.)
- [ ] **Step 5 — Verify:** `$DJ manage.py check`; makemigrations --check; `$DJ -m pytest apps/billing/connectors/stripe/tests/test_connect.py apps/platform -q` → green. **Commit:** `feat(connect): Standard-OAuth Stripe Connect service + ConnectOAuthState + charges_enabled`.

---

### Task 4: Stripe Connect — endpoints, webhooks, charge gating

**Files:** Create `api/v1/connect_endpoints.py`; Modify `config/urls.py`, `api/v1/webhooks.py` (WEBHOOK_HANDLERS), the charge choke points; SDK `ubb-sdk/ubb/client.py`; Tests.

- [ ] **Step 1 — Failing tests** (platform): `POST /api/v1/connect/start` (Bearer) `{"return_url":"https://x/done"}` → 200 `{authorize_url}` starting `https://connect.stripe.com/oauth/authorize`; `GET /api/v1/connect/status` (Bearer) → 200 `{account_id, charges_enabled, onboarded}`; `GET /api/v1/connect/callback?code=ac&state=<valid>` (NO auth, OAuth mocked) → 302 redirect to the state's return_url and the tenant's `stripe_connected_account_id` is persisted; callback with an unknown `state` → a 4xx/redirect-with-error, NEVER a 500 or a mutation. Plus a webhook test: an `account.application.deauthorized` event for the tenant's `acct_` clears `stripe_connected_account_id` + `charges_enabled`.
- [ ] **Step 2 — Router** `api/v1/connect_endpoints.py`: `connect_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_connect_v1")`.
  - `POST /start` (`{return_url}`) → `{"authorize_url": connect.build_authorize_url(request.auth.tenant, return_url=payload.return_url)}` (catch `ConnectError` → 400).
  - `GET /status` → `{"account_id": t.stripe_connected_account_id, "charges_enabled": t.charges_enabled, "onboarded": bool(t.stripe_connected_account_id and t.charges_enabled)}`; if `stripe_connected_account_id` and not `charges_enabled`, do a live `stripe.Account.retrieve` fallback to refresh.
  - **Callback** — needs NO auth + must return a redirect. Make it a SEPARATE plain Django view (not on the ApiKeyAuth `connect_api`), e.g. `def connect_callback(request)` in `connect_endpoints.py` returning `django.http.HttpResponseRedirect`: read `code`/`state` from `request.GET`; `try: connect.complete_oauth(code=code, state=state); ok=True except ConnectError: ok=False`; look up the state's `return_url` (even if used/expired, to redirect somewhere sane — but only COMPLETE if valid); redirect to `return_url + ("?connected=true" if ok else "?connected=false")`. If no return_url, return a plain 200/400 JSON.
- [ ] **Step 3 — Mount** in `config/urls.py` BEFORE `path("api/v1/", api.urls)`:
```python
    path("api/v1/connect/callback", connect_callback),   # plain view, no auth
    path("api/v1/connect/", connect_api.urls),
```
(import `connect_api`, `connect_callback`.)
- [ ] **Step 4 — Webhooks** (`api/v1/webhooks.py`): add handlers + register in `WEBHOOK_HANDLERS`:
```python
def handle_account_updated(event):
    from apps.platform.tenants.models import Tenant
    acct = event.data.object
    t = Tenant.objects.filter(stripe_connected_account_id=acct.id).first()
    if t:
        t.charges_enabled = bool(getattr(acct, "charges_enabled", False))
        t.save(update_fields=["charges_enabled", "updated_at"])

def handle_account_deauthorized(event):
    from apps.platform.tenants.models import Tenant
    t = Tenant.objects.filter(stripe_connected_account_id=event.account).first()
    if t:
        t.stripe_connected_account_id = ""
        t.charges_enabled = False
        t.save(update_fields=["stripe_connected_account_id", "charges_enabled", "updated_at"])
```
Register: `"account.updated": handle_account_updated, "account.application.deauthorized": handle_account_deauthorized`. (For deauthorized, the connected account is `event.account`; for account.updated, `event.data.object.id`. Verify the event shapes.)
- [ ] **Step 5 — Charge gating:** at the charge choke points (`charge_saved_payment_method` / `create_checkout_session` / the postpaid finalize), after resolving the connected account, short-circuit with a clear skip/error when `tenant.charges_enabled` is False (mirror the existing "no connected account → skip" pattern). Find them: `git grep -n "stripe_connected_account_id\|get_tenant_stripe_account\|stripe_account=" apps/billing`. Add the `charges_enabled` guard alongside the existing falsy-account guard.
- [ ] **Step 6 — SDK** (`UBBClient`): `start_connect_onboarding(return_url)` → POST `/api/v1/connect/start`, return the dict; `get_connect_status()` → GET `/api/v1/connect/status`. SDK tests.
- [ ] **Step 7 — Verify:** `$DJ manage.py check`; `$DJ -m pytest api/v1 apps/billing apps/platform -q` → green; SDK green. **Commit:** `feat(connect): /connect OAuth start/callback/status + account webhooks + charge gating (+SDK)`.

---

### Task 5: Capstone — self-serve config + Connect onboarding via the SDK

**Files:** Create `api/v1/tests/test_wave3_selfserve_capstone.py` (live_server + SDK).

- [ ] **Step 1 — Write** (`live_server` + the `_no_outbox_dispatch` patch pattern from the J1 capstones; `@pytest.mark.django_db(transaction=True)`; `settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"`). Via the SDK only, with `stripe.OAuth.token`/`stripe.Account.retrieve` patched:
```python
c = UBBClient(api_key=raw_key, base_url=live_server.url)
c.set_markup(markup_percentage_micros=20_000_000)
assert c.get_markup().markup_percentage_micros == 20_000_000
c.update_tenant_config(billing_mode="prepaid", products=["metering", "billing"])
assert c.get_tenant_config()["billing_mode"] == "prepaid"
res = c.start_connect_onboarding(return_url="https://tenant.example/done")
assert res["authorize_url"].startswith("https://connect.stripe.com/oauth/authorize")
# extract the state from the URL; drive the (no-auth) callback over HTTP with OAuth mocked:
#   httpx.get(live_server.url + "/api/v1/connect/callback?code=ac&state=<state>") -> 302
# then assert status:
assert c.get_connect_status()["onboarded"] is True
```
(VERIFY the SDK method names/returns; extract `state` from the `authorize_url` query; patch `stripe.OAuth.token`/`stripe.Account.retrieve` at `apps.billing.connectors.stripe.connect.stripe.*` — but note the live-server thread runs the real complete_oauth, so the patch must apply process-wide; if patching across the live_server thread is awkward, drive `complete_oauth` via the callback with the stripe calls patched in the same process — confirm it works, else assert up to `authorize_url` + drive the callback in a non-live unit test and assert `onboarded` there.)
- [ ] **Step 2 — Run** 2-3x for stability; then FULL platform suite `$DJ -m pytest -q | tail -2`. **Commit:** `test(wave3): self-serve config + Connect onboarding capstone via SDK`.

---

### Task 6: Final verification
- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Fresh-DB:** drop/recreate `ubb`; `$DJ manage.py migrate` applies `tenants/0011` cleanly; `$DJ -m pytest -q` whole platform suite green (report count); `cd ../ubb-sdk && <venv> -m pytest -q` green.
- [ ] Capstone passes; clean tree.

---

## Self-Review
**Spec coverage:** SDK markup (T1) ✓; tenant-config API self-config + cost-card safety gate + SDK (T2) ✓; Connect OAuth service + ConnectOAuthState + charges_enabled (T3) ✓; /connect endpoints + callback (no-auth, state-identified) + account webhooks + charge gating + SDK (T4) ✓; capstone (T5) ✓; Standard OAuth not Express ✓; products tenant-settable ✓; no signup ✓; dataclass ✓.
**Placeholder scan:** T1/T2 give full code; T3/T4 give the service + endpoint/webhook code with "verify stripe lib call shapes" notes (real verification, not placeholders). No TBD.
**Type consistency:** `TenantMarkup` (T1) used by capstone (T5); `TenantConfigIn/Out` (T2); `ConnectOAuthState` + `build_authorize_url`/`complete_oauth`/`ConnectError` (T3) used by endpoints (T4) + capstone (T5); `charges_enabled` set in T3 service + T4 webhooks, read in T4 status/gating + T5.
**Migration:** one (`tenants/0011`: `charges_enabled` + `ConnectOAuthState`); DB-validated T3 + fresh-DB T6.
**Scope boundary:** config + onboarding only — NO Subscription/Price creation (that's Wave 4).
