"""`subscriptions/0018` run for real: what Stripe sent is recovered, never invented (#564).

Every mirror amount stored before the migration was Stripe's integer times the
minor unit of a two-decimal currency, so dividing gives back what Stripe sent —
and a foreign row's dollar amount, which was a relabel, is cleared. Driven
through Django's executor, back to `0017` and forward again, inside the test's
transaction (`work`'s #562 module is the precedent), with rows written as the
writers before the migration wrote them: an amount, a currency, no source.
"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

BEFORE = ("subscriptions", "0017_supplied_revenue_is_usd_only")
AFTER = ("subscriptions",
         "0018_a_foreign_currency_subscription_is_kept_and_quarantined")


def _migrate_to(target):
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    MigrationExecutor(connection).migrate([target])


class TheMigrationRecoversWhatStripeSentTest(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        _migrate_to(BEFORE)
        state = MigrationExecutor(connection).loader.project_state(BEFORE)
        self.Old = state.apps.get_model("subscriptions", "StripeSubscription")
        self.OldInvoice = state.apps.get_model("subscriptions", "SubscriptionInvoice")

    def tearDown(self):
        _migrate_to(AFTER)

    def _old(self, stripe_id, currency, amount_micros):
        now = timezone.now()
        return self.Old.objects.create(
            tenant_id=self.tenant.id, customer_id=self.customer.id,
            stripe_subscription_id=stripe_id, stripe_product_name="Pro",
            status="active", amount_micros=amount_micros, currency=currency,
            interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now).id

    def test_the_integer_is_recovered_and_only_dollars_keep_a_dollar_amount(self):
        dollars = self._old("sub_usd", "usd", 49_000_000)
        euros = self._old("sub_eur", "eur", 49_000_000)
        invoice = self.OldInvoice.objects.create(
            tenant_id=self.tenant.id, customer_id=self.customer.id,
            stripe_subscription_id=euros, stripe_invoice_id="in_eur",
            amount_paid_micros=12_340_000, currency="eur").id

        _migrate_to(AFTER)

        usd = StripeSubscription.objects.get(id=dollars)
        eur = StripeSubscription.objects.get(id=euros)
        paid = SubscriptionInvoice.objects.get(id=invoice)
        self.assertEqual((usd.source_amount_minor, usd.amount_micros),
                         (4_900, 49_000_000))
        self.assertEqual((eur.currency, eur.source_amount_minor, eur.amount_micros),
                         ("eur", 4_900, None))
        self.assertEqual((paid.currency, paid.source_amount_paid_minor,
                          paid.amount_paid_micros), ("eur", 1_234, None))

    def test_an_amount_no_stripe_integer_produced_is_refused_not_rounded(self):
        self._old("sub_odd", "usd", 49_000_001)

        with self.assertRaisesRegex(RuntimeError, r"49000001.*will not round"):
            _migrate_to(AFTER)
        # Untouched by the refusal; corrected here so tearDown's forward run
        # finds a row a Stripe integer could have produced.
        self.assertEqual(self.Old.objects.get(
            stripe_subscription_id="sub_odd").amount_micros, 49_000_001)
        self.Old.objects.filter(stripe_subscription_id="sub_odd").update(
            amount_micros=49_000_000)

    def test_the_reverse_puts_the_scaled_amount_back(self):
        euros = self._old("sub_eur", "eur", 49_000_000)
        _migrate_to(AFTER)
        _migrate_to(BEFORE)

        self.assertEqual(self.Old.objects.get(id=euros).amount_micros, 49_000_000)
