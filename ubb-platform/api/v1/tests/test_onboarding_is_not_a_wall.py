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
from django.core.exceptions import FieldDoesNotExist
from django.test import TestCase

from apps.billing.gating.models import RiskConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
from apps.platform.work.models import Task


class ALimitedStartNeedsNoCoveragePromiseTest(TestCase):
    """The admission verdict is gone, not defaulted permissive."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Part-way Through")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="u1")
        RiskConfig.objects.create(tenant=self.tenant)
        BillingTenantConfig.objects.create(tenant=self.tenant)
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)

    def test_an_explicit_ceiling_starts_a_task_on_a_tenant_with_no_cost_rates(self):
        result = RiskService.check(
            self.customer, create_task=True,
            provider_cost_limit_micros=10_000_000)

        self.assertTrue(result["allowed"])
        self.assertIsNone(result["reason"])
        task = Task.objects.get(id=result["task_id"])
        self.assertEqual(task.provider_cost_limit_micros, 10_000_000)

    def test_a_tenant_default_ceiling_starts_a_task_too(self):
        config = self.tenant.risk_config
        config.default_task_provider_cost_limit_micros = 7_000_000
        config.save(update_fields=["default_task_provider_cost_limit_micros"])

        result = RiskService.check(self.customer, create_task=True)

        self.assertTrue(result["allowed"])
        self.assertIsNone(result["reason"])
        self.assertEqual(result["provider_cost_limit_micros"], 7_000_000)

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


class TheSettingIsGoneRatherThanDefaultedOffTest(TestCase):
    """Nobody can turn the wall back on — there is nothing left to turn."""

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

    def _admit_a_limited_start(self, tenant, external_id):
        customer = Customer.objects.create(
            tenant=tenant, external_id=external_id)
        RiskConfig.objects.create(tenant=tenant)
        BillingTenantConfig.objects.create(tenant=tenant)
        Wallet.objects.create(customer=customer, balance_micros=20_000_000)
        return RiskService.check(
            customer, create_task=True, provider_cost_limit_micros=5_000_000)

    def test_both_admit_a_limited_start_with_no_cost_rates_declared(self):
        live_result = self._admit_a_limited_start(self.live, "live-1")
        sandbox_result = self._admit_a_limited_start(self.sandbox, "sandbox-1")

        self.assertTrue(live_result["allowed"])
        self.assertTrue(sandbox_result["allowed"])
        self.assertEqual(live_result["reason"], sandbox_result["reason"])
        self.assertEqual(
            live_result["provider_cost_limit_micros"],
            sandbox_result["provider_cost_limit_micros"])
        self.assertEqual(
            Task.objects.filter(tenant=self.live).count(),
            Task.objects.filter(tenant=self.sandbox).count())
