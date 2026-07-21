"""Issue #83: two-secret overlap rotation.

The seam is deliberately small: the config owns "which secrets sign a delivery
right now" (``signing_secrets``) and "stage a rotation" (``apply_secret_rotation``);
the delivery path signs once per secret, emitting a ``v1=`` candidate each. The
shipped SDK verifier already accepts any candidate, so a receiver mid-cutover
verifies with no code change — proven here against the *real* verifier.
"""
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from unittest.mock import MagicMock, patch

from ubb.exceptions import UBBWebhookVerificationError
from ubb.webhooks import verify_webhook

from apps.platform.events.models import OutboxEvent
from apps.platform.events.webhook_models import TenantWebhookConfig
from apps.platform.events.webhooks import deliver_webhook
from apps.platform.tenants.models import Tenant

# A fixed instant far from any clock so window comparisons are unambiguous.
_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt_timezone.utc)


class TestSigningSecrets:
    """The delivery-time read: current secret always, retiring one only while
    its overlap window is open. Pure in-memory — no DB, no clock."""

    def test_no_retiring_secret_signs_with_current_only(self):
        config = TenantWebhookConfig(secret="current")
        assert config.signing_secrets(now=_T0) == ["current"]

    def test_open_window_signs_with_both_current_first(self):
        config = TenantWebhookConfig(
            secret="new", retiring_secret="old",
            retiring_secret_expires_at=_T0 + timedelta(hours=1))
        assert config.signing_secrets(now=_T0) == ["new", "old"]

    def test_expired_window_drops_the_retiring_secret(self):
        config = TenantWebhookConfig(
            secret="new", retiring_secret="old",
            retiring_secret_expires_at=_T0 - timedelta(seconds=1))
        assert config.signing_secrets(now=_T0) == ["new"]

    def test_boundary_is_exclusive_at_expiry(self):
        """At the exact expiry instant the retiring secret is already gone."""
        config = TenantWebhookConfig(
            secret="new", retiring_secret="old", retiring_secret_expires_at=_T0)
        assert config.signing_secrets(now=_T0) == ["new"]

    def test_empty_retiring_secret_is_ignored_even_with_expiry(self):
        config = TenantWebhookConfig(
            secret="new", retiring_secret="",
            retiring_secret_expires_at=_T0 + timedelta(hours=1))
        assert config.signing_secrets(now=_T0) == ["new"]


class TestApplySecretRotation:
    """Staging a rotation: current -> retiring (for the overlap), new -> current.
    Rotating again keeps only ONE retiring secret — the just-superseded one."""

    def test_current_becomes_retiring_and_new_becomes_current(self):
        config = TenantWebhookConfig(secret="A")
        config.apply_secret_rotation("B", overlap=timedelta(hours=24), now=_T0)
        assert config.secret == "B"
        assert config.retiring_secret == "A"
        assert config.retiring_secret_expires_at == _T0 + timedelta(hours=24)

    def test_rotate_again_mid_window_replaces_the_retiring_secret(self):
        config = TenantWebhookConfig(secret="A")
        config.apply_secret_rotation("B", overlap=timedelta(hours=24), now=_T0)
        # Second rotation 12h later, while A's window is still open.
        config.apply_secret_rotation(
            "C", overlap=timedelta(hours=24), now=_T0 + timedelta(hours=12))
        assert config.secret == "C"
        assert config.retiring_secret == "B"          # A is dropped
        # During the new window only B and C sign — never A again.
        assert config.signing_secrets(now=_T0 + timedelta(hours=13)) == ["C", "B"]


@pytest.mark.django_db
class TestRotationDelivery:
    """The end-to-end proof: what the receiver actually gets on the wire, and
    that the shipped SDK verifier accepts the right secrets at each phase."""

    OLD = "old-secret-" + "o" * 24
    NEW = "new-secret-" + "n" * 24

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="rot", products=["metering"])
        self.event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1", "cost_micros": 1000},
            tenant_id=str(self.tenant.id))
        self.config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/hook",
            secret=self.OLD, event_types=["*"])

    def _deliver_and_capture(self):
        """Deliver the event once; return (raw_body_bytes, headers)."""
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.post.return_value = MagicMock(status_code=200, text="OK")
        with patch("apps.platform.events.webhooks.validate_webhook_url"), \
             patch("apps.platform.events.webhooks.httpx.Client",
                   return_value=mock_instance):
            deliver_webhook(self.event)
        # Fresh event each call so the per-endpoint checkpoint never skips.
        call = mock_instance.post.call_args
        return call.kwargs["content"], call.kwargs["headers"]

    def _fresh_event(self):
        self.event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1", "cost_micros": 1000},
            tenant_id=str(self.tenant.id))

    def test_before_rotation_only_current_secret_verifies(self):
        body, headers = self._deliver_and_capture()
        v2 = headers["X-UBB-Signature-V2"]
        assert v2.count("v1=") == 1
        assert verify_webhook(body, v2, self.OLD)  # shipped verifier, unmodified

    def test_during_window_both_old_and_new_secrets_verify(self):
        self.config.apply_secret_rotation(self.NEW, overlap=timedelta(hours=24))
        self.config.save()
        body, headers = self._deliver_and_capture()
        v2 = headers["X-UBB-Signature-V2"]

        # Two candidates on the wire — the existing header, no new field.
        assert v2.count("v1=") == 2
        # A receiver still on the OLD secret verifies; one that has cut over to
        # the NEW secret verifies — both against the SHIPPED verifier unchanged.
        assert verify_webhook(body, v2, self.OLD)
        assert verify_webhook(body, v2, self.NEW)

    def test_after_expiry_only_new_secret_verifies(self):
        self.config.apply_secret_rotation(self.NEW, overlap=timedelta(hours=24))
        # Force the window closed.
        self.config.retiring_secret_expires_at = _T0 - timedelta(days=1)
        self.config.save()
        body, headers = self._deliver_and_capture()
        v2 = headers["X-UBB-Signature-V2"]

        assert v2.count("v1=") == 1
        assert verify_webhook(body, v2, self.NEW)
        with pytest.raises(UBBWebhookVerificationError):
            verify_webhook(body, v2, self.OLD)

    def test_legacy_header_tracks_the_current_secret_only(self):
        """The legacy body-only header can't carry candidates; it signs with
        the active secret so a not-yet-migrated receiver follows the cutover."""
        import hashlib
        import hmac as hmac_mod

        self.config.apply_secret_rotation(self.NEW, overlap=timedelta(hours=24))
        self.config.save()
        body, headers = self._deliver_and_capture()
        expected_new = hmac_mod.new(
            self.NEW.encode(), body, hashlib.sha256).hexdigest()
        assert headers["X-UBB-Signature"] == expected_new
