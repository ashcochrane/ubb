"""Every outbound money call takes its currency from the record it draws on (#565).

UBB v1 is US dollars only, and the database holds every economic column to it
(ADR-0023). So a call to Stripe that wrote `"usd"` itself would send the right
word today — and would go on sending it the day a record said otherwise, with
nothing connecting the money that leaves to the record it is drawn against.
#565 asks for the connection, not the word: each call reads the currency off
the authoritative monetary object and REFUSES, never reconciles, a record that
disagrees.

**The database cannot be what makes these tests pass.** Each refusal case
lifts the record's `CHECK` inside the test's transaction, puts the record in
another currency, and asks the call to send. The call must refuse on its own —
by name, before Stripe is reached — which is what "each adapter independently
refuses a disagreement" means (the owner's amendment C). A call that wrote
`"usd"` instead of reading would send, and go red here.

Each call has its control beside it: a record in US dollars, and the currency
sent is the record's.
"""
from datetime import date
from unittest.mock import MagicMock, patch

from django.db import connection
from django.test import TestCase

from apps.billing.connectors.stripe.receipts import ReceiptService
from apps.billing.connectors.stripe.stripe_api import (
    charge_saved_payment_method, create_checkout_session)
from apps.billing.invoicing.models import CustomerUsageInvoice, Invoice
from apps.billing.stripe.services.stripe_service import StripeService
from apps.billing.tenant_billing.models import TenantBillingPeriod
from apps.billing.topups.models import TopUpAttempt
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from apps.subscriptions.orchestration.service import SubscriptionOrchestrator
from core.currency_policy import CurrencyDisagreement

FOREIGN = "eur"


def _lift(table, check):
    """The record's CHECK, gone for this test's transaction only (the
    deferred rules other tables carry are settled first, or Postgres will not
    alter a table with events pending)."""
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT {check}")


def _restate(table, pk, currency, column="currency"):
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET {column} = %s WHERE id = %s",
                       [currency, str(pk)])


class _ConnectedTenant(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Connected", products=["metering", "billing"],
            stripe_connected_account_id="acct_x", charges_enabled=True,
            stripe_customer_id="cus_platform")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_1")


class ATopUpReadsTheWalletItCreditsTest(_ConnectedTenant):
    """Checkout, the off-session charge and the receipt: the wallet is the record."""

    def setUp(self):
        super().setUp()
        self.wallet = Wallet.objects.create(customer=self.customer)
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer, billing_owner_id=self.customer.id,
            amount_micros=20_000_000, trigger="manual", status="pending")

    def _foreign_wallet(self):
        _lift("ubb_wallet", "ck_wallet_currency_usd")
        _restate("ubb_wallet", self.wallet.id, FOREIGN)

    @patch("apps.billing.connectors.stripe.stripe_api.stripe_call")
    def test_checkout_refuses_a_wallet_in_another_currency(self, stripe_call):
        self._foreign_wallet()
        with self.assertRaisesRegex(CurrencyDisagreement,
                                    rf"wallet {self.wallet.id} is in '{FOREIGN}'"):
            create_checkout_session(self.customer, 20_000_000, self.attempt,
                                    success_url="https://s", cancel_url="https://c")
        stripe_call.assert_not_called()

    @patch("apps.billing.connectors.stripe.stripe_api.stripe_call")
    def test_checkout_sends_the_wallets_currency(self, stripe_call):
        stripe_call.return_value = MagicMock(id="cs_1", url="https://pay")
        create_checkout_session(self.customer, 20_000_000, self.attempt,
                                success_url="https://s", cancel_url="https://c")
        (line,) = stripe_call.call_args.kwargs["line_items"]
        self.assertEqual(line["price_data"]["currency"], self.wallet.currency)

    @patch("apps.billing.connectors.stripe.stripe_api.stripe_call")
    def test_the_off_session_charge_refuses_a_wallet_in_another_currency(
            self, stripe_call):
        self._foreign_wallet()
        with self.assertRaises(CurrencyDisagreement):
            charge_saved_payment_method(self.customer, 20_000_000, self.attempt)
        stripe_call.assert_not_called()

    @patch("apps.billing.connectors.stripe.stripe_api.stripe_call")
    def test_the_off_session_charge_sends_the_wallets_currency(self, stripe_call):
        stripe_call.side_effect = [MagicMock(data=[MagicMock(id="pm_1")]),
                                   {"invoice_settings": {}},
                                   MagicMock(id="pi_1")]
        charge_saved_payment_method(self.customer, 20_000_000, self.attempt)
        self.assertEqual(stripe_call.call_args.kwargs["currency"],
                         self.wallet.currency)

    @patch("apps.billing.connectors.stripe.receipts.stripe_call")
    def test_the_receipt_refuses_a_wallet_in_another_currency(self, stripe_call):
        self._foreign_wallet()
        with self.assertRaises(CurrencyDisagreement):
            ReceiptService.create_topup_receipt(self.customer, self.attempt)
        stripe_call.assert_not_called()
        self.assertFalse(Invoice.objects.filter(top_up_attempt=self.attempt).exists())

    @patch("apps.billing.connectors.stripe.receipts.stripe_call")
    def test_the_receipt_sends_the_wallets_currency(self, stripe_call):
        stripe_call.return_value = MagicMock(id="in_1")
        ReceiptService.create_topup_receipt(self.customer, self.attempt)
        (item,) = [call for call in stripe_call.call_args_list
                   if "currency" in call.kwargs]
        self.assertEqual(item.kwargs["currency"], self.wallet.currency)

    @patch("apps.billing.connectors.stripe.stripe_api.stripe_call")
    def test_a_first_top_up_reads_the_one_rule_a_wallet_is_born_by(
            self, stripe_call):
        """No wallet yet: the record is the rule that will bear it — the
        tenant's currency — and a tenant in another is refused the same way."""
        self.wallet.delete()
        Wallet.all_objects.filter(customer=self.customer).delete()
        _lift("ubb_tenant", "ck_tenant_default_currency_usd")
        _restate("ubb_tenant", self.tenant.id, FOREIGN, "default_currency")
        with self.assertRaisesRegex(CurrencyDisagreement, "will be born with"):
            create_checkout_session(self.customer, 20_000_000, self.attempt,
                                    success_url="https://s", cancel_url="https://c")
        stripe_call.assert_not_called()


class APlatformFeeReadsItsBillingPeriodTest(_ConnectedTenant):

    def setUp(self):
        super().setUp()
        from apps.billing.queries import get_billing_config
        config = get_billing_config(self.tenant.id)
        config.stripe_customer_id = "cus_platform"
        config.save(update_fields=["stripe_customer_id"])
        self.period = TenantBillingPeriod.objects.create(
            tenant=self.tenant, period_start=date(2026, 4, 1),
            period_end=date(2026, 5, 1), status="closed",
            platform_fee_micros=5_000_000)

    @patch("apps.billing.stripe.services.stripe_service.stripe_call")
    @patch("apps.billing.stripe.services.stripe_service.api_key_for_tenant",
           return_value="sk")
    def test_the_fee_refuses_a_period_in_another_currency(self, _key, stripe_call):
        _lift("ubb_tenant_billing_period", "ck_billing_period_currency_usd")
        _restate("ubb_tenant_billing_period", self.period.id, FOREIGN)
        self.period.refresh_from_db()
        with self.assertRaisesRegex(CurrencyDisagreement,
                                    rf"billing period {self.period.id}"):
            StripeService.create_tenant_platform_invoice(self.tenant, self.period)
        stripe_call.assert_not_called()

    @patch("apps.billing.stripe.services.stripe_service.stripe_call")
    @patch("apps.billing.stripe.services.stripe_service.api_key_for_tenant",
           return_value="sk")
    def test_the_fee_sends_the_periods_currency(self, _key, stripe_call):
        stripe_call.return_value = MagicMock(id="in_fee")
        StripeService.create_tenant_platform_invoice(self.tenant, self.period)
        (item,) = [call for call in stripe_call.call_args_list
                   if "currency" in call.kwargs]
        self.assertEqual(item.kwargs["currency"], self.period.currency)


class APlanPriceReadsTheTenantsCatalogTest(_ConnectedTenant):
    """A plan has no currency of its own: the tenant row is its record."""

    def _provision(self, restate=None):
        plan = a_plan(tenant=self.tenant, key="pro", name="Pro",
                      access_fee_micros=50_000_000)
        if restate is not None:
            restate()
        # Read back, as the provisioning task reads it: the tenant the plan
        # names is the row on disk, never this test's copy.
        plan = type(plan).objects.get(pk=plan.pk)
        with patch("apps.subscriptions.orchestration.service.stripe.Product.create",
                   return_value=MagicMock(id="prod_a")), \
             patch("apps.subscriptions.orchestration.service.stripe.Price.create",
                   return_value=MagicMock(id="price_a")) as price:
            SubscriptionOrchestrator.ensure_plan_provisioned(plan)
        return price

    def test_provisioning_refuses_a_tenant_in_another_currency(self):
        def foreign_tenant():
            _lift("ubb_tenant", "ck_tenant_default_currency_usd")
            _restate("ubb_tenant", self.tenant.id, FOREIGN, "default_currency")
        with self.assertRaisesRegex(CurrencyDisagreement, "plan catalog"):
            self._provision(restate=foreign_tenant)

    def test_provisioning_sends_the_tenants_currency(self):
        price = self._provision()
        self.assertEqual(price.call_args.kwargs["currency"],
                         self.tenant.default_currency)
