import json

import pytest
from unittest.mock import patch, MagicMock
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.events.models import OutboxEvent
from apps.platform.events.webhook_models import TenantWebhookConfig, WebhookDeliveryAttempt
from apps.platform.events.webhooks import compute_signature, deliver_webhook


@pytest.mark.django_db
class TestComputeSignature:
    def test_produces_hex_digest(self):
        sig = compute_signature(b'{"test": true}', "my-secret")
        assert len(sig) == 64  # SHA-256 hex digest

    def test_deterministic(self):
        payload = b'{"key": "value"}'
        sig1 = compute_signature(payload, "secret")
        sig2 = compute_signature(payload, "secret")
        assert sig1 == sig2

    def test_different_secrets_different_sigs(self):
        payload = b'{"key": "value"}'
        sig1 = compute_signature(payload, "secret1")
        sig2 = compute_signature(payload, "secret2")
        assert sig1 != sig2


@pytest.mark.django_db
class TestDeliverWebhook:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        self.event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1", "cost_micros": 1000},
            tenant_id=str(self.tenant.id),
        )

    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_delivers_to_matching_config(self, mock_client_class):
        mock_response = MagicMock(status_code=200, text="OK")
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=["usage.recorded"],
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is True
        assert attempt.status_code == 200

    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_skips_non_matching_event_type(self, mock_client_class):
        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=["referral.created"],
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 0

    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_delivers_when_event_types_empty(self, mock_client_class):
        """Empty event_types means deliver all events."""
        mock_response = MagicMock(status_code=200, text="OK")
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=[],
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 1
        assert WebhookDeliveryAttempt.objects.first().success is True

    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_records_failure(self, mock_client_class):
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.side_effect = Exception("connection refused")
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=[],
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is False
        assert "connection refused" in attempt.error_message

    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_includes_signature_header(self, mock_client_class):
        mock_response = MagicMock(status_code=200, text="OK")
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="my-secret",
            event_types=[],
        )

        deliver_webhook(self.event)

        call_kwargs = mock_client_instance.post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert "X-UBB-Signature" in headers
        assert "X-UBB-Event-Type" in headers

    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_skips_inactive_config(self, mock_client_class):
        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=[],
            is_active=False,
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 0

    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_records_non_2xx_as_failure(self, mock_client_class):
        mock_response = MagicMock(status_code=500, text="Internal Server Error")
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=[],
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is False
        assert attempt.status_code == 500
        assert "Internal Server Error" in attempt.error_message


@pytest.mark.django_db
class TestHandleWebhookDelivery:
    def test_handles_missing_event(self):
        from apps.platform.events.webhooks import handle_webhook_delivery
        import uuid

        # Should not raise -- just returns silently
        handle_webhook_delivery(str(uuid.uuid4()), {})


@pytest.mark.django_db
class TestWebhookConfigAPI:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="test", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def test_create_webhook_config(self):
        resp = self.client.post(
            "/api/v1/webhooks/config/configs",
            data=json.dumps(
                {
                    "url": "https://example.com/hook",
                    "secret": "my-secret",
                    "event_types": ["usage.recorded"],
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://example.com/hook"
        assert data["is_active"] is True
        assert data["event_types"] == ["usage.recorded"]

    def test_list_webhook_configs(self):
        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://a.com/hook",
            secret="s1",
        )
        resp = self.client.get(
            "/api/v1/webhooks/config/configs",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_delete_webhook_config(self):
        config = TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://a.com/hook",
            secret="s1",
        )
        resp = self.client.delete(
            f"/api/v1/webhooks/config/configs/{config.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        assert TenantWebhookConfig.objects.count() == 0

    def test_cannot_delete_other_tenants_config(self):
        other_tenant = Tenant.objects.create(name="other", products=["metering"])
        config = TenantWebhookConfig.objects.create(
            tenant=other_tenant,
            url="https://a.com/hook",
            secret="s1",
        )
        resp = self.client.delete(
            f"/api/v1/webhooks/config/configs/{config.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 404
        assert TenantWebhookConfig.objects.count() == 1
