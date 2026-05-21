# UBB UI — Tenant Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tenant-facing dashboard SPA where UBB tenants manage customers, pricing, usage, billing, and settings.

**Architecture:** Vite + React SPA consuming the existing django-ninja REST API. Clerk handles authentication — a new `ClerkJWTAuth` backend class enables dual-auth (API key + Clerk JWT) on existing endpoints, avoiding endpoint duplication. OpenAPI schemas are auto-generated per NinjaAPI instance and fed into `openapi-typescript` for end-to-end type safety.

**Tech Stack:** Vite, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, TanStack Router, TanStack Query, Clerk, openapi-typescript + openapi-fetch, Recharts, React Hook Form + Zod, Vitest + RTL + MSW

**Spec:** `docs/specs/2026-03-13-ubb-ui-dashboard-design.md`

---

## Chunk 1: Backend Prerequisites

These tasks add Clerk JWT auth, the TenantUser model, and missing API endpoints needed by the dashboard.

### Task 1: TenantUser Model

**Files:**
- Create: `ubb-platform/apps/platform/tenants/models.py` (add TenantUser class after Tenant)
- Create: `ubb-platform/apps/platform/tenants/migrations/NNNN_tenantuser.py` (auto-generated)
- Create: `ubb-platform/apps/platform/tenants/tests/test_tenant_user_model.py`

- [ ] **Step 1: Write the failing test**

```python
# ubb-platform/apps/platform/tenants/tests/test_tenant_user_model.py
import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant, TenantUser


@pytest.mark.django_db
class TestTenantUserModel:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test Tenant", products=["metering"])

    def test_create_tenant_user(self):
        user = TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_abc123",
            email="admin@test.com",
            role="owner",
        )
        assert user.id is not None
        assert user.tenant == self.tenant
        assert user.clerk_user_id == "user_abc123"
        assert user.role == "owner"

    def test_clerk_user_id_unique(self):
        TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_abc123",
            email="a@test.com",
            role="owner",
        )
        with pytest.raises(IntegrityError):
            TenantUser.objects.create(
                tenant=self.tenant,
                clerk_user_id="user_abc123",
                email="b@test.com",
                role="member",
            )

    def test_default_role_is_member(self):
        user = TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_def456",
            email="member@test.com",
        )
        assert user.role == "member"

    def test_multiple_users_per_tenant(self):
        TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_1",
            email="a@test.com",
            role="owner",
        )
        TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_2",
            email="b@test.com",
            role="member",
        )
        assert self.tenant.tenant_users.count() == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_tenant_user_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'TenantUser'`

- [ ] **Step 3: Write the TenantUser model**

Add to `ubb-platform/apps/platform/tenants/models.py` after the `TenantApiKey` class:

```python
class TenantUser(BaseModel):
    """Maps a Clerk user to a Tenant for dashboard authentication."""

    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("admin", "Admin"),
        ("member", "Member"),
    ]

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="tenant_users",
    )
    clerk_user_id = models.CharField(max_length=255, unique=True, db_index=True)
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="member")

    class Meta:
        db_table = "ubb_tenant_user"

    def __str__(self):
        return f"{self.email} ({self.role}) → {self.tenant.name}"
```

- [ ] **Step 4: Generate migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py makemigrations tenants --name tenantuser`

- [ ] **Step 5: Apply migration**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python manage.py migrate`

- [ ] **Step 6: Run test to verify it passes**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/tenants/tests/test_tenant_user_model.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add ubb-platform/apps/platform/tenants/models.py \
       ubb-platform/apps/platform/tenants/migrations/*_tenantuser.py \
       ubb-platform/apps/platform/tenants/tests/test_tenant_user_model.py
git commit -m "feat: add TenantUser model for Clerk JWT auth"
```

---

### Task 2: ClerkJWTAuth Class

**Files:**
- Create: `ubb-platform/core/clerk_auth.py`
- Create: `ubb-platform/core/tests/test_clerk_auth.py`

**Dependencies:** Task 1 (TenantUser model)

- [ ] **Step 1: Write the failing test**

```python
# ubb-platform/core/tests/test_clerk_auth.py
import json
from unittest.mock import patch, MagicMock
import pytest
from django.test import RequestFactory
from apps.platform.tenants.models import Tenant, TenantUser
from core.clerk_auth import ClerkJWTAuth


@pytest.mark.django_db
class TestClerkJWTAuth:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.tenant_user = TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_clerk123",
            email="admin@test.com",
            role="owner",
        )
        self.auth = ClerkJWTAuth()
        self.factory = RequestFactory()

    @patch("core.clerk_auth.verify_clerk_token")
    def test_valid_token_returns_key_like_object(self, mock_verify):
        mock_verify.return_value = {"sub": "user_clerk123"}
        request = self.factory.get("/api/v1/platform/customers")
        result = self.auth.authenticate(request, "valid.jwt.token")
        assert result is not None
        assert request.tenant == self.tenant

    @patch("core.clerk_auth.verify_clerk_token")
    def test_invalid_token_returns_none(self, mock_verify):
        mock_verify.return_value = None
        request = self.factory.get("/api/v1/platform/customers")
        result = self.auth.authenticate(request, "bad.jwt.token")
        assert result is None

    @patch("core.clerk_auth.verify_clerk_token")
    def test_valid_token_unknown_user_returns_none(self, mock_verify):
        mock_verify.return_value = {"sub": "user_unknown"}
        request = self.factory.get("/api/v1/platform/customers")
        result = self.auth.authenticate(request, "valid.jwt.token")
        assert result is None

    @patch("core.clerk_auth.verify_clerk_token")
    def test_sets_tenant_user_on_request(self, mock_verify):
        mock_verify.return_value = {"sub": "user_clerk123"}
        request = self.factory.get("/api/v1/platform/customers")
        self.auth.authenticate(request, "valid.jwt.token")
        assert request.tenant_user == self.tenant_user
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_clerk_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.clerk_auth'`

- [ ] **Step 3: Write the ClerkJWTAuth implementation**

```python
# ubb-platform/core/clerk_auth.py
"""Clerk JWT authentication for tenant dashboard users."""

import logging
from functools import lru_cache

import jwt
import requests
from django.conf import settings
from ninja.security import HttpBearer

from apps.platform.tenants.models import TenantUser

logger = logging.getLogger(__name__)

# Cache JWKS keys for 1 hour
_jwks_cache = {"keys": None, "fetched_at": 0}
JWKS_CACHE_TTL = 3600


def _get_jwks():
    """Fetch Clerk's JWKS keys, with caching."""
    import time

    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < JWKS_CACHE_TTL:
        return _jwks_cache["keys"]

    clerk_issuer = settings.CLERK_ISSUER_URL  # e.g. "https://your-app.clerk.accounts.dev"
    jwks_url = f"{clerk_issuer}/.well-known/jwks.json"
    try:
        resp = requests.get(jwks_url, timeout=5)
        resp.raise_for_status()
        keys = resp.json()["keys"]
        _jwks_cache["keys"] = keys
        _jwks_cache["fetched_at"] = now
        return keys
    except Exception:
        logger.exception("Failed to fetch Clerk JWKS")
        return _jwks_cache["keys"]  # Return stale cache if available


def verify_clerk_token(token: str) -> dict | None:
    """Verify a Clerk JWT and return its claims, or None if invalid."""
    jwks = _get_jwks()
    if not jwks:
        return None

    try:
        # Decode header to find the key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            return None

        # Find the matching key
        matching_key = None
        for key in jwks:
            if key.get("kid") == kid:
                matching_key = key
                break
        if not matching_key:
            return None

        # Build the public key and verify
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(matching_key)
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=settings.CLERK_ISSUER_URL,
            options={"require": ["sub", "iss", "exp"]},
        )
        return claims
    except jwt.PyJWTError:
        logger.debug("Clerk JWT verification failed", exc_info=True)
        return None


class ClerkJWTAuth(HttpBearer):
    """Authenticate dashboard users via Clerk JWT.

    Sets request.tenant and request.tenant_user, matching the shape
    that existing endpoints expect from ApiKeyAuth.
    """

    def authenticate(self, request, token: str):
        claims = verify_clerk_token(token)
        if claims is None:
            return None

        clerk_user_id = claims.get("sub")
        if not clerk_user_id:
            return None

        try:
            tenant_user = TenantUser.objects.select_related("tenant").get(
                clerk_user_id=clerk_user_id
            )
        except TenantUser.DoesNotExist:
            return None

        request.tenant = tenant_user.tenant
        request.tenant_user = tenant_user
        return tenant_user  # Becomes request.auth
```

- [ ] **Step 4: Add CLERK_ISSUER_URL to settings**

Add to `ubb-platform/config/settings.py` after the existing env vars:

```python
CLERK_ISSUER_URL = os.environ.get("CLERK_ISSUER_URL", "")
```

- [ ] **Step 5: Verify PyJWT is available**

Run: `cd ubb-platform && .venv/bin/python -c "import jwt; print(jwt.__version__)"`

Note: PyJWT is already in `requirements.txt`. If the `[crypto]` extras (for RS256) are not installed, run: `cd ubb-platform && .venv/bin/pip install PyJWT[crypto]`

- [ ] **Step 6: Run test to verify it passes**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_clerk_auth.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add ubb-platform/core/clerk_auth.py \
       ubb-platform/core/tests/test_clerk_auth.py \
       ubb-platform/config/settings.py
git commit -m "feat: add ClerkJWTAuth for dashboard authentication"
```

---

### Task 3: Create Dashboard-Scoped NinjaAPI + Enable Dual-Auth on Read Endpoints

**Files:**
- Create: `ubb-platform/api/v1/dashboard_endpoints.py` (new read-only dashboard API)
- Modify: `ubb-platform/config/urls.py` (mount dashboard API)
- Modify: `ubb-platform/api/v1/platform_endpoints.py` (add ClerkJWTAuth to platform API only)
- Create: `ubb-platform/core/tests/test_dual_auth.py`

**Dependencies:** Task 2 (ClerkJWTAuth class)

**IMPORTANT — Authorization Boundaries:**

The existing APIs protect sensitive write paths (usage ingestion, wallet debits, rate card changes) with API-key auth + product gating. Dashboard users should NOT get unrestricted access to these machine-to-machine write endpoints. Instead:

1. **Platform API** (`/api/v1/platform/`) — add dual-auth. This API is read/CRUD for customers, which dashboard users legitimately need.
2. **New Dashboard API** (`/api/v1/dashboard/`) — a dedicated read-only API for dashboard views (wallet overview, usage analytics, billing summaries). Uses `ClerkJWTAuth` only.
3. **Metering, Billing, Subscriptions, Referrals, Webhook APIs** — keep as API-key-only. Dashboard reads data through the dedicated dashboard API, not through write-capable machine APIs.

This ensures dashboard sessions cannot call `POST /metering/usage` (record usage), `POST /billing/customers/{id}/refund` (issue refunds), or other sensitive write paths.

- [ ] **Step 1: Write the failing tests**

```python
# ubb-platform/core/tests/test_dual_auth.py
"""Verify auth boundaries: Clerk JWT works on platform + dashboard APIs,
but is rejected on machine-to-machine APIs (metering, billing, etc.)."""
import json
import pytest
from unittest.mock import patch
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey, TenantUser


@pytest.mark.django_db
class TestDualAuthOnPlatformAPI:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="DualAuth Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.tenant_user = TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_dual_test",
            email="dual@test.com",
            role="owner",
        )

    def test_api_key_auth_works_on_platform_create(self):
        """API key auth on existing POST /customers still works."""
        resp = self.http_client.post(
            "/api/v1/platform/customers",
            data=json.dumps({"external_id": "apikey_test"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.api_key}",
        )
        assert resp.status_code == 201

    @patch("core.clerk_auth.verify_clerk_token")
    def test_clerk_jwt_works_on_platform_create(self, mock_verify):
        """Clerk JWT on POST /customers also works (dual-auth)."""
        mock_verify.return_value = {"sub": "user_dual_test"}
        resp = self.http_client.post(
            "/api/v1/platform/customers",
            data=json.dumps({"external_id": "clerk_test"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer fake.jwt.token",
        )
        assert resp.status_code == 201

    def test_no_auth_returns_401(self):
        resp = self.http_client.post(
            "/api/v1/platform/customers",
            data=json.dumps({"external_id": "noauth"}),
            content_type="application/json",
        )
        assert resp.status_code == 401


@pytest.mark.django_db
class TestClerkJWTRejectedOnMachineAPIs:
    """Clerk JWT should NOT be accepted on metering/billing APIs."""

    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
        )
        TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_blocked",
            email="blocked@test.com",
        )

    @patch("core.clerk_auth.verify_clerk_token")
    def test_clerk_jwt_rejected_on_metering_api(self, mock_verify):
        mock_verify.return_value = {"sub": "user_blocked"}
        resp = self.http_client.get(
            "/api/v1/metering/pricing/rates",
            HTTP_AUTHORIZATION="Bearer fake.jwt.token",
        )
        assert resp.status_code == 401

    @patch("core.clerk_auth.verify_clerk_token")
    def test_clerk_jwt_rejected_on_billing_api(self, mock_verify):
        mock_verify.return_value = {"sub": "user_blocked"}
        resp = self.http_client.get(
            "/api/v1/billing/wallets",
            HTTP_AUTHORIZATION="Bearer fake.jwt.token",
        )
        assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_dual_auth.py -v`
Expected: FAIL — Clerk JWT tests fail (ClerkJWTAuth not yet registered on platform API)

- [ ] **Step 3: Add ClerkJWTAuth to platform API only**

In `ubb-platform/api/v1/platform_endpoints.py`, change:
```python
from core.auth import ApiKeyAuth
platform_api = NinjaAPI(auth=ApiKeyAuth(), ...)
```
To:
```python
from core.auth import ApiKeyAuth
from core.clerk_auth import ClerkJWTAuth
platform_api = NinjaAPI(auth=[ApiKeyAuth(), ClerkJWTAuth()], ...)
```

Do NOT modify any other API instance (metering, billing, subscriptions, referrals, webhooks, tenant). These remain API-key-only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest core/tests/test_dual_auth.py -v`
Expected: All passed — Clerk JWT accepted on platform API, rejected on metering/billing

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add ubb-platform/api/v1/platform_endpoints.py \
       ubb-platform/core/tests/test_dual_auth.py
git commit -m "feat: enable Clerk JWT auth on platform API with auth boundary tests"
```

---

### Task 4: Customer List/Detail/Update/Delete Endpoints

**Files:**
- Modify: `ubb-platform/api/v1/platform_endpoints.py` (add endpoints)
- Create: `ubb-platform/apps/platform/customers/tests/test_customer_endpoints.py`

**Dependencies:** Task 3 (dual-auth enabled)

The platform API currently only has `POST /customers`. The dashboard needs list, detail, update, and soft-delete.

- [ ] **Step 1: Write the failing tests**

```python
# ubb-platform/apps/platform/customers/tests/test_customer_endpoints.py
import json
import pytest
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestCustomerListEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}
        self.c1 = Customer.objects.create(
            tenant=self.tenant, external_id="cust_1", status="active",
        )
        self.c2 = Customer.objects.create(
            tenant=self.tenant, external_id="cust_2", status="suspended",
        )

    def test_list_customers(self):
        resp = self.http_client.get("/api/v1/platform/customers", **self.headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert "next_cursor" in body
        assert "has_more" in body

    def test_list_customers_filter_by_status(self):
        resp = self.http_client.get(
            "/api/v1/platform/customers?status=active", **self.headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["external_id"] == "cust_1"

    def test_list_customers_search_by_external_id(self):
        resp = self.http_client.get(
            "/api/v1/platform/customers?search=cust_2", **self.headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_excludes_other_tenants(self):
        other_tenant = Tenant.objects.create(name="Other", products=["metering"])
        Customer.objects.create(tenant=other_tenant, external_id="other_cust")
        resp = self.http_client.get("/api/v1/platform/customers", **self.headers)
        assert len(resp.json()["data"]) == 2

    def test_list_excludes_soft_deleted(self):
        self.c2.soft_delete()
        resp = self.http_client.get("/api/v1/platform/customers", **self.headers)
        assert len(resp.json()["data"]) == 1


@pytest.mark.django_db
class TestCustomerDetailEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_1",
        )

    def test_get_customer(self):
        resp = self.http_client.get(
            f"/api/v1/platform/customers/{self.customer.id}", **self.headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["external_id"] == "cust_1"
        assert body["status"] == "active"

    def test_get_customer_not_found(self):
        import uuid
        resp = self.http_client.get(
            f"/api/v1/platform/customers/{uuid.uuid4()}", **self.headers,
        )
        assert resp.status_code == 404


@pytest.mark.django_db
class TestCustomerUpdateEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_1",
        )

    def test_update_customer_metadata(self):
        resp = self.http_client.patch(
            f"/api/v1/platform/customers/{self.customer.id}",
            data=json.dumps({"metadata": {"plan": "pro"}}),
            content_type="application/json",
            **self.headers,
        )
        assert resp.status_code == 200
        self.customer.refresh_from_db()
        assert self.customer.metadata == {"plan": "pro"}

    def test_update_customer_status(self):
        resp = self.http_client.patch(
            f"/api/v1/platform/customers/{self.customer.id}",
            data=json.dumps({"status": "suspended"}),
            content_type="application/json",
            **self.headers,
        )
        assert resp.status_code == 200
        self.customer.refresh_from_db()
        assert self.customer.status == "suspended"


@pytest.mark.django_db
class TestCustomerDeleteEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_1",
        )

    def test_delete_customer_soft_deletes(self):
        resp = self.http_client.delete(
            f"/api/v1/platform/customers/{self.customer.id}", **self.headers,
        )
        assert resp.status_code == 204
        assert Customer.objects.filter(id=self.customer.id).count() == 0
        assert Customer.all_objects.filter(id=self.customer.id).count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/customers/tests/test_customer_endpoints.py -v`
Expected: FAIL — 404 (endpoints don't exist yet)

- [ ] **Step 3: Implement the endpoints**

Add to `ubb-platform/api/v1/platform_endpoints.py`:

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from apps.platform.customers.models import Customer
from api.v1.pagination import encode_cursor, apply_cursor_filter


class CustomerListResponse(Schema):
    id: str
    external_id: str
    stripe_customer_id: str
    status: str
    metadata: dict
    created_at: str
    updated_at: str


class PaginatedCustomerResponse(Schema):
    data: list[CustomerListResponse]
    next_cursor: Optional[str] = None
    has_more: bool


class UpdateCustomerRequest(Schema):
    status: Optional[str] = None
    metadata: Optional[dict] = None
    stripe_customer_id: Optional[str] = None
    min_balance_micros: Optional[int] = None


def _customer_to_dict(c: Customer) -> dict:
    return {
        "id": str(c.id),
        "external_id": c.external_id,
        "stripe_customer_id": c.stripe_customer_id,
        "status": c.status,
        "metadata": c.metadata,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


@platform_api.get("/customers", response=PaginatedCustomerResponse)
def list_customers(
    request,
    status: str = None,
    search: str = None,
    cursor: str = None,
    limit: int = 50,
):
    _rate_limit(request)
    qs = Customer.objects.filter(tenant=request.auth.tenant).order_by("-created_at", "-id")

    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(external_id__icontains=search)

    limit = min(max(limit, 1), 100)

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return platform_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    customers = list(qs[: limit + 1])
    has_more = len(customers) > limit
    customers = customers[:limit]

    next_cursor = None
    if has_more and customers:
        last = customers[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [_customer_to_dict(c) for c in customers],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@platform_api.get("/customers/{customer_id}", response={200: dict, 404: dict})
def get_customer(request, customer_id: UUID):
    _rate_limit(request)
    try:
        customer = Customer.objects.get(id=customer_id, tenant=request.auth.tenant)
    except Customer.DoesNotExist:
        return 404, {"error": "Customer not found"}
    return 200, _customer_to_dict(customer)


@platform_api.patch("/customers/{customer_id}", response={200: dict, 404: dict})
def update_customer(request, customer_id: UUID, payload: UpdateCustomerRequest):
    _rate_limit(request)
    try:
        customer = Customer.objects.get(id=customer_id, tenant=request.auth.tenant)
    except Customer.DoesNotExist:
        return 404, {"error": "Customer not found"}

    if payload.status is not None:
        customer.status = payload.status
    if payload.metadata is not None:
        customer.metadata = payload.metadata
    if payload.stripe_customer_id is not None:
        customer.stripe_customer_id = payload.stripe_customer_id
    if payload.min_balance_micros is not None:
        customer.min_balance_micros = payload.min_balance_micros

    customer.save()
    return 200, _customer_to_dict(customer)


@platform_api.delete("/customers/{customer_id}", response={204: None, 404: dict})
def delete_customer(request, customer_id: UUID):
    _rate_limit(request)
    try:
        customer = Customer.objects.get(id=customer_id, tenant=request.auth.tenant)
    except Customer.DoesNotExist:
        return 404, {"error": "Customer not found"}
    customer.soft_delete()
    return 204, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/customers/tests/test_customer_endpoints.py -v`
Expected: All passed

- [ ] **Step 5: Run full test suite**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add ubb-platform/api/v1/platform_endpoints.py \
       ubb-platform/apps/platform/customers/tests/test_customer_endpoints.py
git commit -m "feat: add customer list/detail/update/delete endpoints"
```

---

### Task 5: Wallet Overview on Platform API (Dashboard-Accessible)

**Files:**
- Modify: `ubb-platform/api/v1/platform_endpoints.py` (add wallet overview endpoint)
- Create: `ubb-platform/apps/platform/customers/tests/test_wallet_overview_endpoint.py`

**Why platform API, not billing API?** The billing API remains API-key-only (machine-to-machine). Dashboard users authenticate via ClerkJWT on the platform API, so read-only billing views for the dashboard go here. This is a cross-domain read — it queries Wallet data but serves it through the platform API, scoped to the authenticated tenant.

- [ ] **Step 1: Write the failing test**

```python
# ubb-platform/apps/platform/customers/tests/test_wallet_overview_endpoint.py
import pytest
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet


@pytest.mark.django_db
class TestWalletOverviewEndpoint:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
        )
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}

        self.c1 = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.c2 = Customer.objects.create(tenant=self.tenant, external_id="c2")
        self.w1 = Wallet.objects.create(customer=self.c1, balance_micros=5_000_000)
        self.w2 = Wallet.objects.create(customer=self.c2, balance_micros=500_000)

    def test_list_wallets(self):
        resp = self.http_client.get(
            "/api/v1/platform/wallets", **self.headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2

    def test_list_wallets_low_balance_filter(self):
        resp = self.http_client.get(
            "/api/v1/platform/wallets?max_balance_micros=1000000",
            **self.headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["customer_external_id"] == "c2"

    def test_list_wallets_excludes_other_tenants(self):
        other = Tenant.objects.create(name="Other", products=["metering", "billing"])
        oc = Customer.objects.create(tenant=other, external_id="oc")
        Wallet.objects.create(customer=oc, balance_micros=999)
        resp = self.http_client.get(
            "/api/v1/platform/wallets", **self.headers,
        )
        assert len(resp.json()["data"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/customers/tests/test_wallet_overview_endpoint.py -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement the endpoint**

Add to `ubb-platform/api/v1/platform_endpoints.py`:

```python
from apps.billing.wallets.models import Wallet


@platform_api.get("/wallets")
def list_wallets(
    request,
    max_balance_micros: int = None,
    cursor: str = None,
    limit: int = 50,
):
    """Read-only wallet overview for dashboard. Queries billing data scoped to tenant."""
    _rate_limit(request)

    qs = Wallet.objects.filter(
        customer__tenant=request.auth.tenant
    ).select_related("customer").order_by("-created_at", "-id")

    if max_balance_micros is not None:
        qs = qs.filter(balance_micros__lte=max_balance_micros)

    limit = min(max(limit, 1), 100)

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return platform_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    wallets = list(qs[: limit + 1])
    has_more = len(wallets) > limit
    wallets = wallets[:limit]

    next_cursor = None
    if has_more and wallets:
        last = wallets[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(w.id),
                "customer_id": str(w.customer_id),
                "customer_external_id": w.customer.external_id,
                "balance_micros": w.balance_micros,
                "currency": w.currency,
                "created_at": w.created_at.isoformat(),
            }
            for w in wallets
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/customers/tests/test_wallet_overview_endpoint.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add ubb-platform/api/v1/platform_endpoints.py \
       ubb-platform/apps/platform/customers/tests/test_wallet_overview_endpoint.py
git commit -m "feat: add wallet overview endpoint on platform API for dashboard"
```

---

## Chunk 2: Frontend Scaffolding & Auth

### Task 6: Initialize Vite + React + TypeScript Project

**Files:**
- Create: `ubb-ui/` (entire directory via `pnpm create vite`)
- Modify: `ubb-ui/package.json` (add dependencies)
- Modify: `ubb-ui/vite.config.ts` (add API proxy)
- Create: `ubb-ui/.gitignore`

- [ ] **Step 1: Scaffold the Vite project**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb
pnpm create vite ubb-ui --template react-ts
cd ubb-ui
```

- [ ] **Step 2: Install core dependencies**

```bash
cd ubb-ui
pnpm add @tanstack/react-router @tanstack/react-query @clerk/clerk-react openapi-fetch recharts react-hook-form @hookform/resolvers zod sonner zustand
pnpm add -D @tanstack/router-plugin openapi-typescript @types/node vitest @testing-library/react @testing-library/jest-dom jsdom msw
```

- [ ] **Step 3: Configure Vite with API proxy**

Replace `ubb-ui/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import path from "path";

export default defineConfig({
  plugins: [TanStackRouterVite(), react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
```

- [ ] **Step 4: Create test setup file**

```ts
// ubb-ui/src/test-setup.ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 5: Update tsconfig.json path aliases**

Ensure `ubb-ui/tsconfig.json` has:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

- [ ] **Step 6: Verify the dev server starts**

```bash
cd ubb-ui && pnpm dev
```
Expected: Vite dev server starts on localhost:5173

- [ ] **Step 7: Commit**

```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb
git add ubb-ui/
git commit -m "feat: scaffold ubb-ui with Vite + React + TypeScript"
```

---

### Task 7: Install and Configure shadcn/ui + Tailwind CSS v4

**Files:**
- Modify: `ubb-ui/package.json` (add tailwind + shadcn deps)
- Create/Modify: `ubb-ui/src/index.css` (Tailwind v4 CSS config + shadcn theme)
- Delete: `ubb-ui/tailwind.config.ts` (if created — v4 uses CSS config)
- Modify: `ubb-ui/components.json` (shadcn config)

- [ ] **Step 1: Install Tailwind CSS v4**

```bash
cd ubb-ui
pnpm add tailwindcss @tailwindcss/vite
```

Add the Tailwind Vite plugin to `vite.config.ts`:
```ts
import tailwindcss from "@tailwindcss/vite";
// In plugins array:
plugins: [TanStackRouterVite(), tailwindcss(), react()],
```

- [ ] **Step 2: Set up CSS with Tailwind v4 directives**

Replace `ubb-ui/src/index.css`:
```css
@import "tailwindcss";
```

- [ ] **Step 3: Initialize shadcn/ui**

```bash
cd ubb-ui
pnpm dlx shadcn@latest init
```

Follow prompts:
- Style: Default
- Base color: Neutral (or Zinc for a more premium feel)
- CSS variables: Yes

This creates `components.json` and updates `src/index.css` with shadcn's CSS variables.

- [ ] **Step 4: Install essential shadcn components**

```bash
cd ubb-ui
pnpm dlx shadcn@latest add button card input label table dialog sheet \
  dropdown-menu command separator skeleton badge tabs avatar \
  form select textarea toast tooltip popover scroll-area sidebar
```

- [ ] **Step 5: Verify a component renders**

Update `ubb-ui/src/App.tsx` temporarily:
```tsx
import { Button } from "@/components/ui/button";

export default function App() {
  return (
    <div className="p-8">
      <Button>It works</Button>
    </div>
  );
}
```

Run: `cd ubb-ui && pnpm dev`
Expected: Button renders with shadcn styling

- [ ] **Step 6: Commit**

```bash
git add ubb-ui/
git commit -m "feat: configure Tailwind CSS v4 + shadcn/ui"
```

---

### Task 8: Set Up TanStack Router

**Files:**
- Create: `ubb-ui/src/routes/__root.tsx`
- Create: `ubb-ui/src/routes/_authenticated.tsx` (layout route with auth guard)
- Create: `ubb-ui/src/routes/_authenticated/index.tsx` (dashboard home)
- Create: `ubb-ui/src/routes/sign-in.tsx`
- Modify: `ubb-ui/src/main.tsx`

- [ ] **Step 1: Create the root route**

```tsx
// ubb-ui/src/routes/__root.tsx
import { createRootRoute, Outlet } from "@tanstack/react-router";

export const Route = createRootRoute({
  component: () => <Outlet />,
});
```

- [ ] **Step 2: Create the sign-in route**

```tsx
// ubb-ui/src/routes/sign-in.tsx
import { createFileRoute } from "@tanstack/react-router";
import { SignIn } from "@clerk/clerk-react";

export const Route = createFileRoute("/sign-in")({
  component: SignInPage,
});

function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn routing="path" path="/sign-in" afterSignInUrl="/" />
    </div>
  );
}
```

- [ ] **Step 3: Create the authenticated layout route**

```tsx
// ubb-ui/src/routes/_authenticated.tsx
import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated")({
  beforeLoad: ({ context }) => {
    if (!context.auth?.isSignedIn) {
      throw redirect({ to: "/sign-in" });
    }
  },
  component: AuthenticatedLayout,
});

function AuthenticatedLayout() {
  return <Outlet />;
}
```

- [ ] **Step 4: Create the dashboard home placeholder**

```tsx
// ubb-ui/src/routes/_authenticated/index.tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/")({
  component: DashboardHome,
});

function DashboardHome() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <p className="text-muted-foreground">Welcome to UBB.</p>
    </div>
  );
}
```

- [ ] **Step 5: Set up main.tsx with router + Clerk**

```tsx
// ubb-ui/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider, useAuth } from "@clerk/clerk-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

const router = createRouter({
  routeTree,
  context: { auth: undefined! },
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

function InnerApp() {
  const auth = useAuth();
  return <RouterProvider router={router} context={{ auth }} />;
}

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={clerkPubKey}>
      <QueryClientProvider client={queryClient}>
        <InnerApp />
      </QueryClientProvider>
    </ClerkProvider>
  </React.StrictMode>
);
```

- [ ] **Step 6: Create .env.local for development**

```
# ubb-ui/.env.local
VITE_API_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=pk_test_your_key_here
```

Add `.env.local` to `.gitignore`.

- [ ] **Step 7: Verify routing works**

```bash
cd ubb-ui && pnpm dev
```
Expected: Navigating to `/` redirects to `/sign-in` (no Clerk key yet, but routing works)

- [ ] **Step 8: Commit**

```bash
git add ubb-ui/
git commit -m "feat: set up TanStack Router with Clerk auth guard"
```

---

### Task 9: API Client Layer

**Files:**
- Create: `ubb-ui/scripts/generate-api.sh`
- Create: `ubb-ui/src/api/client.ts`
- Create: `ubb-ui/src/api/hooks/use-customers.ts`
- Create: `ubb-ui/src/api/generated/.gitkeep`

- [ ] **Step 1: Create the OpenAPI codegen script**

```bash
#!/bin/bash
# ubb-ui/scripts/generate-api.sh
# Generates TypeScript types from django-ninja OpenAPI schemas.
# Requires the Django dev server to be running on localhost:8000.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$SCRIPT_DIR/../src/api/generated"
mkdir -p "$OUT_DIR"

BASE_URL="${API_URL:-http://localhost:8000}"

APIS=("platform" "metering" "billing" "tenant")

for api in "${APIS[@]}"; do
  echo "Generating types for $api..."
  url="$BASE_URL/api/v1/$api/openapi.json"
  npx openapi-typescript "$url" -o "$OUT_DIR/${api}.ts"
done

echo "Done! Generated types for: ${APIS[*]}"
```

Make executable: `chmod +x ubb-ui/scripts/generate-api.sh`

- [ ] **Step 2: Add .gitignore for generated files**

Add to `ubb-ui/.gitignore`:
```
src/api/generated/*.ts
!src/api/generated/.gitkeep
```

- [ ] **Step 3: Create the API client with Clerk auth middleware**

```ts
// ubb-ui/src/api/client.ts
import createClient, { type Middleware } from "openapi-fetch";

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    // Clerk's useAuth().getToken() is async — we use the global Clerk instance
    const token = await window.Clerk?.session?.getToken();
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
};

function createApiClient<Paths extends {}>(basePath: string) {
  const client = createClient<Paths>({
    baseUrl: `${import.meta.env.VITE_API_URL || ""}${basePath}`,
  });
  client.use(authMiddleware);
  return client;
}

// These will use generated types once codegen runs.
// For now, export untyped clients that work at runtime.
export const platformApi = createApiClient("/api/v1/platform");
export const meteringApi = createApiClient("/api/v1/metering");
export const billingApi = createApiClient("/api/v1/billing");
export const tenantApi = createApiClient("/api/v1/tenant");
```

- [ ] **Step 4: Create an example query hook**

```ts
// ubb-ui/src/api/hooks/use-customers.ts
import { useQuery } from "@tanstack/react-query";
import { platformApi } from "../client";

export function useCustomers(params?: {
  status?: string;
  search?: string;
  cursor?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["customers", params],
    queryFn: async () => {
      const { data, error } = await platformApi.GET("/customers", {
        params: { query: params },
      });
      if (error) throw error;
      return data;
    },
  });
}

export function useCustomer(customerId: string) {
  return useQuery({
    queryKey: ["customers", customerId],
    queryFn: async () => {
      const { data, error } = await platformApi.GET("/customers/{customer_id}", {
        params: { path: { customer_id: customerId } },
      });
      if (error) throw error;
      return data;
    },
    enabled: !!customerId,
  });
}
```

- [ ] **Step 5: Add npm script**

Add to `ubb-ui/package.json` scripts:
```json
"api:generate": "bash scripts/generate-api.sh"
```

- [ ] **Step 6: Commit**

```bash
git add ubb-ui/scripts/ ubb-ui/src/api/ ubb-ui/package.json
git commit -m "feat: add API client layer with OpenAPI codegen and TanStack Query hooks"
```

---

### Task 10: Utility Functions

**Files:**
- Create: `ubb-ui/src/lib/format.ts`
- Create: `ubb-ui/src/lib/format.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// ubb-ui/src/lib/format.test.ts
import { describe, expect, it } from "vitest";
import { formatMicros, formatDate, formatRelativeDate } from "./format";

describe("formatMicros", () => {
  it("formats positive micros to dollars", () => {
    expect(formatMicros(1_500_000)).toBe("$1.50");
  });

  it("formats zero", () => {
    expect(formatMicros(0)).toBe("$0.00");
  });

  it("formats negative micros", () => {
    expect(formatMicros(-500_000)).toBe("-$0.50");
  });

  it("formats large amounts with commas", () => {
    expect(formatMicros(1_234_567_890_000)).toBe("$1,234,567.89");
  });
});

describe("formatDate", () => {
  it("formats ISO date string", () => {
    const result = formatDate("2026-03-13T10:30:00Z");
    expect(result).toContain("Mar");
    expect(result).toContain("13");
    expect(result).toContain("2026");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ubb-ui && pnpm vitest run src/lib/format.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the utilities**

```ts
// ubb-ui/src/lib/format.ts
/**
 * Format micros (1 USD = 1,000,000 micros) to a dollar string.
 */
export function formatMicros(micros: number, currency = "USD"): string {
  const dollars = micros / 1_000_000;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(dollars);
}

/**
 * Format an ISO date string to a human-readable date.
 */
export function formatDate(isoString: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(isoString));
}

/**
 * Format an ISO date string to a relative time (e.g., "2 hours ago").
 */
export function formatRelativeDate(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60_000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return formatDate(isoString);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ubb-ui && pnpm vitest run src/lib/format.test.ts`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add ubb-ui/src/lib/
git commit -m "feat: add currency and date formatting utilities"
```

---

## Chunk 3: Layout Shell & Core Pages

### Task 11: Layout Shell (Sidebar + Top Bar)

**Files:**
- Create: `ubb-ui/src/components/layout/app-sidebar.tsx`
- Create: `ubb-ui/src/components/layout/top-bar.tsx`
- Create: `ubb-ui/src/components/layout/nav-main.tsx`
- Modify: `ubb-ui/src/routes/_authenticated.tsx` (wrap with layout)

This task builds the dashboard shell using shadcn's sidebar component. Reference the shadcn-admin project for patterns.

- [ ] **Step 1: Create the navigation config**

```tsx
// ubb-ui/src/components/layout/nav-config.ts
import {
  LayoutDashboard,
  Users,
  Gauge,
  DollarSign,
  Settings,
  CreditCard,
  BarChart3,
  Search,
  Wallet,
  ArrowUpDown,
  FileText,
  ArrowUpCircle,
  Webhook,
  Link,
  UserPlus,
} from "lucide-react";

export const navConfig = [
  {
    title: "Dashboard",
    url: "/",
    icon: LayoutDashboard,
  },
  {
    title: "Customers",
    url: "/customers",
    icon: Users,
  },
  {
    title: "Metering",
    icon: Gauge,
    items: [
      { title: "Pricing", url: "/metering/pricing", icon: DollarSign },
      { title: "Usage Explorer", url: "/metering/usage", icon: Search },
      { title: "Analytics", url: "/metering/analytics", icon: BarChart3 },
    ],
  },
  {
    title: "Billing",
    icon: CreditCard,
    items: [
      { title: "Wallets", url: "/billing/wallets", icon: Wallet },
      { title: "Transactions", url: "/billing/transactions", icon: ArrowUpDown },
      { title: "Invoices", url: "/billing/invoices", icon: FileText },
      { title: "Top-Ups", url: "/billing/top-ups", icon: ArrowUpCircle },
    ],
  },
  {
    title: "Settings",
    icon: Settings,
    items: [
      { title: "General", url: "/settings/general", icon: Settings },
      { title: "Team", url: "/settings/team", icon: UserPlus },
      { title: "Webhooks", url: "/settings/webhooks", icon: Webhook },
      { title: "Stripe", url: "/settings/stripe", icon: Link },
    ],
  },
];
```

- [ ] **Step 2: Create the sidebar component**

```tsx
// ubb-ui/src/components/layout/app-sidebar.tsx
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar";
import { navConfig } from "./nav-config";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronRight } from "lucide-react";

export function AppSidebar() {
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  return (
    <Sidebar>
      <SidebarHeader className="border-b px-6 py-4">
        <span className="text-lg font-bold">UBB</span>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navConfig.map((item) =>
                item.items ? (
                  <Collapsible key={item.title} defaultOpen>
                    <SidebarMenuItem>
                      <CollapsibleTrigger asChild>
                        <SidebarMenuButton>
                          {item.icon && <item.icon className="size-4" />}
                          <span>{item.title}</span>
                          <ChevronRight className="ml-auto size-4 transition-transform group-data-[state=open]:rotate-90" />
                        </SidebarMenuButton>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <SidebarMenuSub>
                          {item.items.map((sub) => (
                            <SidebarMenuSubItem key={sub.url}>
                              <SidebarMenuSubButton
                                asChild
                                isActive={currentPath === sub.url}
                              >
                                <Link to={sub.url}>
                                  {sub.icon && <sub.icon className="size-4" />}
                                  <span>{sub.title}</span>
                                </Link>
                              </SidebarMenuSubButton>
                            </SidebarMenuSubItem>
                          ))}
                        </SidebarMenuSub>
                      </CollapsibleContent>
                    </SidebarMenuItem>
                  </Collapsible>
                ) : (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton asChild isActive={currentPath === item.url}>
                      <Link to={item.url}>
                        {item.icon && <item.icon className="size-4" />}
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
```

- [ ] **Step 3: Create the top bar**

```tsx
// ubb-ui/src/components/layout/top-bar.tsx
import { UserButton } from "@clerk/clerk-react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";

export function TopBar() {
  return (
    <header className="flex h-14 items-center gap-4 border-b px-6">
      <SidebarTrigger />
      <Separator orientation="vertical" className="h-6" />
      <div className="flex-1" />
      <UserButton afterSignOutUrl="/sign-in" />
    </header>
  );
}
```

- [ ] **Step 4: Update the authenticated layout**

```tsx
// ubb-ui/src/routes/_authenticated.tsx
import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { TopBar } from "@/components/layout/top-bar";

export const Route = createFileRoute("/_authenticated")({
  beforeLoad: ({ context }) => {
    if (!context.auth?.isSignedIn) {
      throw redirect({ to: "/sign-in" });
    }
  },
  component: AuthenticatedLayout,
});

function AuthenticatedLayout() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <TopBar />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
```

- [ ] **Step 5: Verify the layout renders**

Run: `cd ubb-ui && pnpm dev`
Expected: Sidebar with nav items, top bar with user button, content area

- [ ] **Step 6: Commit**

```bash
git add ubb-ui/src/components/layout/ ubb-ui/src/routes/_authenticated.tsx
git commit -m "feat: add dashboard layout shell with sidebar and top bar"
```

---

### Task 12: Dashboard Home Page

**Files:**
- Modify: `ubb-ui/src/routes/_authenticated/index.tsx`
- Create: `ubb-ui/src/components/dashboard/stats-cards.tsx`
- Create: `ubb-ui/src/components/dashboard/usage-chart.tsx`
- Create: `ubb-ui/src/api/hooks/use-dashboard.ts`

- [ ] **Step 1: Create dashboard API hooks**

```ts
// ubb-ui/src/api/hooks/use-dashboard.ts
import { useQuery } from "@tanstack/react-query";
import { meteringApi, billingApi, platformApi } from "../client";

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: async () => {
      // Fetch in parallel
      const [customersRes, walletsRes] = await Promise.all([
        platformApi.GET("/customers", {
          params: { query: { limit: 1 } },
        }),
        platformApi.GET("/wallets", {
          params: { query: { limit: 1 } },
        }),
      ]);
      return {
        customers: customersRes.data,
        wallets: walletsRes.data,
      };
    },
  });
}
```

- [ ] **Step 2: Create stats cards component**

```tsx
// ubb-ui/src/components/dashboard/stats-cards.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Users, Wallet, ArrowUpDown, TrendingUp } from "lucide-react";
import { formatMicros } from "@/lib/format";

interface StatsCardsProps {
  customerCount: number;
  totalBalance: number;
  transactionCount: number;
  revenueThisMonth: number;
}

export function StatsCards({
  customerCount,
  totalBalance,
  transactionCount,
  revenueThisMonth,
}: StatsCardsProps) {
  const stats = [
    {
      title: "Total Customers",
      value: customerCount.toLocaleString(),
      icon: Users,
    },
    {
      title: "Total Wallet Balance",
      value: formatMicros(totalBalance),
      icon: Wallet,
    },
    {
      title: "Transactions",
      value: transactionCount.toLocaleString(),
      icon: ArrowUpDown,
    },
    {
      title: "Revenue (This Month)",
      value: formatMicros(revenueThisMonth),
      icon: TrendingUp,
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat) => (
        <Card key={stat.title}>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {stat.title}
            </CardTitle>
            <stat.icon className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stat.value}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Build the dashboard home page**

```tsx
// ubb-ui/src/routes/_authenticated/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/_authenticated/")({
  component: DashboardHome,
});

function DashboardHome() {
  // TODO: Wire up useDashboardStats() once backend endpoints are ready.
  // For now, render with placeholder data.
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of your usage-based billing platform.
        </p>
      </div>
      <StatsCards
        customerCount={0}
        totalBalance={0}
        transactionCount={0}
        revenueThisMonth={0}
      />
    </div>
  );
}
```

- [ ] **Step 4: Verify the page renders**

Run: `cd ubb-ui && pnpm dev`
Expected: Dashboard with 4 stat cards showing zeros

- [ ] **Step 5: Commit**

```bash
git add ubb-ui/src/routes/_authenticated/index.tsx \
       ubb-ui/src/components/dashboard/ \
       ubb-ui/src/api/hooks/use-dashboard.ts
git commit -m "feat: add dashboard home page with stats cards"
```

---

### Task 13: Customer List Page

**Files:**
- Create: `ubb-ui/src/routes/_authenticated/customers/index.tsx`
- Create: `ubb-ui/src/components/customers/customers-table.tsx`
- Create: `ubb-ui/src/components/customers/columns.tsx`

- [ ] **Step 1: Create the table columns definition**

```tsx
// ubb-ui/src/components/customers/columns.tsx
import { type ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/format";
import { Link } from "@tanstack/react-router";

export type Customer = {
  id: string;
  external_id: string;
  status: string;
  stripe_customer_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export const columns: ColumnDef<Customer>[] = [
  {
    accessorKey: "external_id",
    header: "External ID",
    cell: ({ row }) => (
      <Link
        to="/customers/$customerId"
        params={{ customerId: row.original.id }}
        className="font-medium hover:underline"
      >
        {row.getValue("external_id")}
      </Link>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.getValue("status") as string;
      const variant =
        status === "active"
          ? "default"
          : status === "suspended"
            ? "secondary"
            : "destructive";
      return <Badge variant={variant}>{status}</Badge>;
    },
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => formatDate(row.getValue("created_at")),
  },
];
```

- [ ] **Step 2: Create the data table component**

```tsx
// ubb-ui/src/components/customers/customers-table.tsx
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { columns, type Customer } from "./columns";
import { Skeleton } from "@/components/ui/skeleton";

interface CustomersTableProps {
  data: Customer[];
  isLoading: boolean;
}

export function CustomersTable({ data, isLoading }: CustomersTableProps) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length ? (
            table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center">
                No customers found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 3: Create the customer list page**

```tsx
// ubb-ui/src/routes/_authenticated/customers/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { useCustomers } from "@/api/hooks/use-customers";
import { CustomersTable } from "@/components/customers/customers-table";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useState } from "react";

export const Route = createFileRoute("/_authenticated/customers/")({
  component: CustomersPage,
});

function CustomersPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string | undefined>();
  const { data, isLoading } = useCustomers({ search, status });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Customers</h1>
        <p className="text-muted-foreground">Manage your customers.</p>
      </div>
      <div className="flex items-center gap-4">
        <Input
          placeholder="Search by external ID..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Select
          value={status}
          onValueChange={(v) => setStatus(v === "all" ? undefined : v)}
        >
          <SelectTrigger className="w-40">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="suspended">Suspended</SelectItem>
            <SelectItem value="closed">Closed</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <CustomersTable data={data?.data ?? []} isLoading={isLoading} />
    </div>
  );
}
```

- [ ] **Step 4: Verify the page renders**

Run: `cd ubb-ui && pnpm dev`, navigate to `/customers`
Expected: Customers page with search input, status filter, and empty table

- [ ] **Step 5: Commit**

```bash
git add ubb-ui/src/routes/_authenticated/customers/ \
       ubb-ui/src/components/customers/
git commit -m "feat: add customer list page with search and filter"
```

---

### Task 14: Customer Detail Page

**Files:**
- Create: `ubb-ui/src/routes/_authenticated/customers/$customerId.tsx`
- Create: `ubb-ui/src/components/customers/customer-detail.tsx`

- [ ] **Step 1: Create the customer detail component**

```tsx
// ubb-ui/src/components/customers/customer-detail.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDate, formatMicros } from "@/lib/format";
import { Separator } from "@/components/ui/separator";

interface CustomerDetailProps {
  customer: {
    id: string;
    external_id: string;
    status: string;
    stripe_customer_id: string;
    metadata: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  };
}

export function CustomerDetail({ customer }: CustomerDetailProps) {
  const statusVariant =
    customer.status === "active"
      ? "default"
      : customer.status === "suspended"
        ? "secondary"
        : "destructive";

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex justify-between">
            <span className="text-muted-foreground">External ID</span>
            <span className="font-mono">{customer.external_id}</span>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Status</span>
            <Badge variant={statusVariant}>{customer.status}</Badge>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Created</span>
            <span>{formatDate(customer.created_at)}</span>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Stripe Customer</span>
            <span className="font-mono text-sm">
              {customer.stripe_customer_id || "—"}
            </span>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Metadata</CardTitle>
        </CardHeader>
        <CardContent>
          {Object.keys(customer.metadata).length > 0 ? (
            <pre className="rounded bg-muted p-4 text-sm">
              {JSON.stringify(customer.metadata, null, 2)}
            </pre>
          ) : (
            <p className="text-muted-foreground">No metadata.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Create the customer detail route**

```tsx
// ubb-ui/src/routes/_authenticated/customers/$customerId.tsx
import { createFileRoute } from "@tanstack/react-router";
import { useCustomer } from "@/api/hooks/use-customers";
import { CustomerDetail } from "@/components/customers/customer-detail";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { Link } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/customers/$customerId")({
  component: CustomerDetailPage,
});

function CustomerDetailPage() {
  const { customerId } = Route.useParams();
  const { data: customer, isLoading, isError } = useCustomer(customerId);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-6 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (isError || !customer) {
    return (
      <div className="space-y-4">
        <p className="text-destructive">Customer not found.</p>
        <Button variant="ghost" asChild>
          <Link to="/customers">
            <ArrowLeft className="mr-2 size-4" /> Back to customers
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/customers">
            <ArrowLeft className="size-4" />
          </Link>
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {customer.external_id}
          </h1>
          <p className="text-muted-foreground">Customer details</p>
        </div>
      </div>
      <CustomerDetail customer={customer} />
    </div>
  );
}
```

- [ ] **Step 3: Verify the page renders**

Run: `cd ubb-ui && pnpm dev`, navigate to `/customers/<any-id>`
Expected: Customer detail page with back button, details card, metadata card

- [ ] **Step 4: Commit**

```bash
git add ubb-ui/src/routes/_authenticated/customers/ \
       ubb-ui/src/components/customers/customer-detail.tsx
git commit -m "feat: add customer detail page"
```

---

## Chunk 4: Remaining Pages (Stubs)

For the remaining pages, we create route files with placeholder content. Each can be fleshed out iteratively once the core shell is working end-to-end.

### Task 15: Metering Page Stubs

**Files:**
- Create: `ubb-ui/src/routes/_authenticated/metering/pricing.tsx`
- Create: `ubb-ui/src/routes/_authenticated/metering/usage.tsx`
- Create: `ubb-ui/src/routes/_authenticated/metering/analytics.tsx`

- [ ] **Step 1: Create pricing page stub**

```tsx
// ubb-ui/src/routes/_authenticated/metering/pricing.tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/metering/pricing")({
  component: PricingPage,
});

function PricingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Pricing</h1>
        <p className="text-muted-foreground">
          Manage provider rates and markups.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Rate cards and markup management coming soon.
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create usage explorer page stub**

```tsx
// ubb-ui/src/routes/_authenticated/metering/usage.tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/metering/usage")({
  component: UsageExplorerPage,
});

function UsageExplorerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Usage Explorer</h1>
        <p className="text-muted-foreground">
          Query and visualize usage events.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Usage event explorer coming soon.
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create analytics page stub**

```tsx
// ubb-ui/src/routes/_authenticated/metering/analytics.tsx
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/metering/analytics")({
  component: AnalyticsPage,
});

function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground">
          Revenue breakdowns and usage trends.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Analytics dashboard coming soon.
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add ubb-ui/src/routes/_authenticated/metering/
git commit -m "feat: add metering page stubs (pricing, usage, analytics)"
```

---

### Task 16: Billing Page Stubs

**Files:**
- Create: `ubb-ui/src/routes/_authenticated/billing/wallets.tsx`
- Create: `ubb-ui/src/routes/_authenticated/billing/transactions.tsx`
- Create: `ubb-ui/src/routes/_authenticated/billing/invoices.tsx`
- Create: `ubb-ui/src/routes/_authenticated/billing/top-ups.tsx`

- [ ] **Step 1: Create all billing page stubs**

Follow the same pattern as Task 15. Each file exports a route with a heading, description, and "coming soon" dashed border placeholder.

Pages:
- **Wallets** — "Customer wallet balances and low-balance alerts."
- **Transactions** — "Filterable transaction log."
- **Invoices** — "Invoice list with status and detail views."
- **Top-Ups** — "Auto top-up configurations and attempt history."

- [ ] **Step 2: Commit**

```bash
git add ubb-ui/src/routes/_authenticated/billing/
git commit -m "feat: add billing page stubs (wallets, transactions, invoices, top-ups)"
```

---

### Task 17: Settings Page Stubs

**Files:**
- Create: `ubb-ui/src/routes/_authenticated/settings/general.tsx`
- Create: `ubb-ui/src/routes/_authenticated/settings/team.tsx`
- Create: `ubb-ui/src/routes/_authenticated/settings/webhooks.tsx`
- Create: `ubb-ui/src/routes/_authenticated/settings/stripe.tsx`

- [ ] **Step 1: Create all settings page stubs**

Same pattern. Pages:
- **General** — "Tenant name, API keys, and configuration."
- **Team** — "Manage team members and roles."
- **Webhooks** — "Configure webhook endpoints and view delivery logs."
- **Stripe** — "Stripe connection status and account linking."

- [ ] **Step 2: Commit**

```bash
git add ubb-ui/src/routes/_authenticated/settings/
git commit -m "feat: add settings page stubs (general, team, webhooks, stripe)"
```

---

### Task 18: Error Boundary & 404 Route

**Files:**
- Create: `ubb-ui/src/components/error-boundary.tsx`
- Modify: `ubb-ui/src/routes/__root.tsx` (add error boundary + 404)

- [ ] **Step 1: Create error boundary component**

```tsx
// ubb-ui/src/components/error-boundary.tsx
import { Button } from "@/components/ui/button";

interface ErrorFallbackProps {
  error: Error;
  reset: () => void;
}

export function ErrorFallback({ error, reset }: ErrorFallbackProps) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4">
      <h2 className="text-xl font-semibold">Something went wrong</h2>
      <p className="text-muted-foreground">{error.message}</p>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
```

- [ ] **Step 2: Update root route with 404 handler**

```tsx
// ubb-ui/src/routes/__root.tsx
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";
import type { useAuth } from "@clerk/clerk-react";
import { Button } from "@/components/ui/button";
import { Link } from "@tanstack/react-router";

interface RouterContext {
  auth: ReturnType<typeof useAuth>;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
  notFoundComponent: NotFound,
});

function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-4xl font-bold">404</h1>
      <p className="text-muted-foreground">Page not found.</p>
      <Button asChild>
        <Link to="/">Go home</Link>
      </Button>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add ubb-ui/src/components/error-boundary.tsx ubb-ui/src/routes/__root.tsx
git commit -m "feat: add error boundary and 404 page"
```

---

## Chunk 5: Final Integration & Polish

### Task 19: Dark Mode Support

**Files:**
- Create: `ubb-ui/src/hooks/use-theme.ts`
- Create: `ubb-ui/src/components/layout/theme-toggle.tsx`
- Modify: `ubb-ui/src/components/layout/top-bar.tsx` (add toggle)

- [ ] **Step 1: Create theme hook**

```ts
// ubb-ui/src/hooks/use-theme.ts
import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("ubb-theme") as Theme) || "system"
  );

  useEffect(() => {
    const root = document.documentElement;
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = theme === "dark" || (theme === "system" && systemDark);

    root.classList.toggle("dark", isDark);
    localStorage.setItem("ubb-theme", theme);
  }, [theme]);

  return { theme, setTheme };
}
```

- [ ] **Step 2: Create theme toggle component**

```tsx
// ubb-ui/src/components/layout/theme-toggle.tsx
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "@/hooks/use-theme";

export function ThemeToggle() {
  const { setTheme } = useTheme();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon">
          <Sun className="size-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute size-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          <span className="sr-only">Toggle theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTheme("light")}>Light</DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>Dark</DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>System</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 3: Add toggle to top bar**

In `ubb-ui/src/components/layout/top-bar.tsx`, add `<ThemeToggle />` next to `<UserButton />`:

```tsx
import { ThemeToggle } from "./theme-toggle";
// ...
<ThemeToggle />
<UserButton afterSignOutUrl="/sign-in" />
```

- [ ] **Step 4: Commit**

```bash
git add ubb-ui/src/hooks/use-theme.ts \
       ubb-ui/src/components/layout/theme-toggle.tsx \
       ubb-ui/src/components/layout/top-bar.tsx
git commit -m "feat: add dark mode support with theme toggle"
```

---

### Task 20: Build Verification & CI Script

**Files:**
- Modify: `ubb-ui/package.json` (verify all scripts work)

- [ ] **Step 1: Verify TypeScript compilation**

```bash
cd ubb-ui && pnpm tsc --noEmit
```
Expected: No errors

- [ ] **Step 2: Verify lint**

```bash
cd ubb-ui && pnpm lint
```
Expected: No errors (fix any that appear)

- [ ] **Step 3: Verify tests**

```bash
cd ubb-ui && pnpm vitest run
```
Expected: All tests pass

- [ ] **Step 4: Verify production build**

```bash
cd ubb-ui && pnpm build
ls -la dist/
```
Expected: `dist/` folder with `index.html`, `assets/` directory

- [ ] **Step 5: Verify preview server**

```bash
cd ubb-ui && pnpm preview
```
Expected: Preview server starts, serves built app

- [ ] **Step 6: Commit any fixes**

```bash
git add ubb-ui/
git commit -m "chore: verify build pipeline and fix any issues"
```

---

## Summary

This plan delivers a **working scaffold + partial backend expansion**, not a fully functional dashboard. The goal is to get the full architecture wired up end-to-end so that individual pages can be fleshed out iteratively.

| Chunk | Tasks | What it delivers |
|-------|-------|-----------------|
| 1: Backend Prerequisites | 1-5 | TenantUser model, ClerkJWTAuth (platform API only), auth boundary enforcement, customer CRUD endpoints, wallet list endpoint |
| 2: Frontend Scaffolding | 6-10 | Vite project, shadcn/ui, TanStack Router + Clerk auth, API client layer (untyped until codegen runs against live server), formatting utilities |
| 3: Layout & Core Pages | 11-14 | Dashboard shell (sidebar, top bar), home page (placeholder stats), customer list + detail pages (wired to real API) |
| 4: Remaining Pages | 15-18 | Stub pages for metering/billing/settings (placeholder content), error boundary, 404 |
| 5: Polish | 19-20 | Dark mode, build verification |

### What this plan does NOT deliver
- **Full type safety** — the OpenAPI codegen requires a running Django server. Generated types are gitignored. The typed client workflow is in place but not enforced in CI yet.
- **Dashboard read API for billing/metering data** — the plan only adds ClerkJWTAuth to the platform API. Metering/billing data visible in the dashboard will need a dedicated read-only `/api/v1/dashboard/` API (separate follow-up plan).
- **Fully functional pages** — most pages are stubs. Only the customer list/detail pages are wired to real data.
- **Clerk webhook for signup** — the tenant user provisioning via Clerk webhook needs a separate task.

### Next steps after this plan
1. Set up Clerk project and configure keys
2. Build `/api/v1/dashboard/` read-only API for billing/metering data (separate plan)
3. Flesh out stub pages with real data (one page at a time)
4. Add OpenAPI codegen to CI (generate types from a test server or committed schema snapshots)
5. Deploy to Cloudflare Pages
6. Configure production CORS on Django
7. Implement Clerk webhook for tenant user provisioning
