# Track-Mode Tenant Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a Clerk-authenticated user on a usable dashboard with a provisioned Tenant, TenantUser, and API key, after a three-step onboarding wizard (name → create card → SDK snippet). Track mode only; revenue/billing modes explicitly out of scope.

**Architecture:** Backend service function (`provision_tenant_for_clerk_user`) is the single seam — called from `POST /api/v1/platform/tenant` now, callable from a Clerk webhook later. UI reads `GET /api/v1/platform/me` via TanStack Query on every authed page load; a `beforeLoad` guard on the `_app` layout redirects to `/onboarding` when the user has no tenant or onboarding is incomplete. Completion tracked via `Tenant.onboarding_completed_at` timestamp.

**Tech Stack:** Django 6.0 + django-ninja + Postgres + Celery (outbox); React + TanStack Router/Query + Zustand + Vitest (UI); pytest (backend tests); Clerk (auth).

**Commits:** Per user preference, this plan does **not** include per-task commit steps. The human operator commits at natural checkpoints (end of backend, end of frontend). Each task is self-contained and leaves the tree in a green state.

**Spec:** `docs/plans/2026-04-21-track-mode-onboarding-design.md`.

---

## File Structure

### Backend — `ubb-platform/`

| Path | Purpose |
|---|---|
| `apps/platform/tenants/migrations/0012_tenant_onboarding_completed_at.py` | Add `onboarding_completed_at` field |
| `core/clerk_api.py` | Thin client for Clerk Backend API (`get_clerk_user`) |
| `core/tests/test_clerk_api.py` | Tests for the client |
| `apps/platform/tenants/services.py` | `provision_tenant_for_clerk_user` |
| `apps/platform/tenants/tests/test_provisioning.py` | Tests for the service |
| `apps/platform/events/schemas.py` | Add `TenantProvisionedEvent` dataclass |
| `api/v1/platform_endpoints.py` | Add `GET /me`, `POST /tenant`, `PATCH /tenant` |
| `api/v1/tests/test_platform_onboarding.py` | Endpoint tests |
| `apps/platform/tenants/management/commands/seed_dev_data.py` | Add TenantUser + set `onboarding_completed_at` |
| `config/settings.py` | `CLERK_SECRET_KEY` setting |
| `.env.example` | Add `CLERK_SECRET_KEY=` |

### Frontend — `ubb-ui/`

| Path | Action |
|---|---|
| `src/features/auth/api/types.ts` | Create — `Me` / `MeTenant` / `MeTenantUser` |
| `src/features/auth/api/mock.ts` | Create — mock `getMe` |
| `src/features/auth/api/api.ts` | Create — real `getMe` |
| `src/features/auth/api/provider.ts` | Create — `selectProvider` |
| `src/features/auth/api/queries.ts` | Create — `meQueryOptions` + `useMe` |
| `src/features/onboarding/api/types.ts` | Rewrite — trim to track-mode types only |
| `src/features/onboarding/api/mock.ts` | Rewrite — track-mode only |
| `src/features/onboarding/api/api.ts` | Rewrite — `createTenant`, `completeOnboarding` |
| `src/features/onboarding/api/provider.ts` | Unchanged |
| `src/features/onboarding/api/queries.ts` | Rewrite — mutations |
| `src/features/onboarding/lib/schema.ts` | Rewrite — track-mode only |
| `src/features/onboarding/lib/constants.ts` | Delete (contains unused `MOCK_TENANT_ID`) |
| `src/features/onboarding/components/onboarding-wizard.tsx` | Rewrite |
| `src/features/onboarding/components/name-workspace-step.tsx` | Create |
| `src/features/onboarding/components/create-card-step.tsx` | Create |
| `src/features/onboarding/components/sdk-step.tsx` | Create |
| `src/features/onboarding/components/{stripe-key-step, customer-mapping-step, margin-config-step, review-step, mode-selector, match-results-table, permissions-table, activation-success, onboarding-layout}.tsx` | Delete |
| `src/features/pricing-cards/components/new-card-wizard.tsx` | Modify — accept `onSuccess?` and `onSkip?` props |
| `src/app/routes/_app/route.tsx` | Modify — `beforeLoad` guard |
| `src/app/routes/onboarding.tsx` | Modify — inverse guard |
| `src/features/dashboard/components/getting-started.tsx` | Create |
| `src/features/dashboard/components/dashboard-page.tsx` (or equivalent) | Modify — mount `<GettingStarted />` |
| `src/stores/auth-store.ts` | Modify — remove tenant-identity fields |
| `src/api/schemas/platform.json` + `src/api/generated/platform.ts` | Regenerate after backend changes |

**Backend tests go first (TDD); then backend implementation; then regenerate UI schemas; then UI tests and components.**

---

## Task 1: Add `CLERK_SECRET_KEY` setting

**Files:**
- Modify: `ubb-platform/config/settings.py`
- Modify: `ubb-platform/.env.example`
- Modify: `ubb-platform/.env` (local only, not committed)

- [ ] **Step 1: Add setting to `config/settings.py`**

Near the existing `CLERK_ISSUER_URL` line, add:

```python
CLERK_SECRET_KEY = env("CLERK_SECRET_KEY", default="")
```

- [ ] **Step 2: Add to `.env.example`**

Append:

```
# Clerk Backend API secret key (sk_test_... or sk_live_...).
# Required for tenant provisioning (fetches canonical email from Clerk).
CLERK_SECRET_KEY=
```

- [ ] **Step 3: Add real value to local `.env`**

Append `CLERK_SECRET_KEY=sk_test_<your_real_key>` to `ubb-platform/.env`. Do not commit.

- [ ] **Step 4: Confirm Django starts**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -c "from django.conf import settings; print(bool(settings.CLERK_SECRET_KEY))"
```

Expected: prints `True` (or `False` if you haven't set it locally — still fine, it's a nullable default).

---

## Task 2: Clerk Backend API client — `core/clerk_api.py`

**Files:**
- Create: `ubb-platform/core/clerk_api.py`
- Create: `ubb-platform/core/tests/test_clerk_api.py`

- [ ] **Step 1: Write failing tests**

Create `ubb-platform/core/tests/test_clerk_api.py`:

```python
from unittest.mock import patch, Mock

import pytest
import requests

from core.clerk_api import ClerkAPIError, get_clerk_user


@pytest.fixture
def mock_settings(settings):
    settings.CLERK_SECRET_KEY = "sk_test_fake"
    return settings


def test_returns_user_data_on_200(mock_settings):
    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {
        "id": "user_abc",
        "email_addresses": [{"email_address": "ash@example.com", "id": "em_1"}],
        "primary_email_address_id": "em_1",
    }
    fake_response.raise_for_status = Mock()
    with patch("core.clerk_api.requests.get", return_value=fake_response) as mock_get:
        user = get_clerk_user("user_abc")
    assert user["email"] == "ash@example.com"
    assert user["clerk_user_id"] == "user_abc"
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.clerk.com/v1/users/user_abc"
    assert kwargs["headers"]["Authorization"] == "Bearer sk_test_fake"


def test_raises_when_secret_missing(settings):
    settings.CLERK_SECRET_KEY = ""
    with pytest.raises(ClerkAPIError, match="CLERK_SECRET_KEY not configured"):
        get_clerk_user("user_abc")


def test_raises_on_404(mock_settings):
    fake_response = Mock(status_code=404)
    fake_response.raise_for_status.side_effect = requests.HTTPError("404")
    with patch("core.clerk_api.requests.get", return_value=fake_response):
        with pytest.raises(ClerkAPIError):
            get_clerk_user("user_missing")


def test_raises_on_timeout(mock_settings):
    with patch("core.clerk_api.requests.get", side_effect=requests.Timeout()):
        with pytest.raises(ClerkAPIError):
            get_clerk_user("user_abc")


def test_raises_when_no_primary_email(mock_settings):
    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {
        "id": "user_abc",
        "email_addresses": [],
        "primary_email_address_id": None,
    }
    fake_response.raise_for_status = Mock()
    with patch("core.clerk_api.requests.get", return_value=fake_response):
        with pytest.raises(ClerkAPIError, match="no primary email"):
            get_clerk_user("user_abc")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_clerk_api.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'core.clerk_api'`.

- [ ] **Step 3: Implement the client**

Create `ubb-platform/core/clerk_api.py`:

```python
"""Thin client for Clerk Backend API.

Used during tenant provisioning to fetch the canonical email for a
Clerk user. Email is never accepted from client request bodies — this
is the security boundary.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

CLERK_API_BASE = "https://api.clerk.com/v1"
TIMEOUT_SECONDS = 5


class ClerkAPIError(Exception):
    """Raised on any failure talking to the Clerk Backend API."""


def get_clerk_user(user_id: str) -> dict:
    """Fetch canonical user data from the Clerk Backend API.

    Returns: {"clerk_user_id": str, "email": str}
    Raises: ClerkAPIError on missing secret, non-2xx, timeout, or no primary email.
    """
    if not settings.CLERK_SECRET_KEY:
        raise ClerkAPIError("CLERK_SECRET_KEY not configured")

    url = f"{CLERK_API_BASE}/users/{user_id}"
    headers = {"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"}

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except (requests.RequestException, requests.Timeout) as exc:
        logger.warning("Clerk API request failed: %s", exc)
        raise ClerkAPIError(f"Clerk API request failed: {exc}") from exc

    data = response.json()
    primary_id = data.get("primary_email_address_id")
    email = None
    for addr in data.get("email_addresses", []):
        if addr.get("id") == primary_id:
            email = addr.get("email_address")
            break

    if not email:
        raise ClerkAPIError(f"Clerk user {user_id} has no primary email")

    return {"clerk_user_id": user_id, "email": email}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_clerk_api.py -v
```

Expected: PASS, 5 tests.

---

## Task 3: Migration — `Tenant.onboarding_completed_at`

**Files:**
- Modify: `ubb-platform/apps/platform/tenants/models.py`
- Create: `ubb-platform/apps/platform/tenants/migrations/0012_tenant_onboarding_completed_at.py`

- [ ] **Step 1: Add field to `Tenant` model**

In `apps/platform/tenants/models.py`, after the `default_margin_pct` field:

```python
    onboarding_completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
```

- [ ] **Step 2: Generate the migration**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations tenants
```

Expected: creates `0012_tenant_onboarding_completed_at.py` with `AddField`.

- [ ] **Step 3: Apply the migration**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate tenants
```

Expected: `Applying tenants.0012_tenant_onboarding_completed_at... OK`.

- [ ] **Step 4: Add a model test**

Add to `apps/platform/tenants/tests/test_models.py`:

```python
def test_tenant_onboarding_completed_at_defaults_to_none(db):
    from apps.platform.tenants.models import Tenant
    tenant = Tenant.objects.create(name="t", products=["metering"])
    assert tenant.onboarding_completed_at is None
```

- [ ] **Step 5: Run the test**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_models.py::test_tenant_onboarding_completed_at_defaults_to_none -v
```

Expected: PASS.

---

## Task 4: `TenantProvisioned` outbox event schema

**Files:**
- Modify: `ubb-platform/apps/platform/events/schemas.py`

- [ ] **Step 1: Find the right pattern**

Read `apps/platform/events/schemas.py` to see how existing outbox event dataclasses are structured (`EVENT_TYPE` class attribute, `tenant_id` field, etc.). Match that pattern.

- [ ] **Step 2: Add the new event schema**

Append to `apps/platform/events/schemas.py`:

```python
@dataclass
class TenantProvisionedEvent:
    """Emitted when a new tenant is created via onboarding.

    No handlers registered today. Billing/subscriptions apps may subscribe
    in future to bootstrap product-specific state.
    """
    EVENT_TYPE = "TenantProvisioned"

    tenant_id: str
    clerk_user_id: str
    mode: str  # "track" for this phase
```

(Adjust the `from dataclasses import dataclass` import if needed; use the same imports already in the file.)

- [ ] **Step 3: Quick sanity import**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -c "from apps.platform.events.schemas import TenantProvisionedEvent; e = TenantProvisionedEvent(tenant_id='t', clerk_user_id='u', mode='track'); print(e.EVENT_TYPE)"
```

Expected: `TenantProvisioned`.

---

## Task 5: Provisioning service — `apps/platform/tenants/services.py`

**Files:**
- Create: `ubb-platform/apps/platform/tenants/services.py`
- Create: `ubb-platform/apps/platform/tenants/tests/test_provisioning.py`

- [ ] **Step 1: Write failing tests**

Create `ubb-platform/apps/platform/tenants/tests/test_provisioning.py`:

```python
from unittest.mock import patch

import pytest
from django.db import IntegrityError

from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant, TenantApiKey, TenantUser
from apps.platform.tenants.services import provision_tenant_for_clerk_user


CLERK_USER = "user_test_abc"
EMAIL = "ash@example.com"


@pytest.fixture
def mock_clerk(monkeypatch):
    def fake(user_id):
        return {"clerk_user_id": user_id, "email": EMAIL}
    monkeypatch.setattr(
        "apps.platform.tenants.services.get_clerk_user", fake
    )


def test_provisions_tenant_user_and_key(db, mock_clerk):
    tenant, tu, raw_key = provision_tenant_for_clerk_user(
        clerk_user_id=CLERK_USER, tenant_name="Acme"
    )
    assert Tenant.objects.count() == 1
    assert tenant.name == "Acme"
    assert tenant.products == ["metering"]
    assert tenant.onboarding_completed_at is None

    assert TenantUser.objects.count() == 1
    assert tu.clerk_user_id == CLERK_USER
    assert tu.email == EMAIL
    assert tu.role == "owner"
    assert tu.tenant_id == tenant.id

    assert TenantApiKey.objects.filter(tenant=tenant).count() == 1
    assert raw_key is not None
    assert raw_key.startswith(("ubb_live_", "ubb_test_"))


def test_is_idempotent_per_clerk_user(db, mock_clerk):
    tenant1, tu1, raw_key1 = provision_tenant_for_clerk_user(
        clerk_user_id=CLERK_USER, tenant_name="Acme"
    )
    tenant2, tu2, raw_key2 = provision_tenant_for_clerk_user(
        clerk_user_id=CLERK_USER, tenant_name="Acme Again"
    )
    assert tenant2.id == tenant1.id
    assert tu2.id == tu1.id
    assert Tenant.objects.count() == 1
    assert TenantApiKey.objects.filter(tenant=tenant1).count() == 1
    assert raw_key2 is None  # Keys are returned once, at first creation


def test_rolls_back_on_clerk_api_failure(db, monkeypatch):
    from core.clerk_api import ClerkAPIError
    def failing(user_id):
        raise ClerkAPIError("boom")
    monkeypatch.setattr(
        "apps.platform.tenants.services.get_clerk_user", failing
    )
    with pytest.raises(ClerkAPIError):
        provision_tenant_for_clerk_user(clerk_user_id=CLERK_USER, tenant_name="Acme")
    assert Tenant.objects.count() == 0
    assert TenantUser.objects.count() == 0
    assert TenantApiKey.objects.count() == 0


def test_emits_tenant_provisioned_outbox_event(db, mock_clerk):
    tenant, _, _ = provision_tenant_for_clerk_user(
        clerk_user_id=CLERK_USER, tenant_name="Acme"
    )
    events = OutboxEvent.objects.filter(event_type="TenantProvisioned")
    assert events.count() == 1
    assert events.first().payload["tenant_id"] == str(tenant.id)
    assert events.first().payload["clerk_user_id"] == CLERK_USER
    assert events.first().payload["mode"] == "track"


def test_idempotent_replay_does_not_emit_new_event(db, mock_clerk):
    provision_tenant_for_clerk_user(clerk_user_id=CLERK_USER, tenant_name="Acme")
    provision_tenant_for_clerk_user(clerk_user_id=CLERK_USER, tenant_name="Acme")
    assert OutboxEvent.objects.filter(event_type="TenantProvisioned").count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_provisioning.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'apps.platform.tenants.services'`.

- [ ] **Step 3: Implement the service**

Create `ubb-platform/apps/platform/tenants/services.py`:

```python
"""Tenant provisioning service.

Single entry point for creating a new tenant + tenant user + API key
for a Clerk-authenticated user. Called today from POST /platform/tenant;
later, also from a Clerk webhook handler.
"""
from django.db import IntegrityError, transaction

from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import TenantProvisionedEvent
from apps.platform.tenants.models import Tenant, TenantApiKey, TenantUser
from core.clerk_api import get_clerk_user


def provision_tenant_for_clerk_user(
    clerk_user_id: str,
    tenant_name: str,
) -> tuple[Tenant, TenantUser, str | None]:
    """Create Tenant + TenantUser + TenantApiKey for a new Clerk user.

    Idempotent: if a TenantUser already exists for clerk_user_id,
    returns the existing tenant + tenant_user with raw_api_key=None.
    Keys are returned exactly once, at first creation.

    Raises ClerkAPIError if the email lookup fails.
    """
    existing = TenantUser.objects.select_related("tenant").filter(
        clerk_user_id=clerk_user_id
    ).first()
    if existing:
        return existing.tenant, existing, None

    clerk_user = get_clerk_user(clerk_user_id)

    try:
        with transaction.atomic():
            tenant = Tenant.objects.create(
                name=tenant_name,
                products=["metering"],
            )
            tenant_user = TenantUser.objects.create(
                tenant=tenant,
                clerk_user_id=clerk_user_id,
                email=clerk_user["email"],
                role="owner",
            )
            _, raw_key = TenantApiKey.create_key(tenant, label="default")
            write_event(TenantProvisionedEvent(
                tenant_id=str(tenant.id),
                clerk_user_id=clerk_user_id,
                mode="track",
            ))
    except IntegrityError:
        # Concurrent provisioning raced us — return the winner.
        tenant_user = TenantUser.objects.select_related("tenant").get(
            clerk_user_id=clerk_user_id
        )
        return tenant_user.tenant, tenant_user, None

    return tenant, tenant_user, raw_key
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_provisioning.py -v
```

Expected: PASS, 5 tests.

---

## Task 6: `GET /api/v1/platform/me` endpoint

**Files:**
- Modify: `ubb-platform/api/v1/platform_endpoints.py`
- Modify: `ubb-platform/api/v1/schemas.py`
- Create: `ubb-platform/api/v1/tests/test_platform_onboarding.py`

- [ ] **Step 1: Write failing tests**

Create `ubb-platform/api/v1/tests/test_platform_onboarding.py`:

```python
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone

from apps.platform.tenants.models import Tenant, TenantUser


pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def clerk_jwt():
    """Bypass JWT verification — return fixed claims."""
    def _with(clerk_user_id="user_test_1"):
        return {
            "Authorization": f"Bearer fake.{clerk_user_id}.token",
        }
    return _with


@pytest.fixture(autouse=True)
def mock_clerk_verify(monkeypatch):
    def fake_verify(token):
        # Extract clerk_user_id from "fake.<id>.token"
        parts = token.split(".")
        if len(parts) == 3 and parts[0] == "fake":
            return {"sub": parts[1]}
        return None
    monkeypatch.setattr(
        "core.clerk_auth.verify_clerk_token", fake_verify
    )


def _tenant_with_user(clerk_user_id, name="Acme", completed=False):
    tenant = Tenant.objects.create(name=name, products=["metering"])
    if completed:
        tenant.onboarding_completed_at = timezone.now()
        tenant.save(update_fields=["onboarding_completed_at"])
    tu = TenantUser.objects.create(
        tenant=tenant, clerk_user_id=clerk_user_id, email="ash@example.com", role="owner"
    )
    return tenant, tu


class TestGetMe:
    def test_unauthed_returns_401(self, client):
        resp = client.get("/api/v1/platform/me")
        assert resp.status_code == 401

    def test_authed_without_tenant_user(self, client, clerk_jwt):
        resp = client.get("/api/v1/platform/me", **_headers(clerk_jwt("user_new")))
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenantUser"] is None
        assert body["tenant"] is None
        assert body["onboardingCompleted"] is False

    def test_authed_with_incomplete_onboarding(self, client, clerk_jwt):
        tenant, _ = _tenant_with_user("user_existing", completed=False)
        resp = client.get("/api/v1/platform/me", **_headers(clerk_jwt("user_existing")))
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenantUser"]["email"] == "ash@example.com"
        assert body["tenant"]["name"] == "Acme"
        assert body["tenant"]["pricingCardsCount"] == 0
        assert body["tenant"]["usageEventsCount"] == 0
        assert body["onboardingCompleted"] is False

    def test_authed_with_completed_onboarding(self, client, clerk_jwt):
        _tenant_with_user("user_done", completed=True)
        resp = client.get("/api/v1/platform/me", **_headers(clerk_jwt("user_done")))
        assert resp.status_code == 200
        assert resp.json()["onboardingCompleted"] is True


def _headers(h):
    return {"HTTP_" + k.upper().replace("-", "_"): v for k, v in h.items()}
```

- [ ] **Step 2: Add schemas to `api/v1/schemas.py`**

Append:

```python
class MeTenantResponse(CamelSchema):
    id: str
    name: str
    products: list[str]
    pricing_cards_count: int
    usage_events_count: int


class MeTenantUserResponse(CamelSchema):
    id: str
    email: str
    role: str


class MeResponse(CamelSchema):
    tenant_user: Optional[MeTenantUserResponse] = None
    tenant: Optional[MeTenantResponse] = None
    onboarding_completed: bool
```

(Use the same `Optional` / `CamelSchema` imports already in the file.)

- [ ] **Step 3: Implement the endpoint**

Add to `ubb-platform/api/v1/platform_endpoints.py` (after the existing endpoints, before the end of the file). `Card` and `UsageEvent` are already imported at the top of the file — do not re-import.

```python
@platform_api.get("/me", response=MeResponse, auth=ClerkJWTAuth())
def get_me(request):
    tu = getattr(request, "tenant_user", None)
    if tu is None:
        # Clerk JWT verified but no TenantUser — first-time user.
        return {
            "tenant_user": None,
            "tenant": None,
            "onboarding_completed": False,
        }

    tenant = tu.tenant
    cards_count = Card.objects.filter(tenant=tenant).count()
    events_count = UsageEvent.objects.filter(tenant=tenant).count()
    return {
        "tenant_user": {
            "id": str(tu.id),
            "email": tu.email,
            "role": tu.role,
        },
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "products": tenant.products,
            "pricing_cards_count": cards_count,
            "usage_events_count": events_count,
        },
        "onboarding_completed": tenant.onboarding_completed_at is not None,
    }
```

Import the new schemas at the top of the file:

```python
from api.v1.schemas import (
    # ... existing imports ...
    MeResponse, MeTenantResponse, MeTenantUserResponse,
)
```

- [ ] **Step 4: Update `ClerkJWTAuth` to allow no TenantUser**

Current behavior (at `core/clerk_auth.py:93-94`): `TenantUser.DoesNotExist → return None`. For the `/me` endpoint to return `tenant_user: None`, we must let verified JWTs through even without a TenantUser.

Modify `core/clerk_auth.py:83-98` — change `authenticate` to return a sentinel for "verified Clerk, no tenant user":

```python
    def authenticate(self, request, token: str):
        claims = verify_clerk_token(token)
        if claims is None:
            return None

        clerk_user_id = claims.get("sub")
        if not clerk_user_id:
            return None

        request.clerk_user_id = clerk_user_id

        try:
            tenant_user = TenantUser.objects.select_related("tenant").get(
                clerk_user_id=clerk_user_id
            )
            request.tenant = tenant_user.tenant
            request.tenant_user = tenant_user
            return tenant_user
        except TenantUser.DoesNotExist:
            # Return a sentinel so ninja treats the request as authed.
            # Endpoints that require tenant_user must check request.tenant_user.
            request.tenant = None
            request.tenant_user = None
            return clerk_user_id  # Truthy, not None
```

- [ ] **Step 5: Update existing tests expecting TenantUser.DoesNotExist → 401**

Search `ubb-platform/core/tests/test_clerk_auth.py` for tests asserting 401 when no TenantUser exists. Update them to assert the new behavior: the auth passes but `request.tenant_user is None`. If any endpoint test relied on TenantUser.DoesNotExist being a 401, add an explicit guard inside that endpoint:

```python
if request.tenant_user is None:
    raise HttpError(403, "Tenant user required for this operation")
```

Run the full auth tests to catch regressions:

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_clerk_auth.py -v
```

Fix any failures by adding explicit `tenant_user is None` guards in affected endpoints. Dashboard endpoints (dashboard stats, customer list, etc.) should return 403 if `tenant_user is None`.

- [ ] **Step 6: Run the `/me` tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_platform_onboarding.py -v -k TestGetMe
```

Expected: 4 tests PASS.

---

## Task 7: `POST /api/v1/platform/tenant` endpoint

**Files:**
- Modify: `ubb-platform/api/v1/platform_endpoints.py`
- Modify: `ubb-platform/api/v1/schemas.py`
- Modify: `ubb-platform/api/v1/tests/test_platform_onboarding.py`

- [ ] **Step 1: Write failing tests**

Append to `test_platform_onboarding.py`:

```python
class TestPostTenant:
    def test_creates_tenant_for_new_clerk_user(self, client, clerk_jwt, monkeypatch):
        monkeypatch.setattr(
            "apps.platform.tenants.services.get_clerk_user",
            lambda uid: {"clerk_user_id": uid, "email": "new@example.com"},
        )
        resp = client.post(
            "/api/v1/platform/tenant",
            data='{"name": "Acme"}',
            content_type="application/json",
            **_headers(clerk_jwt("user_new")),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["tenant"]["name"] == "Acme"
        assert body["apiKey"] is not None
        assert body["apiKey"].startswith(("ubb_live_", "ubb_test_"))
        assert Tenant.objects.count() == 1

    def test_is_idempotent_returns_existing_tenant_without_key(
        self, client, clerk_jwt, monkeypatch
    ):
        monkeypatch.setattr(
            "apps.platform.tenants.services.get_clerk_user",
            lambda uid: {"clerk_user_id": uid, "email": "new@example.com"},
        )
        client.post(
            "/api/v1/platform/tenant",
            data='{"name": "Acme"}',
            content_type="application/json",
            **_headers(clerk_jwt("user_new")),
        )
        resp = client.post(
            "/api/v1/platform/tenant",
            data='{"name": "Ignored"}',
            content_type="application/json",
            **_headers(clerk_jwt("user_new")),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["apiKey"] is None
        assert body["tenant"]["name"] == "Acme"  # original name kept

    def test_503_when_clerk_secret_missing(self, client, clerk_jwt, settings):
        settings.CLERK_SECRET_KEY = ""
        resp = client.post(
            "/api/v1/platform/tenant",
            data='{"name": "Acme"}',
            content_type="application/json",
            **_headers(clerk_jwt("user_new")),
        )
        assert resp.status_code == 503

    def test_rejects_empty_name(self, client, clerk_jwt, monkeypatch):
        monkeypatch.setattr(
            "apps.platform.tenants.services.get_clerk_user",
            lambda uid: {"clerk_user_id": uid, "email": "new@example.com"},
        )
        resp = client.post(
            "/api/v1/platform/tenant",
            data='{"name": "   "}',
            content_type="application/json",
            **_headers(clerk_jwt("user_new")),
        )
        assert resp.status_code == 422

    def test_rejects_name_too_long(self, client, clerk_jwt, monkeypatch):
        monkeypatch.setattr(
            "apps.platform.tenants.services.get_clerk_user",
            lambda uid: {"clerk_user_id": uid, "email": "new@example.com"},
        )
        resp = client.post(
            "/api/v1/platform/tenant",
            data=f'{{"name": "{"x" * 256}"}}',
            content_type="application/json",
            **_headers(clerk_jwt("user_new")),
        )
        assert resp.status_code == 422
```

- [ ] **Step 2: Add request/response schemas**

Append to `api/v1/schemas.py`:

```python
class CreateTenantRequest(CamelSchema):
    name: str

    @validator("name")
    def strip_and_validate(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("name must be non-empty")
        if len(v) > 255:
            raise ValueError("name must be <= 255 characters")
        return v


class CreateTenantResponse(CamelSchema):
    tenant: MeTenantResponse
    api_key: Optional[str] = None
```

(Ensure `validator` is imported — ninja uses pydantic; match existing validator patterns in the file.)

- [ ] **Step 3: Implement the endpoint**

Add to `platform_endpoints.py`:

```python
from apps.platform.tenants.services import provision_tenant_for_clerk_user
from core.clerk_api import ClerkAPIError


@platform_api.post("/tenant", response={201: CreateTenantResponse, 200: CreateTenantResponse}, auth=ClerkJWTAuth())
def create_tenant(request, payload: CreateTenantRequest):
    clerk_user_id = getattr(request, "clerk_user_id", None)
    if not clerk_user_id:
        raise HttpError(401, "Clerk authentication required")

    # Detect idempotent replay before calling the service (service returns raw_key=None)
    existed_before = TenantUser.objects.filter(clerk_user_id=clerk_user_id).exists()

    try:
        tenant, tu, raw_key = provision_tenant_for_clerk_user(
            clerk_user_id=clerk_user_id,
            tenant_name=payload.name,
        )
    except ClerkAPIError as exc:
        raise HttpError(503, f"Account verification failed: {exc}") from exc

    status_code = 200 if existed_before else 201
    return status_code, {
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "products": tenant.products,
            "pricing_cards_count": 0,
            "usage_events_count": 0,
        },
        "api_key": raw_key,
    }
```

Ensure imports at the top of the file include `TenantUser` and `HttpError` (already imported).

- [ ] **Step 4: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_platform_onboarding.py -v -k TestPostTenant
```

Expected: 5 tests PASS.

---

## Task 8: `PATCH /api/v1/platform/tenant` endpoint

**Files:**
- Modify: `ubb-platform/api/v1/platform_endpoints.py`
- Modify: `ubb-platform/api/v1/schemas.py`
- Modify: `ubb-platform/api/v1/tests/test_platform_onboarding.py`

- [ ] **Step 1: Write failing tests**

Append to `test_platform_onboarding.py`:

```python
class TestPatchTenant:
    def test_completes_onboarding(self, client, clerk_jwt):
        tenant, _ = _tenant_with_user("user_patch", completed=False)
        resp = client.patch(
            "/api/v1/platform/tenant",
            data='{"completeOnboarding": true}',
            content_type="application/json",
            **_headers(clerk_jwt("user_patch")),
        )
        assert resp.status_code == 200
        tenant.refresh_from_db()
        assert tenant.onboarding_completed_at is not None

    def test_renames_tenant(self, client, clerk_jwt):
        tenant, _ = _tenant_with_user("user_patch")
        resp = client.patch(
            "/api/v1/platform/tenant",
            data='{"name": "NewName"}',
            content_type="application/json",
            **_headers(clerk_jwt("user_patch")),
        )
        assert resp.status_code == 200
        tenant.refresh_from_db()
        assert tenant.name == "NewName"

    def test_requires_tenant_user(self, client, clerk_jwt):
        resp = client.patch(
            "/api/v1/platform/tenant",
            data='{"completeOnboarding": true}',
            content_type="application/json",
            **_headers(clerk_jwt("user_orphan")),
        )
        assert resp.status_code == 403
```

- [ ] **Step 2: Add the request schema**

Append to `api/v1/schemas.py`:

```python
class UpdateTenantRequest(CamelSchema):
    name: Optional[str] = None
    complete_onboarding: Optional[bool] = None

    @validator("name")
    def strip_and_validate(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must be non-empty")
        if len(v) > 255:
            raise ValueError("name must be <= 255 characters")
        return v
```

- [ ] **Step 3: Implement the endpoint**

Add to `platform_endpoints.py`:

```python
@platform_api.patch("/tenant", response=MeTenantResponse, auth=ClerkJWTAuth())
def update_tenant(request, payload: UpdateTenantRequest):
    if request.tenant_user is None:
        raise HttpError(403, "Tenant user required for this operation")

    tenant = request.tenant
    fields_to_update = ["updated_at"]

    if payload.name is not None:
        tenant.name = payload.name
        fields_to_update.append("name")

    if payload.complete_onboarding and tenant.onboarding_completed_at is None:
        tenant.onboarding_completed_at = timezone.now()
        fields_to_update.append("onboarding_completed_at")

    tenant.save(update_fields=fields_to_update)

    cards_count = Card.objects.filter(tenant=tenant).count()
    events_count = UsageEvent.objects.filter(tenant=tenant).count()
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "products": tenant.products,
        "pricing_cards_count": cards_count,
        "usage_events_count": events_count,
    }
```

Ensure `UpdateTenantRequest` is imported at the top.

- [ ] **Step 4: Run tests**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_platform_onboarding.py -v
```

Expected: all endpoint tests PASS (including prior TestGetMe and TestPostTenant classes).

- [ ] **Step 5: Run the full test suite to catch regressions**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q
```

Expected: all tests pass. Fix any regressions caused by Task 6 Step 4's auth change (endpoints with missing `tenant_user` guards).

---

## Task 9: Update `seed_dev_data` command

**Files:**
- Modify: `ubb-platform/apps/platform/tenants/management/commands/seed_dev_data.py`

- [ ] **Step 1: Add TenantUser creation and onboarding flag**

At the top of the file, add imports:

```python
from django.utils import timezone
from apps.platform.tenants.models import TenantUser
```

Add argument:

```python
        parser.add_argument(
            "--clerk-user-id",
            default="",
            help="Clerk user ID to link to the seeded tenant (creates TenantUser).",
        )
        parser.add_argument(
            "--clerk-email",
            default="dev@example.com",
            help="Email for the TenantUser (default: dev@example.com).",
        )
```

In `handle`, after the tenant is created and before the customer section, add:

```python
        # Ensure tenant has metering product and is marked as onboarded
        if "metering" not in tenant.products:
            tenant.products = sorted({*tenant.products, "metering"})
        if tenant.onboarding_completed_at is None:
            tenant.onboarding_completed_at = timezone.now()
        tenant.save(update_fields=["products", "onboarding_completed_at", "updated_at"])

        # Create TenantUser if clerk_user_id provided
        if options["clerk_user_id"]:
            tu, tu_created = TenantUser.objects.get_or_create(
                clerk_user_id=options["clerk_user_id"],
                defaults={
                    "tenant": tenant,
                    "email": options["clerk_email"],
                    "role": "owner",
                },
            )
            self.stdout.write(
                f"{'Created' if tu_created else 'Existing'} TenantUser: {tu.email}"
            )
```

- [ ] **Step 2: Sanity run**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py seed_dev_data --stripe-account acct_test --clerk-user-id user_dev_local --clerk-email dev@localhost
```

Expected: creates or updates tenant + TenantUser + marks onboarded.

---

## Task 10: Regenerate UI OpenAPI types

**Files:**
- Modify: `ubb-ui/src/api/schemas/platform.json`
- Modify: `ubb-ui/src/api/generated/platform.ts`

- [ ] **Step 1: Ensure Django is running**

Start the dev server if not running: `cd ubb-platform && .venv/bin/python manage.py runserver`.

- [ ] **Step 2: Run the generator**

```bash
cd ubb-ui && ./scripts/generate-api.sh
```

Expected: pulls fresh `platform.json` from `http://localhost:8000/api/v1/platform/openapi.json`, regenerates `generated/platform.ts` with `/me`, `/tenant` POST, `/tenant` PATCH operations.

- [ ] **Step 3: Type-check UI**

```bash
cd ubb-ui && npm run typecheck
```

Expected: no TS errors. If there are drift errors in existing code due to the schema regen, fix them inline (they should be rare — only if old endpoints' response shapes change inadvertently).

---

## Task 11: `useMe` hook and `auth` feature

**Files:**
- Create: `ubb-ui/src/features/auth/api/types.ts`
- Create: `ubb-ui/src/features/auth/api/mock.ts`
- Create: `ubb-ui/src/features/auth/api/api.ts`
- Create: `ubb-ui/src/features/auth/api/provider.ts`
- Create: `ubb-ui/src/features/auth/api/queries.ts`
- Create: `ubb-ui/src/features/auth/api/queries.test.ts`

- [ ] **Step 1: Create types**

`src/features/auth/api/types.ts`:

```ts
export interface MeTenantUser {
  id: string;
  email: string;
  role: "owner" | "admin" | "member";
}

export interface MeTenant {
  id: string;
  name: string;
  products: string[];
  pricingCardsCount: number;
  usageEventsCount: number;
}

export interface Me {
  tenantUser: MeTenantUser | null;
  tenant: MeTenant | null;
  onboardingCompleted: boolean;
}
```

- [ ] **Step 2: Create mock**

`src/features/auth/api/mock.ts`:

```ts
import type { Me } from "./types";
import { mockDelay } from "@/lib/api-provider";

export async function getMe(): Promise<Me> {
  await mockDelay();
  return {
    tenantUser: {
      id: "mock-tu-1",
      email: "mock@example.com",
      role: "owner",
    },
    tenant: {
      id: "mock-tenant-1",
      name: "Mock Workspace",
      products: ["metering"],
      pricingCardsCount: 3,
      usageEventsCount: 42,
    },
    onboardingCompleted: true,
  };
}
```

- [ ] **Step 3: Create api**

`src/features/auth/api/api.ts`:

```ts
import { platformApi } from "@/api/client";
import type { Me } from "./types";

export async function getMe(): Promise<Me> {
  const { data, error } = await platformApi.GET("/me", {});
  if (error) throw new Error("Failed to load user");
  return data as Me;
}
```

- [ ] **Step 4: Create provider**

`src/features/auth/api/provider.ts`:

```ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const authApi = selectProvider({ mock, api });
```

- [ ] **Step 5: Create queries**

`src/features/auth/api/queries.ts`:

```ts
import { queryOptions, useQuery } from "@tanstack/react-query";
import { authApi } from "./provider";

export const meQueryOptions = queryOptions({
  queryKey: ["me"] as const,
  queryFn: () => authApi.getMe(),
  staleTime: Infinity,
});

export const useMe = () => useQuery(meQueryOptions);
```

- [ ] **Step 6: Write tests**

`src/features/auth/api/queries.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useMe } from "./queries";

vi.mock("./provider", () => ({
  authApi: {
    getMe: vi.fn(),
  },
}));

import { authApi } from "./provider";

function withQueryClient() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useMe", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns Me payload on success", async () => {
    (authApi.getMe as ReturnType<typeof vi.fn>).mockResolvedValue({
      tenantUser: { id: "tu1", email: "a@b.com", role: "owner" },
      tenant: {
        id: "t1", name: "X", products: ["metering"],
        pricingCardsCount: 0, usageEventsCount: 0,
      },
      onboardingCompleted: false,
    });
    const { result } = renderHook(() => useMe(), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.onboardingCompleted).toBe(false);
  });

  it("surfaces error state when API fails", async () => {
    (authApi.getMe as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("401"));
    const { result } = renderHook(() => useMe(), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
```

- [ ] **Step 7: Run tests**

```bash
cd ubb-ui && npm run test -- src/features/auth/api/queries.test.ts
```

Expected: PASS.

---

## Task 12: Make `NewCardWizard` accept `onSuccess` / `onSkip` props

**Files:**
- Modify: `ubb-ui/src/features/pricing-cards/components/new-card-wizard.tsx`
- Modify: `ubb-ui/src/app/routes/_app/pricing-cards/new.tsx`

- [ ] **Step 1: Add props to NewCardWizard**

Open `new-card-wizard.tsx`. Add a props type and use it:

```tsx
interface NewCardWizardProps {
  onSuccess?: (cardId: string) => void;
  onSkip?: () => void;
}

export function NewCardWizard({ onSuccess, onSkip }: NewCardWizardProps = {}) {
  // ... existing hook setup ...
}
```

Find the existing success handler (wherever the wizard calls the create-card mutation and navigates). Today it probably calls `navigate({ to: "/pricing-cards" })` or similar. Replace that with:

```tsx
if (onSuccess) {
  onSuccess(createdCard.id);
} else {
  navigate({ to: "/pricing-cards" });
}
```

In the first step's footer (wherever back/skip buttons live), add a Skip button that renders **only when `onSkip` is provided**:

```tsx
{onSkip && (
  <button
    type="button"
    onClick={onSkip}
    className="text-[12px] text-muted-foreground underline"
  >
    Skip for now
  </button>
)}
```

- [ ] **Step 2: Ensure the route still works without props**

`src/app/routes/_app/pricing-cards/new.tsx` stays as-is — `NewCardWizard` is invoked without props, so default navigation kicks in.

- [ ] **Step 3: Manually verify in browser**

Run the app with `VITE_API_PROVIDER=mock`. Visit `/pricing-cards/new`. Confirm the wizard still navigates to `/pricing-cards` on completion.

- [ ] **Step 4: Typecheck**

```bash
cd ubb-ui && npm run typecheck
```

Expected: no errors.

---

## Task 13: Delete unused wizard components

**Files:**
- Delete: `ubb-ui/src/features/onboarding/components/stripe-key-step.tsx`
- Delete: `ubb-ui/src/features/onboarding/components/customer-mapping-step.tsx`
- Delete: `ubb-ui/src/features/onboarding/components/margin-config-step.tsx`
- Delete: `ubb-ui/src/features/onboarding/components/review-step.tsx`
- Delete: `ubb-ui/src/features/onboarding/components/mode-selector.tsx`
- Delete: `ubb-ui/src/features/onboarding/components/match-results-table.tsx`
- Delete: `ubb-ui/src/features/onboarding/components/permissions-table.tsx`
- Delete: `ubb-ui/src/features/onboarding/components/activation-success.tsx`
- Delete: `ubb-ui/src/features/onboarding/components/onboarding-layout.tsx`
- Delete: `ubb-ui/src/features/onboarding/lib/constants.ts` (contains unused `MOCK_TENANT_ID`)

- [ ] **Step 1: Delete the files**

```bash
cd ubb-ui && rm \
  src/features/onboarding/components/stripe-key-step.tsx \
  src/features/onboarding/components/customer-mapping-step.tsx \
  src/features/onboarding/components/margin-config-step.tsx \
  src/features/onboarding/components/review-step.tsx \
  src/features/onboarding/components/mode-selector.tsx \
  src/features/onboarding/components/match-results-table.tsx \
  src/features/onboarding/components/permissions-table.tsx \
  src/features/onboarding/components/activation-success.tsx \
  src/features/onboarding/components/onboarding-layout.tsx \
  src/features/onboarding/lib/constants.ts
```

- [ ] **Step 2: Remove imports from `onboarding-wizard.tsx`**

Open `src/features/onboarding/components/onboarding-wizard.tsx`. It imports all the deleted components — don't fix incrementally, since Task 14 rewrites this file. Leave it broken until Task 14.

- [ ] **Step 3: Typecheck will fail — that's expected**

Do **not** typecheck yet. The onboarding wizard will not compile until Task 14.

---

## Task 14: Rewrite onboarding types, schema, api, mock, queries

**Files:**
- Modify: `ubb-ui/src/features/onboarding/api/types.ts`
- Modify: `ubb-ui/src/features/onboarding/api/mock.ts`
- Modify: `ubb-ui/src/features/onboarding/api/api.ts`
- Modify: `ubb-ui/src/features/onboarding/api/queries.ts`
- Modify: `ubb-ui/src/features/onboarding/lib/schema.ts`

- [ ] **Step 1: `api/types.ts`**

Replace contents with:

```ts
import type { MeTenant } from "@/features/auth/api/types";

export interface CreateTenantRequest {
  name: string;
}

export interface CreateTenantResponse {
  tenant: MeTenant;
  apiKey: string | null;
}
```

- [ ] **Step 2: `api/mock.ts`**

Replace contents with:

```ts
import type { CreateTenantRequest, CreateTenantResponse } from "./types";
import type { MeTenant } from "@/features/auth/api/types";
import { mockDelay } from "@/lib/api-provider";

export async function createTenant(
  req: CreateTenantRequest
): Promise<CreateTenantResponse> {
  await mockDelay();
  const tenant: MeTenant = {
    id: "mock-tenant-" + Date.now(),
    name: req.name,
    products: ["metering"],
    pricingCardsCount: 0,
    usageEventsCount: 0,
  };
  return {
    tenant,
    apiKey: "ubb_test_mockkey_" + Math.random().toString(36).slice(2, 10),
  };
}

export async function completeOnboarding(): Promise<void> {
  await mockDelay();
}
```

- [ ] **Step 3: `api/api.ts`**

Replace contents with:

```ts
import type { CreateTenantRequest, CreateTenantResponse } from "./types";
import { platformApi } from "@/api/client";

export async function createTenant(
  req: CreateTenantRequest
): Promise<CreateTenantResponse> {
  const { data, error } = await platformApi.POST("/tenant", { body: req });
  if (error) throw new Error("Failed to create tenant");
  return data as CreateTenantResponse;
}

export async function completeOnboarding(): Promise<void> {
  const { error } = await platformApi.PATCH("/tenant", {
    body: { completeOnboarding: true },
  });
  if (error) throw new Error("Failed to complete onboarding");
}
```

- [ ] **Step 4: `api/queries.ts`**

Replace contents with:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { onboardingApi } from "./provider";
import type { CreateTenantRequest, CreateTenantResponse } from "./types";

export function useCreateTenant() {
  const qc = useQueryClient();
  return useMutation<CreateTenantResponse, Error, CreateTenantRequest>({
    mutationFn: (req) => onboardingApi.createTenant(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

export function useCompleteOnboarding() {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => onboardingApi.completeOnboarding(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}
```

- [ ] **Step 5: Verify `provider.ts` still exports the right shape**

`src/features/onboarding/api/provider.ts` should still read:

```ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";
export const onboardingApi = selectProvider({ mock, api });
```

(No changes needed if that's already the shape.)

- [ ] **Step 6: `lib/schema.ts`**

Replace contents with:

```ts
import { z } from "zod";

export const onboardingSchema = z.object({
  tenantName: z
    .string()
    .trim()
    .min(1, "Workspace name is required")
    .max(255, "Workspace name must be 255 characters or less"),
});

export type OnboardingFormValues = z.infer<typeof onboardingSchema>;
```

---

## Task 15: New onboarding step components

**Files:**
- Create: `ubb-ui/src/features/onboarding/components/name-workspace-step.tsx`
- Create: `ubb-ui/src/features/onboarding/components/create-card-step.tsx`
- Create: `ubb-ui/src/features/onboarding/components/sdk-step.tsx`

- [ ] **Step 1: `name-workspace-step.tsx`**

```tsx
import { useFormContext } from "react-hook-form";
import type { OnboardingFormValues } from "../lib/schema";

interface Props {
  onSubmit: () => void;
  isSubmitting: boolean;
  error: string | null;
}

export function NameWorkspaceStep({ onSubmit, isSubmitting, error }: Props) {
  const { register, formState: { errors } } = useFormContext<OnboardingFormValues>();
  return (
    <div className="space-y-4">
      <div className="text-center">
        <h1 className="text-[18px] font-semibold">Name your workspace</h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          You can rename it anytime.
        </p>
      </div>
      <div>
        <input
          type="text"
          placeholder="e.g. Acme Corp"
          autoFocus
          disabled={isSubmitting}
          {...register("tenantName")}
          className="w-full rounded-lg border border-border px-3 py-2 text-[13px]"
        />
        {errors.tenantName && (
          <p className="mt-1 text-[11px] text-destructive">
            {errors.tenantName.message}
          </p>
        )}
        {error && <p className="mt-1 text-[11px] text-destructive">{error}</p>}
      </div>
      <button
        type="button"
        onClick={onSubmit}
        disabled={isSubmitting}
        className="w-full rounded-lg bg-foreground px-5 py-2 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
      >
        {isSubmitting ? "Creating workspace…" : "Continue"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: `create-card-step.tsx`**

```tsx
import { NewCardWizard } from "@/features/pricing-cards/components/new-card-wizard";

interface Props {
  onSuccess: () => void;
  onSkip: () => void;
}

export function CreateCardStep({ onSuccess, onSkip }: Props) {
  return (
    <div className="space-y-4">
      <div className="text-center">
        <h1 className="text-[18px] font-semibold">Create your first pricing card</h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Pricing cards describe what you're tracking. You can skip this for now and add one later.
        </p>
      </div>
      <NewCardWizard onSuccess={() => onSuccess()} onSkip={onSkip} />
    </div>
  );
}
```

- [ ] **Step 3: `sdk-step.tsx`**

```tsx
import { useState } from "react";

interface Props {
  apiKey: string | null;
  onDone: () => void;
  isCompleting: boolean;
}

export function SdkStep({ apiKey, onDone, isCompleting }: Props) {
  const [copied, setCopied] = useState<"key" | "snippet" | null>(null);

  const snippet = apiKey
    ? `import { UBBClient } from "ubb-sdk";
const client = new UBBClient({ apiKey: "${apiKey}" });
await client.usage.record({
  customerId: "cus_123",
  cardId: "<your card id>",
  costMicros: 1000,
});`
    : "";

  const copy = (text: string, kind: "key" | "snippet") => {
    navigator.clipboard.writeText(text);
    setCopied(kind);
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h1 className="text-[18px] font-semibold">Connect the SDK</h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Send usage events from your codebase with the key below.
        </p>
      </div>

      {apiKey ? (
        <div>
          <label className="text-[11px] text-muted-foreground">API key</label>
          <div className="flex items-center gap-2">
            <code className="flex-1 rounded border border-border bg-muted px-2 py-1 text-[11px]">
              {apiKey}
            </code>
            <button
              type="button"
              onClick={() => copy(apiKey, "key")}
              className="rounded border border-border px-2 py-1 text-[11px]"
            >
              {copied === "key" ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">
            This key is shown once. Store it safely — you can't retrieve it again.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-[11px] text-amber-900">
          Your API key was shown earlier. If you didn't copy it, you'll need to
          generate a new one from Settings.
        </div>
      )}

      <div>
        <label className="text-[11px] text-muted-foreground">Example snippet</label>
        <pre className="whitespace-pre rounded border border-border bg-muted p-3 text-[11px]">
          {snippet || "// API key unavailable — generate a new one from Settings."}
        </pre>
        {snippet && (
          <button
            type="button"
            onClick={() => copy(snippet, "snippet")}
            className="mt-1 rounded border border-border px-2 py-1 text-[11px]"
          >
            {copied === "snippet" ? "Copied" : "Copy snippet"}
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={onDone}
        disabled={isCompleting}
        className="w-full rounded-lg bg-foreground px-5 py-2 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
      >
        {isCompleting ? "Finishing…" : "Done"}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Typecheck**

```bash
cd ubb-ui && npm run typecheck
```

Expected: no errors in new files. (Wizard file still broken until Task 16.)

---

## Task 16: Rewrite `onboarding-wizard.tsx`

**Files:**
- Modify: `ubb-ui/src/features/onboarding/components/onboarding-wizard.tsx`
- Create: `ubb-ui/src/features/onboarding/components/onboarding-wizard.test.tsx`

- [ ] **Step 1: Rewrite the wizard**

Replace `onboarding-wizard.tsx` with:

```tsx
import { useState } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "@tanstack/react-router";
import { onboardingSchema, type OnboardingFormValues } from "../lib/schema";
import { useCreateTenant, useCompleteOnboarding } from "../api/queries";
import { useMe } from "@/features/auth/api/queries";
import { Stepper } from "@/components/shared/stepper";
import { NameWorkspaceStep } from "./name-workspace-step";
import { CreateCardStep } from "./create-card-step";
import { SdkStep } from "./sdk-step";

const STEP_LABELS = ["Name workspace", "Create card", "Connect SDK"];

export function OnboardingWizard() {
  const navigate = useNavigate();
  const { data: me } = useMe();

  // If user has a tenant but hasn't completed onboarding, resume at Step 2.
  const initialStep = me?.tenant ? 1 : 0;
  const [step, setStep] = useState(initialStep);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<OnboardingFormValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: { tenantName: "" },
    mode: "onChange",
  });

  const createTenant = useCreateTenant();
  const completeOnboarding = useCompleteOnboarding();

  const handleNameSubmit = async () => {
    setSubmitError(null);
    const valid = await form.trigger();
    if (!valid) return;
    const { tenantName } = form.getValues();
    try {
      const result = await createTenant.mutateAsync({ name: tenantName });
      setApiKey(result.apiKey);
      setStep(1);
    } catch (err) {
      setSubmitError(
        err instanceof Error
          ? `Couldn't create workspace: ${err.message}`
          : "Couldn't create workspace. Please retry."
      );
    }
  };

  const handleCardDone = () => setStep(2);
  const handleCardSkip = () => setStep(2);

  const handleFinalDone = async () => {
    try {
      await completeOnboarding.mutateAsync();
      navigate({ to: "/" });
    } catch {
      setSubmitError("Couldn't complete onboarding. Please retry.");
    }
  };

  return (
    <div>
      <Stepper
        steps={STEP_LABELS.map((label) => ({ label }))}
        currentIndex={step}
        className="mb-6"
      />
      <FormProvider {...form}>
        {step === 0 && (
          <NameWorkspaceStep
            onSubmit={handleNameSubmit}
            isSubmitting={createTenant.isPending}
            error={submitError}
          />
        )}
        {step === 1 && (
          <CreateCardStep onSuccess={handleCardDone} onSkip={handleCardSkip} />
        )}
        {step === 2 && (
          <SdkStep
            apiKey={apiKey}
            onDone={handleFinalDone}
            isCompleting={completeOnboarding.isPending}
          />
        )}
      </FormProvider>
    </div>
  );
}
```

- [ ] **Step 2: Write component tests**

Create `onboarding-wizard.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

vi.mock("@/features/auth/api/queries", () => ({
  useMe: vi.fn(() => ({ data: { tenantUser: null, tenant: null, onboardingCompleted: false } })),
}));

const createTenantMutate = vi.fn();
const completeOnboardingMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useCreateTenant: () => ({
    mutateAsync: createTenantMutate,
    isPending: false,
  }),
  useCompleteOnboarding: () => ({
    mutateAsync: completeOnboardingMutate,
    isPending: false,
  }),
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("@/features/pricing-cards/components/new-card-wizard", () => ({
  NewCardWizard: ({ onSuccess, onSkip }: { onSuccess: () => void; onSkip: () => void }) =>
    React.createElement("div", { "data-testid": "card-wizard" },
      React.createElement("button", { onClick: onSuccess }, "Mock Success"),
      React.createElement("button", { onClick: onSkip }, "Mock Skip")
    ),
}));

import { OnboardingWizard } from "./onboarding-wizard";

function renderWizard() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(OnboardingWizard)
    )
  );
}

describe("OnboardingWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createTenantMutate.mockResolvedValue({
      tenant: { id: "t1", name: "Acme", products: ["metering"], pricingCardsCount: 0, usageEventsCount: 0 },
      apiKey: "ubb_test_abc123",
    });
    completeOnboardingMutate.mockResolvedValue(undefined);
  });

  it("renders step 1 (name workspace) initially", () => {
    renderWizard();
    expect(screen.getByText("Name your workspace")).toBeInTheDocument();
  });

  it("advances to step 2 after submitting workspace name", async () => {
    renderWizard();
    fireEvent.input(screen.getByPlaceholderText(/Acme Corp/), { target: { value: "Acme" } });
    fireEvent.click(screen.getByText("Continue"));
    await waitFor(() => expect(createTenantMutate).toHaveBeenCalledWith({ name: "Acme" }));
    await screen.findByText("Create your first pricing card");
  });

  it("advances to step 3 when user clicks Skip", async () => {
    renderWizard();
    fireEvent.input(screen.getByPlaceholderText(/Acme Corp/), { target: { value: "Acme" } });
    fireEvent.click(screen.getByText("Continue"));
    const skipBtn = await screen.findByText("Mock Skip");
    fireEvent.click(skipBtn);
    await screen.findByText("Connect the SDK");
  });

  it("shows API key on step 3 and fires complete on Done", async () => {
    renderWizard();
    fireEvent.input(screen.getByPlaceholderText(/Acme Corp/), { target: { value: "Acme" } });
    fireEvent.click(screen.getByText("Continue"));
    fireEvent.click(await screen.findByText("Mock Skip"));
    expect(await screen.findByText("ubb_test_abc123")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Done"));
    await waitFor(() => expect(completeOnboardingMutate).toHaveBeenCalled());
  });
});
```

- [ ] **Step 3: Run tests**

```bash
cd ubb-ui && npm run test -- src/features/onboarding/components/onboarding-wizard.test.tsx
```

Expected: 4 tests PASS.

- [ ] **Step 4: Typecheck the whole UI**

```bash
cd ubb-ui && npm run typecheck
```

Expected: no errors.

---

## Task 17: Routing guards

**Files:**
- Modify: `ubb-ui/src/app/routes/_app/route.tsx`
- Modify: `ubb-ui/src/app/routes/onboarding.tsx`

- [ ] **Step 1: Read the current routes**

Read `_app/route.tsx` and `onboarding.tsx` to see the current `createFileRoute` setup. Match that pattern.

- [ ] **Step 2: Add router context type for queryClient**

Find where the router is created (likely `src/app/router.tsx` or `src/main.tsx`). Ensure the router context includes `queryClient`:

```ts
// Typical pattern:
const router = createRouter({ routeTree, context: { queryClient } });
```

If `queryClient` is not already in context, add it. Update the root route to declare the context type if required by the codebase pattern.

- [ ] **Step 3: Update `_app/route.tsx`**

Replace (or augment) with:

```tsx
import { createFileRoute, redirect } from "@tanstack/react-router";
import { meQueryOptions } from "@/features/auth/api/queries";

export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context }) => {
    const me = await context.queryClient.ensureQueryData(meQueryOptions);
    if (!me.tenantUser || !me.onboardingCompleted) {
      throw redirect({ to: "/onboarding" });
    }
  },
  // Keep existing component / layout intact below.
});
```

(Preserve whatever else was in `_app/route.tsx` — layout component, loader, etc.)

- [ ] **Step 4: Update `onboarding.tsx`**

```tsx
import { createFileRoute, redirect } from "@tanstack/react-router";
import { meQueryOptions } from "@/features/auth/api/queries";
import { OnboardingWizard } from "@/features/onboarding/components/onboarding-wizard";

export const Route = createFileRoute("/onboarding")({
  beforeLoad: async ({ context }) => {
    const me = await context.queryClient.ensureQueryData(meQueryOptions);
    if (me.tenantUser && me.onboardingCompleted) {
      throw redirect({ to: "/" });
    }
  },
  component: OnboardingWizard,
});
```

- [ ] **Step 5: Regenerate route tree**

```bash
cd ubb-ui && npm run dev -- --help > /dev/null 2>&1 || true
# The TanStack Router plugin watches and regenerates routeTree.gen.ts on file changes.
# Run typecheck to trigger regen + verify.
npm run typecheck
```

Expected: `routeTree.gen.ts` is in sync; typecheck passes.

- [ ] **Step 6: Manual verification in browser**

With `VITE_API_PROVIDER=mock`, the mock `getMe()` returns `onboardingCompleted: true`, so the app should load straight to the dashboard. To test the redirect path, temporarily change the mock to return `tenantUser: null` and confirm `/` redirects to `/onboarding`.

---

## Task 18: Getting-started checklist

**Files:**
- Create: `ubb-ui/src/features/dashboard/components/getting-started.tsx`
- Create: `ubb-ui/src/features/dashboard/components/getting-started.test.tsx`
- Modify: dashboard page component (find via `grep -r "dashboard-page" src/features/dashboard`)

- [ ] **Step 1: Build the component**

```tsx
import { useState } from "react";
import { useMe } from "@/features/auth/api/queries";

const DISMISS_KEY = "getting-started:dismissed";

type ChecklistItem = {
  id: string;
  label: string;
  done: boolean;
  href?: string;
};

function getDismissed(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveDismissed(set: Set<string>) {
  localStorage.setItem(DISMISS_KEY, JSON.stringify([...set]));
}

export function GettingStarted() {
  const { data: me } = useMe();
  const [dismissed, setDismissed] = useState<Set<string>>(() => getDismissed());

  if (!me?.tenant) return null;

  const items: ChecklistItem[] = [
    {
      id: "create-card",
      label: "Create your first pricing card",
      done: me.tenant.pricingCardsCount > 0,
      href: "/pricing-cards/new",
    },
    {
      id: "send-event",
      label: "Send your first usage event",
      done: me.tenant.usageEventsCount > 0,
    },
    {
      id: "invite-teammate",
      label: "Invite a teammate (coming soon)",
      done: false,
    },
  ];

  const visible = items.filter((i) => !dismissed.has(i.id));
  if (visible.length === 0 || visible.every((i) => i.done)) return null;

  const dismiss = (id: string) => {
    const next = new Set(dismissed);
    next.add(id);
    setDismissed(next);
    saveDismissed(next);
  };

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="mb-3 text-[13px] font-medium">Getting started</h3>
      <ul className="space-y-2">
        {visible.map((item) => (
          <li key={item.id} className="flex items-center gap-2 text-[12px]">
            <input type="checkbox" checked={item.done} disabled className="h-3 w-3" />
            {item.href && !item.done ? (
              <a href={item.href} className="flex-1 underline hover:no-underline">
                {item.label}
              </a>
            ) : (
              <span className={item.done ? "flex-1 line-through text-muted-foreground" : "flex-1"}>
                {item.label}
              </span>
            )}
            <button
              type="button"
              onClick={() => dismiss(item.id)}
              className="text-[11px] text-muted-foreground hover:text-foreground"
              aria-label={`Dismiss ${item.label}`}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Test**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

vi.mock("@/features/auth/api/queries", () => ({
  useMe: vi.fn(),
}));

import { useMe } from "@/features/auth/api/queries";
import { GettingStarted } from "./getting-started";

const baseTenant = {
  id: "t1",
  name: "Acme",
  products: ["metering"],
  pricingCardsCount: 0,
  usageEventsCount: 0,
};

function mockMe(tenantOverrides: Partial<typeof baseTenant> = {}) {
  (useMe as ReturnType<typeof vi.fn>).mockReturnValue({
    data: {
      tenantUser: { id: "u", email: "a@b.c", role: "owner" },
      tenant: { ...baseTenant, ...tenantOverrides },
      onboardingCompleted: true,
    },
  });
}

describe("GettingStarted", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("shows all items when none done", () => {
    mockMe();
    render(React.createElement(GettingStarted));
    expect(screen.getByText("Create your first pricing card")).toBeInTheDocument();
    expect(screen.getByText("Send your first usage event")).toBeInTheDocument();
  });

  it("marks first item done when card count > 0", () => {
    mockMe({ pricingCardsCount: 2 });
    render(React.createElement(GettingStarted));
    const checkboxes = screen.getAllByRole("checkbox");
    expect((checkboxes[0] as HTMLInputElement).checked).toBe(true);
  });

  it("persists dismissal to localStorage", () => {
    mockMe();
    render(React.createElement(GettingStarted));
    const dismissButtons = screen.getAllByRole("button", { name: /Dismiss/ });
    fireEvent.click(dismissButtons[0]);
    expect(localStorage.getItem("getting-started:dismissed")).toContain("create-card");
  });

  it("hides entirely when every visible item is done", () => {
    mockMe({ pricingCardsCount: 1, usageEventsCount: 1 });
    // "invite-teammate" is never done — dismiss it so the panel collapses.
    localStorage.setItem("getting-started:dismissed", JSON.stringify(["invite-teammate"]));
    const { container } = render(React.createElement(GettingStarted));
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 3: Run tests**

```bash
cd ubb-ui && npm run test -- src/features/dashboard/components/getting-started.test.tsx
```

Expected: 4 tests PASS.

- [ ] **Step 4: Mount on dashboard**

Find the dashboard page component (`grep -r "dashboard-page\|DashboardPage" src/features/dashboard/components src/app/routes/_app/index.tsx`). Import `GettingStarted` and render it near the top of the page:

```tsx
import { GettingStarted } from "@/features/dashboard/components/getting-started";

// ... inside the page component render:
<GettingStarted />
```

---

## Task 19: Clean up `auth-store.ts`

**Files:**
- Modify: `ubb-ui/src/stores/auth-store.ts`
- Modify: any remaining callers (grep for `useAuthStore`)

- [ ] **Step 1: Find all callers**

```bash
cd ubb-ui && grep -rn "useAuthStore\|authStore\|activeTenantId\|tenantMode" src --include='*.ts' --include='*.tsx' | grep -v "\.test\."
```

- [ ] **Step 2: Determine what the store still needs**

Read the current `auth-store.ts`. If `activeTenantId` / `tenantMode` / `setTenant` / `permissions` are the only fields, and only the onboarding wizard (now rewritten) referenced them, **delete the file entirely** and remove any remaining imports.

If there are other UI-only fields (modals, nav state), keep those and remove only the tenant-identity fields.

- [ ] **Step 3: Replace callers with `useMe()`**

Any remaining call sites that read `activeTenantId` or `tenantMode` — replace with `useMe()`:

```tsx
const { data: me } = useMe();
const tenantId = me?.tenant?.id;
```

- [ ] **Step 4: Typecheck + test**

```bash
cd ubb-ui && npm run typecheck && npm run test
```

Expected: all passes.

---

## Task 20: End-to-end manual verification

This is not a coded test; it's the human-operator acceptance check before declaring done.

- [ ] **Step 1: Fresh Postgres state**

(Optional) Drop `onboarding_completed_at` on your test tenant to simulate a fresh user:

```sql
UPDATE ubb_tenant SET onboarding_completed_at = NULL;
DELETE FROM ubb_tenant_user;
```

(Or skip if you have a throwaway Clerk user.)

- [ ] **Step 2: Run the platform**

```bash
cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py runserver
```

- [ ] **Step 3: Run the UI in `api` mode**

Set `ubb-ui/.env.local`:

```
VITE_API_PROVIDER=api
VITE_API_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=pk_test_c3RpbGwtY2hhbW9pcy0yNi5jbGVyay5hY2NvdW50cy5kZXYk
```

```bash
cd ubb-ui && npm run dev
```

- [ ] **Step 4: Sign up as ashtoncochrane96@gmail.com in Clerk**

- Use the Clerk-hosted sign-up flow at `/sign-in` (or Clerk dashboard to create the user).
- After sign-in, expected: redirect to `/onboarding`.

- [ ] **Step 5: Complete the wizard**

- Step 1: enter "Ash's workspace" → Continue → creates tenant. Expected: Step 2 renders.
- Step 2: either create a pricing card (existing wizard flow) or click "Skip for now". Expected: Step 3 renders.
- Step 3: confirm API key is shown, copy it, click "Done". Expected: redirect to `/`.

- [ ] **Step 6: Reload and confirm no re-onboarding**

Reload the page. Expected: stays on `/`, does not redirect back to `/onboarding`.

- [ ] **Step 7: Confirm getting-started panel**

If you skipped card creation, the dashboard should show a "Getting started" checklist with "Create your first pricing card" unchecked.

---

## Self-Review Notes

**Spec coverage check:**

| Spec section | Implementing task(s) |
|---|---|
| 3.1 Provisioning via endpoint (not webhook) | Tasks 2, 5, 7 |
| 3.2 Data collected: name → card → SDK | Tasks 14, 15, 16 |
| 3.3 Gating: redirect + completion flag | Tasks 3, 8, 17 |
| 3.4 Scope: single-tenant, no invites | (enforced by existing schema; no code change) |
| 4.1 Provisioning service seam | Task 5 |
| 4.2 GET /me endpoint | Task 6 |
| 4.3 POST/PATCH endpoints | Tasks 7, 8 |
| 4.4 Routing guards with ensureQueryData | Task 17 |
| 5.1 `onboarding_completed_at` migration | Task 3 |
| 5.3 Atomic provisioning writes | Task 5 |
| 5.4 `TenantProvisioned` outbox event | Tasks 4, 5 |
| 5.5 CLERK_SECRET_KEY settings | Task 1 |
| 5.6 Clerk Backend API client | Task 2 |
| 6.1 `useMe()` hook | Task 11 |
| 6.2 Wizard rewrite, deletions | Tasks 13, 14, 15, 16 |
| 6.3 Routing guards | Task 17 |
| 6.4 Getting-started checklist | Task 18 |
| 6.5 auth-store cleanup | Task 19 |
| 7.x Error handling & edge cases | Covered inline in Tasks 5, 7, 8, 16 |
| 8.x Testing strategy | Tasks 2, 5, 6, 7, 8, 11, 16, 18 |
| 8.3 seed_dev_data update | Task 9 |
| 9 Follow-ups | Not implemented — tracked in spec |

No spec gaps.

**Placeholder scan:** no TBDs/TODOs found.

**Type consistency:** `MeTenant`, `MeTenantUser`, `Me`, `CreateTenantRequest`, `CreateTenantResponse`, `OnboardingFormValues` — names match across UI tasks. Backend: `MeResponse`, `MeTenantResponse`, `MeTenantUserResponse`, `CreateTenantRequest`, `CreateTenantResponse`, `UpdateTenantRequest` — match across tasks.
