"""The per-minute bound on new work lives on the tenant row, not on billing's
risk row (#462, slice 6 §1, §6; ADR-0007 §1).

Admission control is a property of the work's admission, run by the kernel for
every tenant, so the bound is the tenant's `max_task_starts_per_minute` — NULL
is its one spelling of "no bound" — and the risk row keeps only the posture
the pool read takes when its store is away. What is pinned is that end state:
the risk row carries no per-minute bound, and the tenant row does.

Before the cutover (#190) this module drove `gating/0015`'s carry on the
historical models: each risk row's bound copied onto its tenant (the old row's
zero becoming NULL), the reverse putting every bound back, and the migration's
own operation list (a `RunPython` then the `RemoveField`). That data step left
with the squashed chain; the column it removed is still absent, and that is
the half kept here.
"""
from django.test import SimpleTestCase

from apps.billing.gating.models import RiskConfig
from apps.platform.tenants.models import Tenant

#: The risk row's column before #462, under the spelling the app held it by.
RISK_COLUMN = "max_requests_per_minute"
#: The tenant row's column, under the canonical name.
TENANT_COLUMN = "max_task_starts_per_minute"


class TheBoundLivesOnTheTenantRowTest(SimpleTestCase):

    def test_the_risk_row_holds_no_bound_and_the_tenant_row_does(self):
        self.assertNotIn(RISK_COLUMN,
                         {f.name for f in RiskConfig._meta.get_fields()})
        self.assertIn(TENANT_COLUMN,
                      {f.name for f in Tenant._meta.get_fields()})
        # NULL is the one spelling of "no bound" on the tenant row; the risk
        # row's zero-means-off convention did not travel.
        self.assertTrue(Tenant._meta.get_field(TENANT_COLUMN).null)
