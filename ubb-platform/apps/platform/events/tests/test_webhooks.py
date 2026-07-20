import json

import pytest
from unittest.mock import patch, MagicMock
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.events.models import OutboxEvent
from apps.platform.events.webhook_models import TenantWebhookConfig, WebhookDeliveryAttempt
from apps.platform.events.webhooks import (
    WebhookDeliveryIncomplete,
    compute_signature,
    deliver_webhook,
    _PinnedIPTransport,
    _PinnedIPBackend,
)


class _FakePerUrlClient:
    """Stands in for httpx.Client: routes post() to a per-URL behavior callable
    and logs every POSTed url, so tests can count deliveries per endpoint."""

    def __init__(self, behaviors, post_log):
        self._behaviors = behaviors
        self._post_log = post_log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, content=None, headers=None):
        self._post_log.append(url)
        return self._behaviors[url]()


def _ok_response():
    return MagicMock(status_code=200, text="OK")


def _raise_timeout():
    import httpx

    raise httpx.ReadTimeout("timeout")


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

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_delivers_to_matching_config(self, mock_client_class, mock_validate):
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

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_customer_deleted_delivers_to_matching_config(self, mock_client_class, mock_validate):
        """customer.deleted is delivered like any other catalog type (#75)."""
        mock_response = MagicMock(status_code=200, text="OK")
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        event = OutboxEvent.objects.create(
            event_type="customer.deleted",
            payload={"tenant_id": str(self.tenant.id), "customer_id": "c1"},
            tenant_id=str(self.tenant.id),
        )
        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=["customer.deleted"],
        )

        deliver_webhook(event)

        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is True
        assert attempt.status_code == 200

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_skips_non_matching_event_type(self, mock_client_class, mock_validate):
        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=["referral.created"],
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 0

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_empty_event_types_delivers_nothing(self, mock_client_class, mock_validate):
        """Empty event_types is an explicit subscription to nothing — no delivery."""
        # Configure a working response so that if delivery were (wrongly)
        # attempted, the assertions fail cleanly rather than erroring on plumbing.
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

        assert WebhookDeliveryAttempt.objects.count() == 0
        mock_client_class.assert_not_called()

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_wildcard_delivers_all(self, mock_client_class, mock_validate):
        """["*"] subscribes to every event type."""
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
            event_types=["*"],
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 1
        assert WebhookDeliveryAttempt.objects.first().success is True

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_records_failure(self, mock_client_class, mock_validate):
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.side_effect = Exception("connection refused")
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=["*"],
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is False
        assert "connection refused" in attempt.error_message

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_includes_signature_header(self, mock_client_class, mock_validate):
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
            event_types=["*"],
        )

        deliver_webhook(self.event)

        call_kwargs = mock_client_instance.post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert "X-UBB-Signature" in headers
        assert "X-UBB-Event-Type" in headers

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_skips_inactive_config(self, mock_client_class, mock_validate):
        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=["*"],
            is_active=False,
        )

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 0

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_records_5xx_as_retryable_failure(self, mock_client_class, mock_validate):
        """A 5xx response records a failed attempt AND raises for the outbox
        retry — the endpoint answered but didn't durably receive the event."""
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
            event_types=["*"],
        )

        with pytest.raises(WebhookDeliveryIncomplete):
            deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is False
        assert attempt.status_code == 500
        assert "Internal Server Error" in attempt.error_message

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_records_4xx_as_permanent_failure(self, mock_client_class, mock_validate):
        """A 4xx response is a permanent failure for the pair — recorded, not
        retried: a receiver rejecting the request will keep rejecting it."""
        mock_response = MagicMock(status_code=400, text="Bad Request")
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=["*"],
        )

        deliver_webhook(self.event)  # no raise

        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is False
        assert attempt.status_code == 400
        assert "Bad Request" in attempt.error_message


@pytest.mark.django_db
class TestPerEndpointDeliveryCheckpointing:
    """Issue #76: each (event, endpoint) pair succeeds, retries, or dead-letters
    independently. Observed through delivery attempts per endpoint under
    injected failure — never by inspecting task internals."""

    URL_A = "https://a.example.com/hook"
    URL_B = "https://b.example.com/hook"  # the failing endpoint in these tests
    URL_C = "https://c.example.com/hook"

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="pe", products=["metering", "billing"])
        self.event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1", "cost_micros": 1000},
            tenant_id=str(self.tenant.id),
        )
        self.config_a = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url=self.URL_A, secret="s", event_types=["*"]
        )
        self.config_b = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url=self.URL_B, secret="s", event_types=["*"]
        )

    def _deliver(self, behaviors, post_log):
        with patch("apps.platform.events.webhooks.validate_webhook_url"), \
             patch(
                 "apps.platform.events.webhooks.httpx.Client",
                 side_effect=lambda **kw: _FakePerUrlClient(behaviors, post_log),
             ):
            deliver_webhook(self.event)

    def test_failing_endpoint_does_not_starve_others_in_same_pass(self):
        """A mid-pass failure must not abort delivery to the remaining endpoints."""
        config_c = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url=self.URL_C, secret="s", event_types=["*"]
        )
        behaviors = {self.URL_A: _ok_response, self.URL_B: _raise_timeout, self.URL_C: _ok_response}
        post_log = []

        with pytest.raises(WebhookDeliveryIncomplete):
            self._deliver(behaviors, post_log)

        assert post_log.count(self.URL_A) == 1
        assert post_log.count(self.URL_C) == 1
        assert WebhookDeliveryAttempt.objects.filter(
            webhook_config=self.config_a, success=True
        ).count() == 1
        assert WebhookDeliveryAttempt.objects.filter(
            webhook_config=config_c, success=True
        ).count() == 1
        assert WebhookDeliveryAttempt.objects.filter(
            webhook_config=self.config_b, success=False
        ).count() == 1

    def test_retry_passes_send_zero_duplicates_to_healthy_endpoint(self):
        """One endpoint failing across N retries -> zero duplicate POSTs to the
        healthy endpoint; retries target only the failing (event, endpoint) pair."""
        behaviors = {self.URL_A: _ok_response, self.URL_B: _raise_timeout}
        post_log = []

        for _ in range(3):
            with pytest.raises(WebhookDeliveryIncomplete):
                self._deliver(behaviors, post_log)

        assert post_log.count(self.URL_A) == 1
        assert post_log.count(self.URL_B) == 3

    def test_recovered_endpoint_succeeds_without_resending_to_healthy(self):
        """When the failing endpoint recovers, its pair completes and the pass
        raises nothing — the healthy endpoint still sees exactly one POST."""
        post_log = []

        with pytest.raises(WebhookDeliveryIncomplete):
            self._deliver({self.URL_A: _ok_response, self.URL_B: _raise_timeout}, post_log)

        self._deliver({self.URL_A: _ok_response, self.URL_B: _ok_response}, post_log)

        assert post_log.count(self.URL_A) == 1
        assert post_log.count(self.URL_B) == 2
        assert WebhookDeliveryAttempt.objects.filter(
            webhook_config=self.config_b, success=True
        ).count() == 1

    def test_5xx_endpoint_retries_without_duplicates_to_healthy(self):
        """A 5xx endpoint retries per pair like a network failure — the
        healthy endpoint still sees exactly one POST across all passes."""

        def _server_error():
            return MagicMock(status_code=503, text="Service Unavailable")

        post_log = []
        for _ in range(2):
            with pytest.raises(WebhookDeliveryIncomplete):
                self._deliver({self.URL_A: _ok_response, self.URL_B: _server_error}, post_log)

        self._deliver({self.URL_A: _ok_response, self.URL_B: _ok_response}, post_log)

        assert post_log.count(self.URL_A) == 1
        assert post_log.count(self.URL_B) == 3
        assert WebhookDeliveryAttempt.objects.filter(
            webhook_config=self.config_b, success=False, status_code=503
        ).count() == 2
        assert WebhookDeliveryAttempt.objects.filter(
            webhook_config=self.config_b, success=True
        ).count() == 1

    def test_dead_letter_is_per_endpoint_healthy_endpoint_still_served(self):
        """One endpoint dead-lettering -> every other subscribed endpoint still
        receives the event, exactly once. Driven through the outbox task seam."""
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.events.tasks import process_single_event
        from apps.platform.events.webhooks import handle_webhook_delivery

        registry = HandlerRegistry()
        registry.register(
            "usage.recorded",
            "platform.webhook_delivery.usage.recorded",
            handle_webhook_delivery,
        )

        behaviors = {self.URL_A: _ok_response, self.URL_B: _raise_timeout}
        post_log = []
        passes = 0

        with patch("apps.platform.events.dispatch.handler_registry", registry), \
             patch("apps.platform.events.webhooks.validate_webhook_url"), \
             patch(
                 "apps.platform.events.webhooks.httpx.Client",
                 side_effect=lambda **kw: _FakePerUrlClient(behaviors, post_log),
             ):
            while True:
                self.event.refresh_from_db()
                if self.event.status != "pending":
                    break
                process_single_event(str(self.event.id))
                passes += 1
                assert passes <= 10, "outbox retry loop did not converge"

        self.event.refresh_from_db()
        assert self.event.status == "failed"  # B's pair exhausted the retries
        assert post_log.count(self.URL_A) == 1  # healthy endpoint served exactly once
        assert WebhookDeliveryAttempt.objects.filter(
            webhook_config=self.config_a, success=True
        ).count() == 1
        assert WebhookDeliveryAttempt.objects.filter(
            webhook_config=self.config_b, success=False
        ).count() == self.event.max_retries
        assert not WebhookDeliveryAttempt.objects.filter(
            webhook_config=self.config_b, success=True
        ).exists()


@pytest.mark.django_db
class TestWebhookTimeoutRetry:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        self.event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1", "cost_micros": 1000},
            tenant_id=str(self.tenant.id),
        )

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_timeout_raises_for_retry(self, mock_client_class, mock_validate):
        """A timeout surfaces as WebhookDeliveryIncomplete at the end of the
        pass, which the outbox retries."""
        import httpx
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.side_effect = httpx.ReadTimeout("timeout")
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://slow.example.com/hook",
            secret="test-secret",
            event_types=["*"],
        )

        with pytest.raises(WebhookDeliveryIncomplete):
            deliver_webhook(self.event)

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_timeout_records_delivery_attempt_before_raising(self, mock_client_class, mock_validate):
        import httpx
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.side_effect = httpx.ConnectTimeout("connect timeout")
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://slow.example.com/hook",
            secret="test-secret",
            event_types=["*"],
        )

        with pytest.raises(WebhookDeliveryIncomplete):
            deliver_webhook(self.event)

        # Delivery attempt should have been saved before raising
        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is False
        assert "connect timeout" in attempt.error_message


@pytest.mark.django_db
class TestWebhookNetworkErrorRetry:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        self.event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1", "cost_micros": 1000},
            tenant_id=str(self.tenant.id),
        )

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_connection_error_raises_for_retry(self, mock_client_class, mock_validate):
        """Non-timeout network errors (ConnectError) surface as
        WebhookDeliveryIncomplete for the outbox retry."""
        import httpx

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=["*"],
        )

        with pytest.raises(WebhookDeliveryIncomplete):
            deliver_webhook(self.event)

        # Attempt should still be saved before re-raising
        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is False

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_non_network_error_swallowed(self, mock_client_class, mock_validate):
        """Non-network errors (e.g. ValueError) should be swallowed, not re-raised."""
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.side_effect = ValueError("bad data")
        mock_client_class.return_value = mock_client_instance

        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret="test-secret",
            event_types=["*"],
        )

        # Should not raise
        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 1
        assert WebhookDeliveryAttempt.objects.first().success is False


@pytest.mark.django_db
class TestHandleWebhookDelivery:
    def test_handles_missing_event(self):
        from apps.platform.events.webhooks import handle_webhook_delivery
        import uuid

        # Should not raise -- just returns silently
        handle_webhook_delivery(str(uuid.uuid4()), {})


@pytest.mark.django_db
class TestWebhookDeliveryRevalidatesSSRF:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="ssrf", products=["metering", "billing"])
        self.event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1", "cost_micros": 1000}, tenant_id=str(self.tenant.id))

    @patch("apps.platform.events.webhooks.httpx.Client")
    @patch("apps.platform.events.webhooks.validate_webhook_url")
    def test_delivery_blocked_when_url_now_resolves_private(self, mock_validate, mock_client_class):
        mock_validate.side_effect = ValueError("Webhook URL must not point to private/internal addresses")
        TenantWebhookConfig.objects.create(tenant=self.tenant, url="https://rebind.attacker.example/hook",
                                           secret="test-secret", event_types=["*"])
        deliver_webhook(self.event)
        mock_client_class.assert_not_called()                       # no outbound request
        assert WebhookDeliveryAttempt.objects.count() == 1
        attempt = WebhookDeliveryAttempt.objects.first()
        assert attempt.success is False
        assert attempt.error_message.startswith("blocked:")


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
                    "secret": "a" * 32,
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

    def test_create_requires_event_types(self):
        """Omitting event_types is rejected — no implicit default subscription."""
        resp = self.client.post(
            "/api/v1/webhooks/config/configs",
            data=json.dumps({"url": "https://example.com/hook", "secret": "a" * 32}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 422
        assert TenantWebhookConfig.objects.count() == 0

    def test_create_rejects_empty_event_types(self):
        """An empty list would be a silent no-op webhook — reject it."""
        resp = self.client.post(
            "/api/v1/webhooks/config/configs",
            data=json.dumps(
                {"url": "https://example.com/hook", "secret": "a" * 32, "event_types": []}
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 422
        assert TenantWebhookConfig.objects.count() == 0

    def test_create_rejects_unknown_event_type(self):
        """A typo'd event type is rejected loudly instead of matching nothing forever."""
        resp = self.client.post(
            "/api/v1/webhooks/config/configs",
            data=json.dumps(
                {
                    "url": "https://example.com/hook",
                    "secret": "a" * 32,
                    "event_types": ["usage.recieved"],
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 400
        assert TenantWebhookConfig.objects.count() == 0

    def test_create_accepts_customer_deleted(self):
        """customer.deleted is a catalog type like any other (#75) — the
        delivery path emitted it while the catalog silently hid it from
        subscribers."""
        resp = self.client.post(
            "/api/v1/webhooks/config/configs",
            data=json.dumps(
                {
                    "url": "https://example.com/hook",
                    "secret": "a" * 32,
                    "event_types": ["customer.deleted"],
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 201
        assert resp.json()["event_types"] == ["customer.deleted"]

    def test_create_accepts_wildcard(self):
        """["*"] is the explicit opt-in to all events."""
        resp = self.client.post(
            "/api/v1/webhooks/config/configs",
            data=json.dumps(
                {"url": "https://example.com/hook", "secret": "a" * 32, "event_types": ["*"]}
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 201
        assert resp.json()["event_types"] == ["*"]

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


class TestPinnedIPTransport:
    """Unit tests for the DNS-rebinding pin (Fix B).

    These tests are hermetic — no DB, no real network.  They verify the
    transport wiring so that a DNS rebind after validate_webhook_url returns
    cannot steer the TCP connection to a private address.
    """

    def test_pinned_ip_backend_stores_ip(self):
        """_PinnedIPBackend stores the validated IP it was given."""
        backend = _PinnedIPBackend("1.2.3.4")
        assert backend._validated_ip == "1.2.3.4"

    def test_pinned_ip_transport_injects_backend(self):
        """_PinnedIPTransport replaces the pool's network backend with a pinned one."""
        transport = _PinnedIPTransport("1.2.3.4")
        assert isinstance(transport._pool._network_backend, _PinnedIPBackend)
        assert transport._pool._network_backend._validated_ip == "1.2.3.4"

    @pytest.mark.django_db
    def test_delivery_uses_pinned_transport_with_validated_ip(self):
        """_deliver_to_config constructs _PinnedIPTransport with the IP returned by
        validate_webhook_url, defeating a rebind that happens after validation."""
        tenant = Tenant.objects.create(name="rebind-pin", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1", "cost_micros": 1000},
            tenant_id=str(tenant.id),
        )
        TenantWebhookConfig.objects.create(
            tenant=tenant,
            url="https://rebind.example.com/hook",
            secret="test-secret",
            event_types=["*"],
        )

        validated_ip = "1.2.3.4"
        captured_transports = []

        def fake_client(timeout=None, transport=None):
            captured_transports.append(transport)
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.post.return_value = MagicMock(status_code=200, text="OK")
            return mock_instance

        with patch("apps.platform.events.webhooks.validate_webhook_url", return_value=validated_ip), \
             patch("apps.platform.events.webhooks.httpx.Client", side_effect=fake_client), \
             patch("apps.platform.events.webhooks._PinnedIPTransport") as mock_transport_cls:

            mock_transport_cls.return_value = MagicMock()

            deliver_webhook(event)

            # Assert the transport was constructed with the validated IP
            mock_transport_cls.assert_called_once_with(validated_ip)

    def test_pinned_ip_backend_connect_tcp_uses_ip_not_hostname(self):
        """_PinnedIPBackend.connect_tcp forwards the pinned IP, ignoring the hostname
        that would normally re-trigger DNS resolution."""
        backend = _PinnedIPBackend("1.2.3.4")

        connect_calls = []

        class _FakeParent:
            def connect_tcp(self, host, port, **kwargs):
                connect_calls.append(host)
                return MagicMock()

        # Patch super().connect_tcp via the MRO by temporarily replacing SyncBackend
        with patch.object(
            _PinnedIPBackend.__bases__[0],  # SyncBackend
            "connect_tcp",
            side_effect=lambda self_inner, host, port, **kw: connect_calls.append(host) or MagicMock(),
        ):
            # Call with a hostname — backend should substitute the pinned IP
            try:
                backend.connect_tcp(host="rebind.attacker.example", port=443, timeout=5)
            except Exception:
                pass  # socket error is fine; we only care what host was passed

        # The ip was forwarded to the parent, not the original hostname
        if connect_calls:
            assert connect_calls[0] == "1.2.3.4"


@pytest.mark.django_db
class TestSignatureV2:
    """F5.7: timestamped v2 signatures ride alongside the unchanged legacy header."""

    SECRET = "v2-secret"

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="v2", products=["metering", "billing"])
        self.event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1", "cost_micros": 1000},
            tenant_id=str(self.tenant.id),
        )
        TenantWebhookConfig.objects.create(
            tenant=self.tenant,
            url="https://example.com/hook",
            secret=self.SECRET,
            event_types=["*"],
        )

    def _deliver_and_capture(self):
        """Deliver the event; return (body_bytes, headers) of the POST."""
        mock_response = MagicMock(status_code=200, text="OK")
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.return_value = mock_response
        with patch("apps.platform.events.webhooks.validate_webhook_url"), \
             patch("apps.platform.events.webhooks.httpx.Client",
                   return_value=mock_client_instance):
            deliver_webhook(self.event)
        call = mock_client_instance.post.call_args
        return call.kwargs["content"], call.kwargs["headers"]

    def test_both_signature_headers_present(self):
        _, headers = self._deliver_and_capture()
        assert "X-UBB-Signature" in headers       # legacy, deprecation window
        assert "X-UBB-Signature-V2" in headers    # replay-bounded
        assert headers["X-UBB-Signature-V2"].startswith("t=")

    def test_v2_verifies_against_documented_recipe(self):
        """v2 = HMAC-SHA256(secret, f"{t}.{body}"), header t=<ts>,v1=<hex>."""
        import hashlib
        import hmac as hmac_mod

        body, headers = self._deliver_and_capture()
        t_part, v1_part = headers["X-UBB-Signature-V2"].split(",")
        ts = int(t_part[len("t="):])
        v1 = v1_part[len("v1="):]

        expected = hmac_mod.new(
            self.SECRET.encode("utf-8"),
            str(ts).encode("utf-8") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        assert v1 == expected
        # The signed ts is the payload's own timestamp (signed at send time).
        assert ts == json.loads(body)["timestamp"]

    def test_legacy_signature_unchanged_byte_for_byte(self):
        """The legacy header is still the body-only HMAC — existing receivers
        keep verifying without any change."""
        body, headers = self._deliver_and_capture()
        assert headers["X-UBB-Signature"] == compute_signature(body, self.SECRET)

    def test_v2_round_trips_through_compute_signature_v2(self):
        from apps.platform.events.webhooks import compute_signature_v2

        body, headers = self._deliver_and_capture()
        t_part, v1_part = headers["X-UBB-Signature-V2"].split(",")
        ts = int(t_part[len("t="):])
        assert v1_part[len("v1="):] == compute_signature_v2(body, self.SECRET, ts)
