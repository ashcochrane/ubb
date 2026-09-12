"""Migration `0015` carries each tenant's per-minute bound off billing's risk
row onto the tenant row, then drops its own column (#462, slice 6 §1, §6;
ADR-0007 §1).

⚠ REPLAYED AGAINST THE TABLE THE MIGRATION RAN AGAINST, NOT THE LIVE MODEL.
The carry reads a column the live risk row no longer has, so driving it from
today's registry would ask for a field that does not exist (#367's lesson).
Each case re-adds the dropped column to the live table for its duration —
Postgres runs DDL inside the transaction the test rolls back — and every
row is built through the HISTORICAL models `0015` was handed, so the
migration is exercised on the shape it was written for. The reverse is run
the same way, on the same reconstruction.

What is pinned: a bound above zero travels at its figure; the old row's
zero — its spelling of "switched off" — becomes the tenant row's NULL; a
tenant with no risk row keeps no bound; and the reverse puts every bound
back, creating the risk row where a tenant has none and writing zero where
a tenant declares no bound.
"""
import importlib

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from apps.billing.gating.models import RiskConfig as LiveRiskConfig
from apps.platform.tenants.models import Tenant as LiveTenant

MIGRATION = importlib.import_module(
    "apps.billing.gating.migrations."
    "0015_the_rate_bound_leaves_the_risk_row_for_the_tenant")

#: The state `0015` was handed: the gating app one migration before it, and
#: the tenant app at the migration that added the column it writes to.
BEFORE = [("gating", "0014_the_signal_ledger_keys_by_family_and_line"),
          ("tenants", "0027_admission_control_comes_to_the_kernel")]

A_BOUND = 25
ANOTHER_BOUND = 7


class TheCarryTest(TestCase):
    def setUp(self):
        self.apps = MigrationLoader(connection).project_state(BEFORE).apps
        self.RiskConfig = self.apps.get_model("gating", "RiskConfig")
        self.Tenant = self.apps.get_model("tenants", "Tenant")
        # Re-add the column the live table dropped, from the historical
        # model's own definition of it, so the historical INSERT lands.
        with connection.schema_editor() as editor:
            editor.add_field(
                self.RiskConfig,
                self.RiskConfig._meta.get_field(MIGRATION.RISK_COLUMN))

    def a_tenant(self, name, *, risk_bound=None, tenant_bound=None):
        tenant = LiveTenant.objects.create(name=name)
        if tenant_bound is not None:
            LiveTenant.objects.filter(pk=tenant.pk).update(
                **{MIGRATION.TENANT_COLUMN: tenant_bound})
        if risk_bound is not None:
            self.RiskConfig.objects.create(
                tenant_id=tenant.pk, **{MIGRATION.RISK_COLUMN: risk_bound})
        return tenant

    def tenant_bound(self, tenant):
        return (LiveTenant.objects.filter(pk=tenant.pk)
                .values_list(MIGRATION.TENANT_COLUMN, flat=True).get())

    def risk_bound(self, tenant):
        return (self.RiskConfig.objects.filter(tenant_id=tenant.pk)
                .values_list(MIGRATION.RISK_COLUMN, flat=True).first())

    def forwards(self):
        MIGRATION.carry_the_bound_onto_the_tenant(self.apps, None)

    def backwards(self):
        MIGRATION.carry_the_bound_back_onto_the_risk_row(self.apps, None)

    def test_a_bound_travels_at_its_figure(self):
        bounded = self.a_tenant("bounded", risk_bound=A_BOUND)
        self.forwards()
        self.assertEqual(self.tenant_bound(bounded), A_BOUND)

    def test_the_old_rows_zero_becomes_the_tenants_null(self):
        off = self.a_tenant("off", risk_bound=MIGRATION.SWITCHED_OFF)
        self.forwards()
        self.assertIsNone(self.tenant_bound(off))

    def test_a_tenant_with_no_risk_row_keeps_no_bound(self):
        unrowed = self.a_tenant("unrowed")
        self.forwards()
        self.assertIsNone(self.tenant_bound(unrowed))
        self.assertFalse(LiveRiskConfig.objects.filter(tenant_id=unrowed.pk).exists())

    def test_the_reverse_puts_every_bound_back(self):
        bounded = self.a_tenant("bounded", tenant_bound=A_BOUND)
        rowed_and_unbounded = self.a_tenant(
            "rowed", risk_bound=ANOTHER_BOUND)
        unrowed = self.a_tenant("unrowed")
        self.backwards()
        # A bound comes back at its figure, on a risk row created for it.
        self.assertEqual(self.risk_bound(bounded), A_BOUND)
        # A tenant declaring no bound whose row exists gets the old row's
        # spelling of "switched off", not the column's default of sixty.
        self.assertEqual(self.risk_bound(rowed_and_unbounded),
                         MIGRATION.SWITCHED_OFF)
        # And a tenant with neither still has neither.
        self.assertIsNone(self.risk_bound(unrowed))

    def test_the_two_directions_round_trip_a_bound(self):
        bounded = self.a_tenant("bounded", risk_bound=A_BOUND)
        self.forwards()
        self.RiskConfig.objects.filter(tenant_id=bounded.pk).update(
            **{MIGRATION.RISK_COLUMN: MIGRATION.SWITCHED_OFF})
        self.backwards()
        self.assertEqual(self.risk_bound(bounded), A_BOUND)

    def test_the_migration_carries_then_removes_and_says_why(self):
        from django.db.migrations import RemoveField, RunPython
        operations = MIGRATION.Migration.operations
        self.assertEqual([type(op) for op in operations], [RunPython, RemoveField])
        self.assertIsNotNone(operations[0].reverse_code)
        self.assertEqual(operations[1].name, MIGRATION.RISK_COLUMN)
        self.assertIn("ADR-0007", MIGRATION.__doc__)
        self.assertNotIn(MIGRATION.RISK_COLUMN,
                         {f.name for f in LiveRiskConfig._meta.get_fields()})
        self.assertIn(MIGRATION.TENANT_COLUMN,
                      {f.name for f in LiveTenant._meta.get_fields()})
