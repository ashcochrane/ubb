"""F4.4: outbound tenant-webhook payloads carry the tenant's mode."""
import json
from unittest.mock import MagicMock, patch

import pytest

from apps.platform.events.models import OutboxEvent
from apps.platform.events.webhook_models import TenantWebhookConfig
from apps.platform.events.webhooks import deliver_webhook
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox


def _capture_post():
    mock_response = MagicMock(status_code=200, text="OK")
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.post.return_value = mock_response
    return client


def _delivered_payload(client):
    call = client.post.call_args
    return json.loads(call.kwargs.get("content", call[1].get("content")))


@pytest.mark.django_db
@patch("apps.platform.events.webhooks.validate_webhook_url")
@patch("apps.platform.events.webhooks.httpx.Client")
def test_live_tenant_payload_has_livemode_true(mock_client_class, _validate):
    client = _capture_post()
    mock_client_class.return_value = client
    tenant = Tenant.objects.create(name="L", products=["metering"])
    TenantWebhookConfig.objects.create(
        tenant=tenant, url="https://example.com/hook", secret="s", event_types=["*"])
    event = OutboxEvent.objects.create(
        event_type="usage.recorded", payload={"x": 1}, tenant_id=str(tenant.id))

    deliver_webhook(event)

    payload = _delivered_payload(client)
    assert payload["livemode"] is True
    assert payload["event_type"] == "usage.recorded"


@pytest.mark.django_db
@patch("apps.platform.events.webhooks.validate_webhook_url")
@patch("apps.platform.events.webhooks.httpx.Client")
def test_sandbox_tenant_payload_has_livemode_false(mock_client_class, _validate):
    client = _capture_post()
    mock_client_class.return_value = client
    live = Tenant.objects.create(name="L", products=["metering"])
    sandbox = get_or_create_sandbox(live)
    TenantWebhookConfig.objects.create(
        tenant=sandbox, url="https://example.com/hook", secret="s", event_types=["*"])
    event = OutboxEvent.objects.create(
        event_type="sandbox.reset_completed", payload={}, tenant_id=str(sandbox.id))

    deliver_webhook(event)

    payload = _delivered_payload(client)
    assert payload["livemode"] is False


@pytest.mark.django_db
@patch("apps.platform.events.webhooks.validate_webhook_url")
@patch("apps.platform.events.webhooks.httpx.Client")
def test_signature_covers_the_livemode_field(mock_client_class, _validate):
    """The HMAC is computed over the exact bytes POSTed (livemode included)."""
    from apps.platform.events.webhooks import compute_signature

    client = _capture_post()
    mock_client_class.return_value = client
    tenant = Tenant.objects.create(name="L", products=["metering"])
    TenantWebhookConfig.objects.create(
        tenant=tenant, url="https://example.com/hook", secret="sig-secret", event_types=["*"])
    event = OutboxEvent.objects.create(
        event_type="usage.recorded", payload={}, tenant_id=str(tenant.id))

    deliver_webhook(event)

    call = client.post.call_args
    body = call.kwargs.get("content", call[1].get("content"))
    headers = call.kwargs.get("headers", call[1].get("headers"))
    assert headers["X-UBB-Signature"] == compute_signature(body, "sig-secret")
    assert json.loads(body)["livemode"] is True
