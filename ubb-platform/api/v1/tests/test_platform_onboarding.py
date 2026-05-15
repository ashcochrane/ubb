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


def _headers(h):
    return {"HTTP_" + k.upper().replace("-", "_"): v for k, v in h.items()}


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
        assert body["tenant"]["name"] == "Acme"

    def test_503_when_clerk_secret_missing(self, client, clerk_jwt, settings, monkeypatch):
        settings.CLERK_SECRET_KEY = ""
        # Do NOT mock get_clerk_user — let the real function run and raise
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
        tenant, _ = _tenant_with_user("user_rename")
        resp = client.patch(
            "/api/v1/platform/tenant",
            data='{"name": "NewName"}',
            content_type="application/json",
            **_headers(clerk_jwt("user_rename")),
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
