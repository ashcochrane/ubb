"""Sandbox reset clears sandbox-scoped audit entries and records itself (#82).

ADR-004: a sandbox reset wipes the sandbox's history but is not itself invisible
— it clears the sandbox tenant's ledger entries and writes ``sandbox.reset`` as
the first line of the fresh history, attributed to the principal that asked for
it. The ledger has no FK to Tenant, so the generic model sweep never touches it;
this pins the explicit clear-and-record.
"""
from django.test import TestCase

from apps.platform.audit.ledger import record
from apps.platform.audit.models import AuditRecord
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
from apps.platform.tenants.tasks import reset_sandbox_tenant_sync


class SandboxResetAuditTest(TestCase):
    def setUp(self):
        self.live = Tenant.objects.create(name="Live Co", products=["metering", "billing"])
        self.sandbox = get_or_create_sandbox(self.live)

    def _seed_sandbox_history(self, n=3):
        for i in range(n):
            record(action="api_key.created", tenant_id=self.sandbox.id,
                   resource_type="api_key", resource_id=f"k{i}", metadata={})

    def test_reset_clears_sandbox_entries_and_records_itself(self):
        self._seed_sandbox_history(3)
        # A live-tenant entry that must survive (clear is tenant-scoped).
        record(action="api_key.created", tenant_id=self.live.id,
               resource_type="api_key", resource_id="live", metadata={})

        reset_sandbox_tenant_sync(
            str(self.sandbox.id), keep_config=True,
            actor_kind="api_key", actor_id="key-1", actor_display="primary")

        sandbox_rows = list(AuditRecord.objects.filter(tenant_id=self.sandbox.id))
        # The three seeded entries are gone; only the reset remains.
        self.assertEqual(len(sandbox_rows), 1)
        reset = sandbox_rows[0]
        self.assertEqual(reset.action, "sandbox.reset")
        self.assertEqual(reset.resource_type, "sandbox")
        self.assertEqual(reset.actor_kind, "api_key")
        self.assertEqual(reset.actor_display, "primary")
        self.assertTrue(reset.metadata["keep_config"])
        # The live tenant's history is untouched.
        self.assertEqual(
            AuditRecord.objects.filter(tenant_id=self.live.id).count(), 1)

    def test_reset_without_an_actor_is_system_attributed(self):
        self._seed_sandbox_history(1)
        reset_sandbox_tenant_sync(str(self.sandbox.id), keep_config=False)
        reset = AuditRecord.objects.get(tenant_id=self.sandbox.id,
                                        action="sandbox.reset")
        self.assertEqual(reset.actor_kind, "system")
        self.assertFalse(reset.metadata["keep_config"])
