"""Issue #83: the webhook lifecycle HTTP surface — PATCH edit/pause, secret
rotation, and the delivery-history read. Exercised through the real API (auth,
role floors, problem+json, audit) exactly as a tenant admin would."""
import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.platform.audit.models import AuditRecord
from apps.platform.events.models import OutboxEvent
from apps.platform.events.webhook_models import (
    TenantWebhookConfig,
    WebhookDeliveryAttempt,
)
from apps.platform.tenants.models import Tenant, TenantApiKey

SECRET_A = "a" * 32
SECRET_B = "b" * 40


@pytest.mark.django_db
class TestWebhookConfigPatch:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="patch", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        self.config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/hook",
            secret=SECRET_A, event_types=["usage.recorded"], is_active=True)

    def _patch(self, body):
        return self.client.patch(
            f"/api/v1/webhooks/configs/{self.config.id}",
            data=json.dumps(body), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_edits_url_without_delete_and_recreate(self):
        resp = self._patch({"url": "https://example.com/hook2"})
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://example.com/hook2"
        self.config.refresh_from_db()
        assert self.config.url == "https://example.com/hook2"

    def test_edits_event_types(self):
        resp = self._patch({"event_types": ["*"]})
        assert resp.status_code == 200
        assert resp.json()["event_types"] == ["*"]

    def test_pauses_and_resumes(self):
        assert self._patch({"is_active": False}).json()["is_active"] is False
        self.config.refresh_from_db()
        assert self.config.is_active is False
        assert self._patch({"is_active": True}).json()["is_active"] is True

    def test_partial_update_leaves_other_fields_intact(self):
        resp = self._patch({"is_active": False})
        assert resp.status_code == 200
        self.config.refresh_from_db()
        assert self.config.url == "https://example.com/hook"          # untouched
        assert self.config.event_types == ["usage.recorded"]          # untouched

    def test_secret_is_untouchable_via_patch(self):
        """A `secret` in the PATCH body is ignored — rotation is the only path."""
        resp = self._patch({"secret": "z" * 40, "is_active": False})
        assert resp.status_code == 200
        self.config.refresh_from_db()
        assert self.config.secret == SECRET_A                         # unchanged
        # And never leaked in the response body either.
        assert "secret" not in resp.json()

    def test_url_collision_is_conflict(self):
        # Same host (resolves through the real SSRF guard), different path so
        # it's a distinct (tenant, url) — the collision the PATCH must catch.
        TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/taken",
            secret=SECRET_A, event_types=["*"])
        resp = self._patch({"url": "https://example.com/taken"})
        assert resp.status_code == 409
        assert resp["Content-Type"] == "application/problem+json"
        assert resp.json()["code"] == "conflict"

    def test_patching_url_to_its_current_value_is_not_a_conflict(self):
        resp = self._patch({"url": "https://example.com/hook", "is_active": False})
        assert resp.status_code == 200

    def test_non_https_url_is_validation_error(self):
        resp = self._patch({"url": "http://example.com/hook"})
        assert resp.status_code == 422
        assert resp.json()["code"] == "validation_error"

    def test_unknown_event_type_is_validation_error(self):
        resp = self._patch({"event_types": ["usage.recieved"]})
        assert resp.status_code == 422
        assert resp.json()["code"] == "validation_error"
        assert "usage.recieved" in resp.json()["detail"]

    def test_empty_event_types_is_validation_error(self):
        resp = self._patch({"event_types": []})
        assert resp.status_code == 422
        assert resp.json()["code"] == "validation_error"

    def test_cannot_patch_other_tenants_config(self):
        other = Tenant.objects.create(name="other", products=["metering"])
        cfg = TenantWebhookConfig.objects.create(
            tenant=other, url="https://o.example.com/hook",
            secret=SECRET_A, event_types=["*"])
        resp = self.client.patch(
            f"/api/v1/webhooks/configs/{cfg.id}",
            data=json.dumps({"is_active": False}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 404
        cfg.refresh_from_db()
        assert cfg.is_active is True

    def test_edit_records_audit(self):
        self._patch({"is_active": False})
        rec = AuditRecord.objects.get(action="webhook_config.updated")
        assert rec.tenant_id == self.tenant.id
        assert str(rec.resource_id) == str(self.config.id)


@pytest.mark.django_db
class TestWebhookSecretRotation:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="rotapi", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        self.config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/hook",
            secret=SECRET_A, event_types=["*"])

    def _rotate(self, body):
        return self.client.post(
            f"/api/v1/webhooks/configs/{self.config.id}/rotate-secret",
            data=json.dumps(body), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_rotation_sets_new_secret_and_retires_the_old(self):
        before = timezone.now()
        resp = self._rotate({"new_secret": SECRET_B})
        assert resp.status_code == 200
        self.config.refresh_from_db()
        assert self.config.secret == SECRET_B
        assert self.config.retiring_secret == SECRET_A
        # Default overlap ~24h.
        assert self.config.retiring_secret_expires_at > before + timedelta(hours=23)
        assert self.config.retiring_secret_expires_at < before + timedelta(hours=25)
        # The response advertises the window close (but never the secret).
        assert resp.json()["retiring_secret_expires_at"] is not None
        assert "secret" not in resp.json()

    def test_overlap_hours_override(self):
        before = timezone.now()
        self._rotate({"new_secret": SECRET_B, "overlap_hours": 1})
        self.config.refresh_from_db()
        assert self.config.retiring_secret_expires_at < before + timedelta(hours=2)

    def test_rotate_again_replaces_the_retiring_secret(self):
        self._rotate({"new_secret": SECRET_B})
        self._rotate({"new_secret": "c" * 36})
        self.config.refresh_from_db()
        assert self.config.secret == "c" * 36
        assert self.config.retiring_secret == SECRET_B      # A dropped, not A

    def test_short_secret_is_rejected(self):
        resp = self._rotate({"new_secret": "tooshort"})
        assert resp.status_code == 422
        self.config.refresh_from_db()
        assert self.config.secret == SECRET_A

    def test_rotating_to_the_same_secret_is_rejected(self):
        resp = self._rotate({"new_secret": SECRET_A})
        assert resp.status_code == 422
        assert resp.json()["code"] == "validation_error"

    def test_cannot_rotate_other_tenants_config(self):
        other = Tenant.objects.create(name="other-rot", products=["metering"])
        cfg = TenantWebhookConfig.objects.create(
            tenant=other, url="https://o.example.com/hook", secret=SECRET_A)
        resp = self.client.post(
            f"/api/v1/webhooks/configs/{cfg.id}/rotate-secret",
            data=json.dumps({"new_secret": SECRET_B}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 404

    def test_rotation_records_audit_without_the_secret(self):
        self._rotate({"new_secret": SECRET_B})
        rec = AuditRecord.objects.get(action="webhook_config.secret_rotated")
        assert str(rec.resource_id) == str(self.config.id)
        # The secret material must never reach the permanent ledger (ADR-004 §4).
        blob = json.dumps(rec.metadata)
        assert SECRET_A not in blob
        assert SECRET_B not in blob


@pytest.mark.django_db
class TestWebhookDeliveryHistory:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="hist", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        self.config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/hook",
            secret=SECRET_A, event_types=["*"])
        self.event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "c1"}, tenant_id=str(self.tenant.id))

    def _attempt(self, *, success, status_code=None, error="", minutes_ago=0):
        a = WebhookDeliveryAttempt.objects.create(
            webhook_config=self.config, outbox_event=self.event,
            success=success, status_code=status_code, error_message=error)
        if minutes_ago:
            WebhookDeliveryAttempt.objects.filter(id=a.id).update(
                created_at=timezone.now() - timedelta(minutes=minutes_ago))
        return a

    def _get(self, qs=""):
        return self.client.get(
            f"/api/v1/webhooks/configs/{self.config.id}/deliveries{qs}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_lists_attempts_in_the_cursor_envelope(self):
        self._attempt(success=True, status_code=200)
        resp = self._get()
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"data", "next_cursor", "has_more"}
        row = body["data"][0]
        assert row["success"] is True
        assert row["status_code"] == 200
        assert row["event_id"] == str(self.event.id)
        assert row["event_type"] == "usage.recorded"

    def test_includes_retries_and_dead_letters(self):
        """Every attempt row shows — successes, retryable 5xx, and the final
        permanent failure — as the per-endpoint checkpointing fix records them."""
        self._attempt(success=False, status_code=503, error="Service Unavailable")
        self._attempt(success=False, status_code=503, error="Service Unavailable")
        self._attempt(success=False, status_code=500, error="dead")
        resp = self._get()
        rows = resp.json()["data"]
        assert len(rows) == 3
        assert all(r["success"] is False for r in rows)
        assert {r["status_code"] for r in rows} == {500, 503}

    def test_pagination_walks_newest_first(self):
        a_old = self._attempt(success=True, status_code=200, minutes_ago=10)
        a_new = self._attempt(success=True, status_code=200, minutes_ago=1)
        page1 = self._get("?limit=1")
        b1 = page1.json()
        assert [r["id"] for r in b1["data"]] == [str(a_new.id)]
        assert b1["has_more"] is True
        page2 = self._get(f"?limit=1&cursor={b1['next_cursor']}")
        b2 = page2.json()
        assert [r["id"] for r in b2["data"]] == [str(a_old.id)]
        assert b2["has_more"] is False

    def test_invalid_cursor_is_problem(self):
        resp = self._get("?cursor=not-a-cursor")
        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_cursor"

    def test_only_this_endpoints_attempts(self):
        other_cfg = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/other",
            secret=SECRET_A, event_types=["*"])
        WebhookDeliveryAttempt.objects.create(
            webhook_config=other_cfg, outbox_event=self.event, success=True)
        self._attempt(success=True, status_code=200)
        rows = self._get().json()["data"]
        assert len(rows) == 1  # only self.config's attempt, not other_cfg's

    def test_history_for_other_tenants_config_is_404(self):
        other = Tenant.objects.create(name="other-hist", products=["metering"])
        cfg = TenantWebhookConfig.objects.create(
            tenant=other, url="https://o.example.com/hook", secret=SECRET_A)
        resp = self.client.get(
            f"/api/v1/webhooks/configs/{cfg.id}/deliveries",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 404
