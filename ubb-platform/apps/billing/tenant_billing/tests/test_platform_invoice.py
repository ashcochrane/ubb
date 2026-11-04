import contextlib
import io
import logging
import uuid
from datetime import date
from unittest.mock import patch, MagicMock

import stripe
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.platform.audit.models import AuditRecord
from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.models import BillingTenantConfig, TenantBillingPeriod, TenantInvoice
from apps.billing.tenant_billing.tasks import generate_tenant_platform_invoices

STRIPE_CALL = "apps.billing.stripe.services.stripe_service.stripe_call"
TASKS_LOGGER = "apps.billing.tenant_billing.tasks"
NO_PLATFORM_CUSTOMER = "platform_invoice.no_platform_customer"
SET_ACTION = "tenant.platform_billing_customer_set"


class PlatformInvoiceStripeTest(TestCase):
    def setUp(self):
        # A platform customer id in the shape Stripe issues one (`cus_` and an
        # alphanumeric suffix): since R10 Stage C3 (F-10) the monthly job
        # refuses any other shape before it claims the period.
        self.tenant = Tenant.objects.create(
            name="Test",
            stripe_connected_account_id="acct_test",
            stripe_customer_id="cus_tenant_test",  # Tenant as UBB's customer
            platform_fee_percentage=1.00,
        )
        BillingTenantConfig.objects.create(
            tenant=self.tenant,
            stripe_customer_id="cus_TenantTest",
            platform_fee_percentage=1.00,
        )
        self.period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
            total_billed_cost_micros=100_000_000_000,
            recorded_events=5000,
            platform_fee_micros=1_000_000_000,
        )

    @patch("apps.billing.stripe.services.stripe_service.stripe_call")
    def test_creates_stripe_invoice_for_platform_fee(self, mock_stripe_call):
        mock_invoice = MagicMock()
        mock_invoice.id = "inv_platform_test"
        mock_stripe_call.return_value = mock_invoice

        generate_tenant_platform_invoices()

        invoice = TenantInvoice.objects.get(billing_period=self.period)
        self.assertEqual(invoice.total_amount_micros, 1_000_000_000)
        self.assertEqual(invoice.status, "finalized")

        # Verify Stripe was called with tenant's customer ID, not connected account
        create_call = mock_stripe_call.call_args_list[0]
        self.assertNotIn("stripe_account", create_call.kwargs)

    @patch("apps.billing.stripe.services.stripe_service.stripe_call")
    def test_stripe_failure_keeps_period_closed_for_retry(self, mock_stripe_call):
        """On Stripe failure, period stays closed so next run retries."""
        mock_stripe_call.side_effect = Exception("Stripe down")

        generate_tenant_platform_invoices()

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "closed")  # NOT "invoiced"
        self.assertFalse(TenantInvoice.objects.filter(billing_period=self.period).exists())

    def test_zero_fee_period_auto_invoiced(self):
        self.period.platform_fee_micros = 0
        self.period.save()

        generate_tenant_platform_invoices()

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "invoiced")
        self.assertFalse(TenantInvoice.objects.filter(billing_period=self.period).exists())


# --- R10 Stage C3, F-10 (RULED Q6): the platform-fee Stripe customer ---------


class _Captured(logging.Handler):
    """`caplog` cannot see `apps.*` loggers (`propagate: False` in settings),
    so the module's own logger gets a handler for the test's duration."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@contextlib.contextmanager
def _captured(name=TASKS_LOGGER):
    log = logging.getLogger(name)
    handler = _Captured()
    log.addHandler(handler)
    try:
        yield handler.records
    finally:
        log.removeHandler(handler)


def _no_platform_customer(records):
    return [r for r in records if r.getMessage() == NO_PLATFORM_CUSTOMER]


def _closed_period(tenant, start, end, fee=280_000):
    return TenantBillingPeriod.objects.create(
        tenant=tenant, period_start=start, period_end=end, status="closed",
        total_billed_cost_micros=28_400_000, recorded_events=16,
        platform_fee_micros=fee)


class NoPlatformCustomerTest(TestCase):
    """A fee period whose tenant has no platform billing customer — none set,
    or one that is not a Stripe customer id — is NOT claimed, NOT sent to
    Stripe, and stays `closed` for the next run. The job says so ONCE per run
    per tenant, as a structured ERROR an operator can alert on, naming the
    periods waiting. Until C3 it claimed each period, raised before any Stripe
    call, reverted it to `closed` and logged a generic exception per period."""

    def test_one_structured_error_per_tenant_and_every_period_stays_closed(self):
        missing = Tenant.objects.create(name="Missing")  # no config row at all
        blank = Tenant.objects.create(name="Blank")
        BillingTenantConfig.objects.create(tenant=blank)
        malformed = Tenant.objects.create(name="Malformed")
        BillingTenantConfig.objects.create(tenant=malformed, stripe_customer_id="acct_not_a_customer")
        periods = [
            _closed_period(missing, date(2026, 1, 1), date(2026, 2, 1)),
            _closed_period(missing, date(2026, 2, 1), date(2026, 3, 1)),
            _closed_period(blank, date(2026, 1, 1), date(2026, 2, 1)),
            _closed_period(malformed, date(2026, 1, 1), date(2026, 2, 1)),
        ]
        for run in (1, 2):
            with self.subTest(run=run):
                with patch(STRIPE_CALL) as sc, _captured() as records:
                    generate_tenant_platform_invoices()
                sc.assert_not_called()
                errors = _no_platform_customer(records)
                self.assertTrue(all(r.levelno == logging.ERROR for r in errors))
                self.assertEqual(
                    sorted((r.data["tenant_id"], r.data["reason"], sorted(r.data["period_ids"]))
                           for r in errors),
                    sorted([
                        (str(missing.id), "missing", sorted(str(p.id) for p in periods[:2])),
                        (str(blank.id), "missing", [str(periods[2].id)]),
                        (str(malformed.id), "malformed", [str(periods[3].id)]),
                    ]))
                for period in periods:
                    period.refresh_from_db()
                    self.assertEqual(period.status, "closed")
                self.assertFalse(TenantInvoice.objects.exists())

    def test_a_tenant_with_a_customer_is_invoiced_beside_one_without(self):
        ready = Tenant.objects.create(name="Ready")
        BillingTenantConfig.objects.create(tenant=ready, stripe_customer_id="cus_Ready01")
        unready = Tenant.objects.create(name="Unready")
        ready_period = _closed_period(ready, date(2026, 1, 1), date(2026, 2, 1))
        unready_period = _closed_period(unready, date(2026, 1, 1), date(2026, 2, 1))
        with patch(STRIPE_CALL) as sc, _captured() as records:
            sc.return_value = MagicMock(id="in_platform_ready")
            generate_tenant_platform_invoices()
        self.assertEqual([r.data["tenant_id"] for r in _no_platform_customer(records)],
                         [str(unready.id)])
        ready_period.refresh_from_db()
        unready_period.refresh_from_db()
        self.assertEqual((ready_period.status, unready_period.status), ("invoiced", "closed"))
        self.assertEqual(sc.call_args_list[0].kwargs["customer"], "cus_Ready01")


class SetPlatformBillingCustomerCommandTest(TestCase):
    """The canonical operator path (RULED Q6): format validation, an optional
    `--verify` through the guarded Stripe wrapper under UBB's own platform key,
    the write, and a governance audit entry recorded under the operator actor.
    No tenant route and no admin form writes this field."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme")

    def _run(self, *args):
        out = io.StringIO()
        call_command("set_platform_billing_customer", "--tenant", str(self.tenant.id),
                     *args, stdout=out)
        return out.getvalue()

    def _nothing_written(self):
        config = BillingTenantConfig.objects.filter(tenant=self.tenant).first()
        self.assertTrue(config is None or config.stripe_customer_id == "")
        self.assertFalse(AuditRecord.objects.filter(action=SET_ACTION).exists())

    def test_sets_the_customer_and_records_the_governance_action(self):
        out = self._run("--stripe-customer-id", "cus_Acme123", "--operator", "op-7")
        self.assertIn("cus_Acme123", out)
        config = BillingTenantConfig.objects.get(tenant=self.tenant)
        self.assertEqual(config.stripe_customer_id, "cus_Acme123")
        entry = AuditRecord.objects.get(tenant_id=self.tenant.id, action=SET_ACTION)
        self.assertEqual((entry.actor_kind, entry.actor_id, entry.actor_display),
                         ("operator", "op-7", "UBB operator"))
        self.assertEqual((entry.resource_type, entry.resource_id), ("tenant", str(self.tenant.id)))
        self.assertEqual(entry.metadata, {"stripe_customer_id": "cus_Acme123",
                                          "previous_stripe_customer_id": "",
                                          "verified": False})

    def test_a_change_records_the_customer_it_replaced(self):
        BillingTenantConfig.objects.create(tenant=self.tenant, stripe_customer_id="cus_Old1")
        self._run("--stripe-customer-id", "cus_New2")
        self.assertEqual(BillingTenantConfig.objects.get(tenant=self.tenant).stripe_customer_id,
                         "cus_New2")
        entry = AuditRecord.objects.get(action=SET_ACTION)
        self.assertEqual(entry.metadata["previous_stripe_customer_id"], "cus_Old1")
        self.assertEqual((entry.actor_kind, entry.actor_id), ("operator", ""))

    def test_a_malformed_customer_id_is_refused_and_nothing_is_written(self):
        for bad in ("", "cus_", "acct_123", "cus_has space", "cus_x-y", "CUS_ABC",
                    " cus_ABC", "cus_ABC\n", "cus_" + "a" * 252):
            with self.subTest(value=bad):
                with self.assertRaisesRegex(CommandError, "Stripe customer id"):
                    self._run("--stripe-customer-id", bad)
        self._nothing_written()

    def test_an_unknown_tenant_is_refused(self):
        for tenant in (str(uuid.uuid4()), "not-a-uuid"):
            with self.subTest(tenant=tenant):
                with self.assertRaisesRegex(CommandError, "tenant"):
                    call_command("set_platform_billing_customer", "--tenant", tenant,
                                 "--stripe-customer-id", "cus_Acme123", stdout=io.StringIO())
        self.assertFalse(BillingTenantConfig.objects.exists())

    def test_verify_without_a_key_is_refused_by_name_before_transport(self):
        with override_settings(STRIPE_SECRET_KEY=""), \
                patch("stripe.Customer.retrieve") as retrieve:
            with self.assertRaisesRegex(CommandError, "STRIPE_SECRET_KEY"):
                self._run("--stripe-customer-id", "cus_Acme123", "--verify")
        retrieve.assert_not_called()
        self._nothing_written()

    def test_verify_retrieves_the_customer_under_ubbs_platform_key_then_writes(self):
        customer = stripe.Customer.construct_from(
            {"id": "cus_Acme123", "object": "customer"}, settings.STRIPE_SECRET_KEY)
        with patch("stripe.Customer.retrieve", return_value=customer) as retrieve:
            self._run("--stripe-customer-id", "cus_Acme123", "--verify")
        retrieve.assert_called_once()
        self.assertEqual(retrieve.call_args.kwargs["id"], "cus_Acme123")
        self.assertEqual(retrieve.call_args.kwargs["api_key"], settings.STRIPE_SECRET_KEY)
        self.assertNotIn("stripe_account", retrieve.call_args.kwargs)  # UBB's own account
        self.assertEqual(BillingTenantConfig.objects.get(tenant=self.tenant).stripe_customer_id,
                         "cus_Acme123")
        self.assertIs(AuditRecord.objects.get(action=SET_ACTION).metadata["verified"], True)

    def test_verify_refuses_a_deleted_customer(self):
        deleted = stripe.Customer.construct_from(
            {"id": "cus_Acme123", "object": "customer", "deleted": True},
            settings.STRIPE_SECRET_KEY)
        with patch("stripe.Customer.retrieve", return_value=deleted):
            with self.assertRaisesRegex(CommandError, "deleted"):
                self._run("--stripe-customer-id", "cus_Acme123", "--verify")
        self._nothing_written()

    def test_verify_refuses_a_customer_stripe_does_not_know(self):
        unknown = stripe.error.InvalidRequestError("No such customer: 'cus_Acme123'", "id")
        with patch("stripe.Customer.retrieve", side_effect=unknown):
            with self.assertRaisesRegex(CommandError, "No such customer"):
                self._run("--stripe-customer-id", "cus_Acme123", "--verify")
        self._nothing_written()


class StageBStep12PlatformFeeTest(TestCase):
    """Stage B step 12, end to end: a closed period with a platform fee
    (280,000) waits — structured ERROR, still `closed`, nothing sent — until an
    operator sets the platform billing customer through the command; the next
    run invoices it to that customer."""

    def test_the_fee_period_waits_for_the_operator_then_invoices(self):
        tenant = Tenant.objects.create(name="Step12")
        period = _closed_period(tenant, date(2026, 10, 1), date(2026, 11, 1), fee=280_000)

        with patch(STRIPE_CALL) as sc, _captured() as records:
            generate_tenant_platform_invoices()
        sc.assert_not_called()
        self.assertEqual(len(_no_platform_customer(records)), 1)
        period.refresh_from_db()
        self.assertEqual(period.status, "closed")

        call_command("set_platform_billing_customer", "--tenant", str(tenant.id),
                     "--stripe-customer-id", "cus_Step12Tenant", "--operator", "op-1",
                     stdout=io.StringIO())

        with patch(STRIPE_CALL) as sc, _captured() as records:
            sc.return_value = MagicMock(id="in_platform_step12")
            generate_tenant_platform_invoices()
        self.assertEqual(_no_platform_customer(records), [])
        period.refresh_from_db()
        self.assertEqual(period.status, "invoiced")
        invoice = TenantInvoice.objects.get(billing_period=period)
        self.assertEqual(invoice.stripe_invoice_id, "in_platform_step12")
        self.assertEqual(invoice.total_amount_micros, 280_000)
        self.assertEqual(sc.call_args_list[0].kwargs["customer"], "cus_Step12Tenant")
