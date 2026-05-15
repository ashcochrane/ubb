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
    assert raw_key2 is None


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
    events = OutboxEvent.objects.filter(event_type="tenant.provisioned")
    assert events.count() == 1
    evt = events.first()
    assert evt.payload["tenant_id"] == str(tenant.id)
    assert evt.payload["clerk_user_id"] == CLERK_USER
    assert evt.payload["mode"] == "track"


def test_idempotent_replay_does_not_emit_new_event(db, mock_clerk):
    provision_tenant_for_clerk_user(clerk_user_id=CLERK_USER, tenant_name="Acme")
    provision_tenant_for_clerk_user(clerk_user_id=CLERK_USER, tenant_name="Acme")
    assert OutboxEvent.objects.filter(event_type="tenant.provisioned").count() == 1
