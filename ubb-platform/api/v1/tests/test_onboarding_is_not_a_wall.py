"""Onboarding is not a wall (#321): a tenant part-way through declaring their
cost rates still gets admitted, and still gets their events recorded.

#320 made the compute spine record an event UBB cannot cost, with the cost
UNRESOLVED and the gaps named. That took the last thing the tenant setting
below was buying. What remained was a start gate that refused a limited unit
unless the tenant had promised full cost coverage — a promise nothing has kept
since #320, because the recording path no longer refuses an uncovered event and
a limited unit's total is now a floor rather than a total (#328 makes the floor
say so). This ticket deletes the setting, the gate and the word it returned,
and puts nothing in their place.

These tests sit in the composition layer because the deletion spans four
surfaces that no single product may import from each other: the tenant model,
the admission service in billing, the published tenant-config schemas, and the
sandbox provisioner in the platform kernel.

Every assertion below is an ABSENCE, so each one fails on the commit before
this one — they were written that way on purpose. Relaxing any of them puts
the wall back.
"""
import json
import uuid

from django.core.exceptions import FieldDoesNotExist
from django.test import Client, TestCase

from apps.billing.gating.models import RiskConfig
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
from apps.platform.work.models import Task


def a_limited_start(tenant, customer, *, ceiling):
    """Register a unit of work with a ceiling, through the one route that
    registers one.

    ⚠ THROUGH THE API RATHER THAN THROUGH THE ADMISSION SERVICE (#410). Every
    case in this module used to drive a start by setting a flag on that
    service, because that flag was the only way to create a unit of work.
    Registering one is `POST /api/v1/tasks` now, and the deleted coverage gate
    this module is about was a START-GATE refusal — so the honest place to
    assert its absence is the call that would have met it.
    """
    # The key's mode must match the tenant's — a live key cannot exist on a
    # sandbox and vice versa — and this helper is called with both.
    _, raw_key = TenantApiKey.create_key(tenant, is_test=tenant.is_sandbox)
    return Client().post(
        "/api/v1/tasks",
        data=json.dumps({"customer_id": str(customer.id),
                         "idempotency_key": f"attempt-{uuid.uuid4()}",
                         "provider_cost_limit_micros": ceiling}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}")


class ALimitedStartNeedsNoCoveragePromiseTest(TestCase):
    """The admission verdict is gone, not defaulted permissive."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Part-way Through")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="u1")
        RiskConfig.objects.create(tenant=self.tenant)
        BillingTenantConfig.objects.create(tenant=self.tenant)
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)

    def test_an_explicit_ceiling_starts_a_task_on_a_tenant_with_no_cost_rates(self):
        response = a_limited_start(self.tenant, self.customer,
                                   ceiling=10_000_000)

        self.assertEqual(response.status_code, 200)
        task = Task.objects.get(id=response.json()["task_id"])
        self.assertEqual(task.provider_cost_limit_micros, 10_000_000)

    def test_a_tenant_default_ceiling_starts_a_task_too(self):
        config = self.tenant.risk_config
        config.default_task_provider_cost_limit_micros = 7_000_000
        config.save(update_fields=["default_task_provider_cost_limit_micros"])

        response = a_limited_start(self.tenant, self.customer, ceiling=None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["provider_cost_limit_micros"], 7_000_000)


class TheSettingIsGoneRatherThanDefaultedOffTest(TestCase):
    """Nobody can turn the wall back on — there is nothing left to turn.

    Nothing here touches the database, on purpose: these read the model's
    declared fields and two checked-in registry documents, and paying an
    admission fixture for them would say the tests were about admission.
    """

    def test_the_refusal_word_leaves_the_published_verdict_vocabulary(self):
        """A word the API can no longer return is a lie in a machine-read file.

        `openapi/error-codes.json` is the registry the conformance sweep, the
        SDK generator and `core.problems` all read; its `verdicts` section is
        the closed vocabulary of the spend-control surface
        (`docs/conventions/api-contract.md`).
        """
        from core.problems import VERDICTS

        self.assertNotIn("cost_coverage_required", VERDICTS["pre_check_reasons"])

    def test_the_enable_time_refusal_code_leaves_the_registry_too(self):
        """The settings write raised this when the setting could not be armed.

        Same argument, one surface up, and the same shape as #320's retirement
        of `pricing_error`: the raise site is gone, so the code follows it out
        of the registry and out of the SDK's generated exception hierarchy.
        """
        from core.problems import PROBLEMS

        self.assertNotIn("no_cost_cards", PROBLEMS)

    def test_the_tenant_model_has_no_such_field(self):
        with self.assertRaises(FieldDoesNotExist):
            Tenant._meta.get_field("require_cost_card_coverage")

    def test_neither_published_tenant_config_schema_carries_it(self):
        """Both class names are OpenAPI component names, so this is contract.

        Django Ninja publishes a `Schema` subclass name as the component name,
        which is why the removal below is a reviewed contract break rather than
        an internal edit — and why neither class is renamed here.
        """
        from api.v1.schemas import TenantConfigIn, TenantConfigOut

        self.assertNotIn(
            "require_cost_card_coverage", TenantConfigOut.model_fields)
        self.assertNotIn(
            "require_cost_card_coverage", TenantConfigIn.model_fields)


class ASandboxAdmitsWhatItsLiveParentAdmitsTest(TestCase):
    """What a tenant tests is what they get.

    The sandbox provisioner copied the setting, so before this ticket a
    sandbox could refuse a start its live parent allowed, or the reverse, on
    nothing but a copied boolean. The parity is asserted as BEHAVIOUR rather
    than as "the provisioner no longer names the field": a copy reintroduced
    under another name would pass the second and fail this.
    """

    def setUp(self):
        self.live = Tenant.objects.create(
            name="Live Co", products=["metering", "billing"])
        self.sandbox = get_or_create_sandbox(self.live)

    def _outcome_of_a_limited_start(self, tenant, external_id):
        """The answer, reduced to what a caller can act on.

        The identifiers are excluded because they differ between two tenants
        for reasons that have nothing to do with this ticket; the STATUS is
        included, because a gate that refused would not answer 200, and so is
        the ceiling, because a gate that refused would pin none.
        """
        customer = Customer.objects.create(
            tenant=tenant, external_id=external_id)
        RiskConfig.objects.create(tenant=tenant)
        BillingTenantConfig.objects.create(tenant=tenant)
        Wallet.objects.create(customer=customer, balance_micros=20_000_000)

        response = a_limited_start(tenant, customer, ceiling=5_000_000)
        task = Task.objects.filter(tenant=tenant).get()
        return {
            "http_status": response.status_code,
            "ceiling_returned": response.json().get("provider_cost_limit_micros"),
            "ceiling_on_the_task": task.provider_cost_limit_micros,
        }

    def test_both_admit_a_limited_start_with_no_cost_rates_declared(self):
        live = self._outcome_of_a_limited_start(self.live, "live-1")
        sandbox = self._outcome_of_a_limited_start(self.sandbox, "sandbox-1")

        # Stated absolutely first, so this cannot pass by both being refused.
        self.assertEqual(live, {
            "http_status": 200,
            "ceiling_returned": 5_000_000,
            "ceiling_on_the_task": 5_000_000,
        })
        # Then the parity, over the whole verdict rather than key by key — a
        # difference in any field the caller reads fails here.
        self.assertEqual(sandbox, live)
