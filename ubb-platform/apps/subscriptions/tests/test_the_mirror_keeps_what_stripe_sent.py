"""The mirror keeps what Stripe sent, and a dollar amount only in dollars (#564).

A mirrored subscription and a mirrored invoice keep Stripe's integer, in the
minor unit of the currency Stripe sent, for every currency. Beside it sits the
economic amount in micros of UBB's one currency — which exists exactly when
that currency is UBB's. A foreign row is kept and quarantined with no dollar
amount: there is no FX, so any dollar figure beside a foreign code would be a
relabel. The database holds the pairing: `ck_subscription_economic_amount_only_in_usd`
and `ck_subscription_invoice_economic_amount_only_in_usd`.

These pin it at birth, through `objects.create()` — which skips every writer's
own check and meets only the database. The doors that move an existing row
(`QuerySet.update()`, raw SQL) are driven in
`apps/platform/tests/test_v1_is_usd_only.py::TheSourceFactsPairTheirAmountWithTheirCurrencyTest`.

Before the cutover (#190) this module ran `subscriptions/0018` through the
executor and back: each stored amount recovered as Stripe's integer, a foreign
row's relabelled dollar amount cleared, an amount no Stripe integer could have
produced refused rather than rounded, and the reverse putting the scaled amount
back. That data step left with the squashed chain; the state it produced is
what the cases below hold.
"""
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from apps.subscriptions.tests._helpers import a_mirrored_subscription

SUBSCRIPTION_PAIRING = "ck_subscription_economic_amount_only_in_usd"
INVOICE_PAIRING = "ck_subscription_invoice_economic_amount_only_in_usd"


class TheMirrorHoldsWhatStripeSentTest(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _subscription(self, stripe_id, currency, source_amount_minor, amount_micros):
        now = timezone.now()
        return a_mirrored_subscription(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription_id=stripe_id, stripe_product_name="Pro",
            status="active", amount_micros=amount_micros, currency=currency,
            source_amount_minor=source_amount_minor,
            interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)

    def _invoice(self, subscription, stripe_id, currency, source_minor, amount_micros):
        return SubscriptionInvoice.objects.create(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription=subscription, stripe_invoice_id=stripe_id,
            amount_paid_micros=amount_micros, source_amount_paid_minor=source_minor,
            currency=currency)

    def test_stripes_integer_is_kept_and_only_dollars_keep_a_dollar_amount(self):
        dollars = self._subscription("sub_usd", "usd", 4_900, 49_000_000)
        euros = self._subscription("sub_eur", "eur", 4_900, None)
        paid = self._invoice(euros, "in_eur", "eur", 1_234, None)

        usd = StripeSubscription.objects.get(id=dollars.id)
        eur = StripeSubscription.objects.get(id=euros.id)
        paid = SubscriptionInvoice.objects.get(id=paid.id)
        self.assertEqual((usd.source_amount_minor, usd.amount_micros),
                         (4_900, 49_000_000))
        self.assertEqual((eur.currency, eur.source_amount_minor, eur.amount_micros),
                         ("eur", 4_900, None))
        self.assertEqual((paid.currency, paid.source_amount_paid_minor,
                          paid.amount_paid_micros), ("eur", 1_234, None))

    def test_a_foreign_row_born_with_a_dollar_amount_is_refused_by_name(self):
        """The relabel, refused where it would be written: a dollar amount
        beside a foreign code, on the subscription and on its invoice. Nothing
        lands; the admitted foreign row beside it is the control."""
        with self.assertRaisesRegex(IntegrityError, SUBSCRIPTION_PAIRING):
            with transaction.atomic():
                self._subscription("sub_relabelled", "eur", 4_900, 49_000_000)
        self.assertFalse(StripeSubscription.objects.filter(
            stripe_subscription_id="sub_relabelled").exists())

        euros = self._subscription("sub_eur", "eur", 4_900, None)
        with self.assertRaisesRegex(IntegrityError, INVOICE_PAIRING):
            with transaction.atomic():
                self._invoice(euros, "in_relabelled", "eur", 1_234, 12_340_000)
        self.assertFalse(SubscriptionInvoice.objects.filter(
            stripe_invoice_id="in_relabelled").exists())
