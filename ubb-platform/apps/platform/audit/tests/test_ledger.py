"""The audit ledger seam: record() writes a durable, tenant-scoped entry, reads
the actor from the auth-seam contextvar, rides the caller's transaction, refuses
unregistered actions, and is append-only (ADR-004 §2, §4)."""
import uuid

from django.db import transaction
from django.test import TestCase

from apps.platform.audit.actors import (
    SYSTEM,
    api_key_actor,
    clear_current_actor,
    member_actor,
    operator_actor,
    set_current_actor,
)
from apps.platform.audit.ledger import record
from apps.platform.audit.models import AuditRecord
from core.logging import correlation_id_var


class RecordTest(TestCase):
    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.addCleanup(clear_current_actor)

    def test_record_writes_all_fields(self):
        rec = record(
            action="api_key.created",
            tenant_id=self.tenant_id,
            resource_type="api_key",
            resource_id="key-123",
            metadata={"label": "CI"},
            actor=member_actor("m-1", "sam@example.com"),
        )
        rec.refresh_from_db()
        self.assertEqual(rec.tenant_id, self.tenant_id)
        self.assertEqual(rec.action, "api_key.created")
        self.assertEqual(rec.actor_kind, "member")
        self.assertEqual(rec.actor_id, "m-1")
        self.assertEqual(rec.actor_display, "sam@example.com")
        self.assertEqual(rec.resource_type, "api_key")
        self.assertEqual(rec.resource_id, "key-123")
        self.assertEqual(rec.metadata, {"label": "CI"})

    def test_record_reads_actor_from_contextvar(self):
        set_current_actor(api_key_actor("k-9", "primary"))
        rec = record(action="api_key.created", tenant_id=self.tenant_id,
                     resource_type="api_key", resource_id="key-1")
        self.assertEqual(rec.actor_kind, "api_key")
        self.assertEqual(rec.actor_id, "k-9")
        self.assertEqual(rec.actor_display, "primary")

    def test_explicit_actor_overrides_contextvar(self):
        set_current_actor(api_key_actor("k-9", "primary"))
        rec = record(action="api_key.created", tenant_id=self.tenant_id,
                     resource_type="api_key", resource_id="key-1",
                     actor=operator_actor("staff-1"))
        self.assertEqual(rec.actor_kind, "operator")
        self.assertEqual(rec.actor_display, "UBB operator")

    def test_unattributed_record_falls_back_to_system(self):
        # No actor passed, none captured — the fact is still recorded (never lose
        # a change) under the reserved `system` kind, and a warning is logged.
        with self.assertLogs("ubb.audit", level="WARNING") as cm:
            rec = record(action="api_key.created", tenant_id=self.tenant_id,
                         resource_type="api_key", resource_id="key-1")
        self.assertEqual(rec.actor_kind, SYSTEM)
        self.assertEqual(rec.actor_id, "")
        self.assertEqual(rec.actor_display, "")
        self.assertTrue(any("audit.unattributed" in m for m in cm.output))

    def test_unregistered_action_raises_and_writes_nothing(self):
        with self.assertRaises(ValueError):
            record(action="not.registered", tenant_id=self.tenant_id,
                   resource_type="api_key", resource_id="key-1")
        self.assertEqual(AuditRecord.objects.count(), 0)

    def test_record_stamps_request_correlation_id(self):
        cid = "11111111-1111-1111-1111-111111111111"
        token = correlation_id_var.set(cid)
        try:
            rec = record(action="api_key.created", tenant_id=self.tenant_id,
                         resource_type="api_key", resource_id="key-1",
                         actor=member_actor("m-1", "a@b.com"))
        finally:
            correlation_id_var.reset(token)
        self.assertEqual(rec.correlation_id, cid)

    def test_record_rides_caller_transaction_rollback(self):
        # ADR-004 §4: written in the same transaction as the change — a rolled
        # back mutation leaves no phantom row.
        try:
            with transaction.atomic():
                record(action="api_key.created", tenant_id=self.tenant_id,
                       resource_type="api_key", resource_id="key-1",
                       actor=member_actor("m-1", "a@b.com"))
                raise RuntimeError("mutation failed after recording")
        except RuntimeError:
            pass
        self.assertEqual(AuditRecord.objects.count(), 0)

    def test_resource_id_is_stringified(self):
        rid = uuid.uuid4()
        rec = record(action="api_key.created", tenant_id=self.tenant_id,
                     resource_type="api_key", resource_id=rid,
                     actor=member_actor("m-1", "a@b.com"))
        self.assertEqual(rec.resource_id, str(rid))


class AppendOnlyTest(TestCase):
    def setUp(self):
        self.addCleanup(clear_current_actor)

    def test_existing_row_cannot_be_updated(self):
        rec = record(action="api_key.created", tenant_id=uuid.uuid4(),
                     resource_type="api_key", resource_id="key-1",
                     actor=member_actor("m-1", "a@b.com"))
        # Reload so _state.adding is False (a fetched, persisted row).
        loaded = AuditRecord.objects.get(pk=rec.pk)
        loaded.action = "tampered"
        with self.assertRaises(ValueError):
            loaded.save()
        # And the stored value is untouched.
        self.assertEqual(AuditRecord.objects.get(pk=rec.pk).action,
                         "api_key.created")
