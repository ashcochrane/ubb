"""A foreign-currency fact from Stripe is kept as Stripe stated it, and quarantined (#564).

UBB v1 is US dollars only (ADR-0023). That is two rules, and this module is the
second: a connected account may hold a subscription — and issue its invoices —
in a currency UBB never admitted, and UBB does not refuse what Stripe already
did. It keeps the fact truthfully and keeps it OUT of its economics:

  * **kept, as Stripe stated it** — the currency Stripe named and the integer it
    sent, in that currency's own minor unit, never scaled by the tenant's;
  * **never relabelled** — no dollar amount exists for it, so none is stored;
  * **idempotent** — a retried event, a second event about the same object, and
    the poller's repair all meet the one row;
  * **excluded from every aggregate** — subscription revenue, the business
    margin, and the alerting snapshot an unprofitable flag is raised on;
  * **visible** — every revenue and margin read says how many it left out, as a
    required, exact count that reads 0, never null, where nothing was.

Both inbound paths are driven through their public webhook routes, signature
verification patched as the routes' own modules do; the poll sync and the
poller's repair through the functions their schedules call.
"""
import json
from datetime import date, datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import Client, RequestFactory, TestCase

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from apps.subscriptions.tests._helpers import a_mirrored_subscription
from apps.subscriptions.tests.test_sync import FakeStripeSub, _licensed_item
from core.currency_policy import FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_KEY as COUNT

ACCOUNT = "acct_foreign"

#: Stripe's own integers, in each currency's minor unit.
EUROS = 4_900          # €49.00
YEN = 6_000            # ¥6,000 — a currency `core.money` cannot even represent
DOLLARS = 2_500        # $25.00

#: The window every aggregate below is asked about: one whole month, so a
#: monthly subscription's nominal accrual is its amount exactly.
OPENS = date(2026, 4, 1)
CLOSES = date(2026, 4, 30)


def _subscription(stripe_id, customer, currency, unit_amount):
    return FakeStripeSub(
        id=stripe_id, customer=customer.stripe_customer_id, status="active",
        currency=currency,
        items={"data": [_licensed_item(unit_amount, qty=1, product_name="Pro")]})


def _event(event_id, kind, obj, account=ACCOUNT):
    event = MagicMock()
    event.id = event_id
    event.type = kind
    event.account = account
    event.livemode = True
    event.data.object = obj
    return event


def _invoice(stripe_id, subscription_id, currency, amount_paid):
    return SimpleNamespace(
        id=stripe_id, subscription=subscription_id, parent=None,
        amount_paid=amount_paid, currency=currency,
        hosted_invoice_url="", invoice_pdf="",
        period_start=1775001600, period_end=1777593600,
        status_transitions=SimpleNamespace(paid_at=1775001600))


class _ForeignCurrencyCase(TestCase):

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Connected", products=["metering", "billing"],
            stripe_connected_account_id=ACCOUNT)
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_1")

    def _subscription_webhook(self, event):
        with patch("apps.subscriptions.api.endpoints.stripe") as stripe:
            stripe.Webhook.construct_event.return_value = event
            answered = self.http_client.post(
                "/api/v1/subscriptions/webhooks/stripe", data=b"{}",
                content_type="application/json", HTTP_STRIPE_SIGNATURE="v")
        self.assertEqual(answered.status_code, 200, answered.content)

    def _invoice_webhook(self, event):
        """The connector's webhook view, driven as its own module drives it."""
        from api.v1.webhooks import stripe_webhook
        with patch("api.v1.webhooks.stripe.Webhook.construct_event",
                   return_value=event):
            answered = stripe_webhook(RequestFactory().post(
                "/api/v1/webhooks/stripe/", content_type="application/json",
                HTTP_STRIPE_SIGNATURE="v"))
        self.assertEqual(answered.status_code, 200, answered.content)

    def _get(self, path):
        answered = self.http_client.get(
            path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(answered.status_code, 200, answered.content)
        return answered.json()

    def _economics(self, measures):
        query = "&".join(f"measures={m}" for m in measures)
        return self._get(f"/api/v1/metering/analytics/economics?{query}"
                         f"&start_date={OPENS}&end_date={CLOSES}")


class AForeignSubscriptionIsKeptAndQuarantinedTest(_ForeignCurrencyCase):
    """The subscription path — the one that reaches revenue and margin."""

    def _created(self, stripe_id, currency, unit_amount, event_id=None):
        self._subscription_webhook(_event(
            event_id or f"evt_{stripe_id}", "customer.subscription.created",
            _subscription(stripe_id, self.customer, currency, unit_amount)))
        return StripeSubscription.objects.get(stripe_subscription_id=stripe_id)

    def test_it_is_kept_exactly_as_stripe_stated_it(self):
        mirrored = self._created("sub_eur", "eur", EUROS)

        self.assertEqual((mirrored.currency, mirrored.source_amount_minor),
                         ("eur", EUROS))
        self.assertIsNone(mirrored.amount_micros)

    def test_a_currency_ubb_cannot_represent_is_kept_too_never_refused(self):
        """No exponent to convert with, and none needed: the integer is kept as
        Stripe sent it, never scaled by the tenant's minor unit."""
        mirrored = self._created("sub_jpy", "JPY", YEN)

        self.assertEqual((mirrored.currency, mirrored.source_amount_minor),
                         ("jpy", YEN))
        self.assertIsNone(mirrored.amount_micros)

    def test_a_dollar_subscription_is_admitted_beside_it(self):
        mirrored = self._created("sub_usd", "usd", DOLLARS)

        self.assertEqual((mirrored.currency, mirrored.source_amount_minor,
                          mirrored.amount_micros),
                         ("usd", DOLLARS, DOLLARS * 10_000))

    def test_a_retry_another_event_and_the_poll_sync_add_no_second_fact(self):
        self._created("sub_eur", "eur", EUROS, event_id="evt_a")
        self._created("sub_eur", "eur", EUROS, event_id="evt_a")   # the retry
        self._subscription_webhook(_event(                          # an update
            "evt_b", "customer.subscription.updated",
            _subscription("sub_eur", self.customer, "eur", EUROS)))
        listing = MagicMock()
        listing.auto_paging_iter.return_value = [
            _subscription("sub_eur", self.customer, "eur", EUROS)]
        from apps.subscriptions.stripe.sync import sync_subscriptions
        with patch("apps.subscriptions.stripe.sync.stripe.Subscription.list",
                   return_value=listing):
            sync_subscriptions(self.tenant)

        (only,) = StripeSubscription.objects.filter(stripe_subscription_id="sub_eur")
        self.assertEqual((only.currency, only.source_amount_minor,
                          only.amount_micros), ("eur", EUROS, None))

    def test_it_is_absent_from_revenue_and_the_answer_counts_it(self):
        self._created("sub_usd", "usd", DOLLARS)
        self._created("sub_eur", "eur", EUROS)

        answer = self._economics(["customer_revenue"])

        (row,) = answer["rows"]
        (revenue,) = row["measures"]
        self.assertEqual(revenue["amount_micros"], DOLLARS * 10_000)
        self.assertEqual(answer[COUNT], 1)

    def test_a_question_that_asks_no_revenue_left_nothing_out(self):
        self._created("sub_eur", "eur", EUROS)

        self.assertEqual(self._economics(["supplier_cogs"])[COUNT], 0)

    def test_a_tenant_with_no_foreign_subscription_reads_zero_never_null(self):
        self._created("sub_usd", "usd", DOLLARS)

        answer = self._economics(["customer_revenue", "gross_margin"])

        self.assertIn(COUNT, answer)
        self.assertEqual(answer[COUNT], 0)

    def test_the_mirrors_own_read_shows_the_source_and_no_dollar_amount(self):
        self._created("sub_eur", "eur", EUROS)

        read = self._get(f"/api/v1/subscriptions/customers/{self.customer.id}"
                         f"/subscription")

        self.assertEqual((read["currency"], read["source_amount_minor"],
                          read["amount_micros"]), ("eur", EUROS, None))


class AForeignInvoiceIsKeptAndQuarantinedTest(_ForeignCurrencyCase):
    """The invoice path, and its poller repair."""

    def setUp(self):
        super().setUp()
        self.subscription = a_mirrored_subscription(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription_id="sub_1", stripe_product_name="Pro",
            status="active", amount_micros=None, currency="eur",
            source_amount_minor=EUROS, interval="month",
            current_period_start=datetime(2026, 4, 1, tzinfo=dt_timezone.utc),
            current_period_end=datetime(2026, 5, 1, tzinfo=dt_timezone.utc),
            last_synced_at=datetime(2026, 4, 1, tzinfo=dt_timezone.utc))

    def _paid(self, event_id, currency="eur", amount=EUROS,
              invoice_id="in_eur"):
        self._invoice_webhook(_event(
            event_id, "invoice.paid", _invoice(invoice_id, "sub_1", currency,
                                               amount)))
        return SubscriptionInvoice.objects.get(stripe_invoice_id=invoice_id)

    def test_it_is_kept_exactly_as_stripe_stated_it(self):
        stored = self._paid("evt_1")

        self.assertEqual((stored.currency, stored.source_amount_paid_minor),
                         ("eur", EUROS))
        self.assertIsNone(stored.amount_paid_micros)

    def test_a_retry_a_second_event_and_the_poller_repair_add_no_second_fact(self):
        self._paid("evt_1")
        self._paid("evt_1")                                         # the retry
        self._invoice_webhook(_event(                               # another one
            "evt_2", "invoice.finalized",
            _invoice("in_eur", "sub_1", "eur", EUROS)))
        from apps.subscriptions.ports import repair_subscription_invoice
        repair_subscription_invoice(self.tenant, "in_eur",
                                    _invoice("in_eur", "sub_1", "eur", EUROS),
                                    "paid")

        (only,) = SubscriptionInvoice.objects.filter(stripe_invoice_id="in_eur")
        self.assertEqual((only.currency, only.source_amount_paid_minor,
                          only.amount_paid_micros), ("eur", EUROS, None))

    def test_the_revenue_listing_shows_the_source_and_no_dollar_amount(self):
        self._paid("evt_1")

        (listed,) = self._get(f"/api/v1/subscriptions/customers/"
                              f"{self.customer.id}/invoices")["data"]

        self.assertEqual((listed["currency"], listed["source_amount_paid_minor"],
                          listed["amount_paid_micros"]), ("eur", EUROS, None))

    def test_a_dollar_invoice_beside_it_is_admitted(self):
        stored = self._paid("evt_usd", currency="usd", amount=DOLLARS,
                            invoice_id="in_usd")

        self.assertEqual(stored.amount_paid_micros, DOLLARS * 10_000)


def _mirrored(customer, stripe_id, currency, minor):
    """A mirrored subscription as `mirrored_amounts` writes one. The routes
    above prove the ingress; the margin reads below need only the rows."""
    stamp = datetime(2026, 4, 1, tzinfo=dt_timezone.utc)
    return a_mirrored_subscription(
        tenant=customer.tenant, customer=customer, stripe_subscription_id=stripe_id,
        stripe_product_name="Pro", status="active", currency=currency,
        source_amount_minor=minor,
        amount_micros=minor * 10_000 if currency == "usd" else None,
        interval="month", current_period_start=stamp,
        current_period_end=stamp + timedelta(days=30), last_synced_at=stamp)


class AMarginThatLeftForeignRevenueOutConcludesNothingTest(_ForeignCurrencyCase):
    """No authoritative "unprofitable" over revenue UBB could not count (#564;
    the owner's review of #619).

    A known US-dollar cost, a margin that reads negative in dollars, and a
    subscription Stripe holds in euros: the euro revenue is unknown in dollars,
    not zero, so the margin is a subtotal and no alarm may be raised on it. The
    control is the same customer with no euro subscription, which IS flagged —
    so the fixture is unprofitable, and only the quarantine stops the verdict.
    """

    def setUp(self):
        super().setUp()
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=OPENS,
            period_end=CLOSES + timedelta(days=1),
            total_provider_cost_micros=30_000_000, total_billed_cost_micros=5_000_000,
            posting_count=3)

    def _evaluated(self):
        from apps.subscriptions.economics.services import MarginService
        econ = MarginService.snapshot_customer(
            self.tenant.id, self.customer.id, OPENS, CLOSES + timedelta(days=1))
        MarginService.evaluate_and_emit(econ)
        econ.refresh_from_db()
        return econ

    def _alarms(self):
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.schemas import CustomerUnprofitable
        return OutboxEvent.objects.filter(
            event_type=CustomerUnprofitable.EVENT_TYPE, tenant_id=self.tenant.id)

    def test_known_cost_negative_margin_and_euro_revenue_raise_no_alarm(self):
        _mirrored(self.customer, "sub_eur", "eur", EUROS)

        econ = self._evaluated()

        self.assertLess(econ.margin_percentage, 0)  # the dollar subtotal is negative
        self.assertEqual(econ.foreign_currency_subscription_count, 1)
        self.assertFalse(econ.is_unprofitable)
        self.assertFalse(self._alarms().exists())
        self.assertEqual(
            self._get(f"/api/v1/margin/unprofitable?period_start={OPENS}")["customers"], [])

    def test_the_same_customer_with_nothing_left_out_is_flagged(self):
        """THE CONTROL: the fixture is unprofitable, so the alarm fires when
        nothing in the scope was quarantined."""
        econ = self._evaluated()

        self.assertTrue(econ.is_unprofitable)
        self.assertEqual(self._alarms().count(), 1)


class TheMarginReadsCountWhatTheyLeftOutTest(_ForeignCurrencyCase):
    """Every margin read whose revenue a foreign subscription would change
    says how many it left out — exact, scoped like its figures, 0 not null."""

    def setUp(self):
        super().setUp()
        self.business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="allocated")
        self.seat = Customer.objects.create(
            tenant=self.tenant, external_id="alice", account_type="seat",
            parent=self.business)

    def _business_margin(self):
        # This route reads its end date as exclusive: the day after April.
        return self._get(f"/api/v1/margin/business/biz"
                         f"?start_date={OPENS}&end_date={date(2026, 5, 1)}")

    def test_the_business_rollup_counts_its_seats_and_its_own(self):
        _mirrored(self.seat, "sub_seat_usd", "usd", DOLLARS)
        _mirrored(self.seat, "sub_seat_eur", "eur", EUROS)
        _mirrored(self.business, "sub_biz_jpy", "jpy", YEN)

        body = self._business_margin()

        (seat,) = body["seats"]
        self.assertEqual(seat[COUNT], 1)
        self.assertEqual(seat["subscription_revenue_micros"], DOLLARS * 10_000)
        self.assertEqual(body["totals"][COUNT], 2)
        self.assertEqual(body["totals"]["subscription_revenue_micros"],
                         DOLLARS * 10_000)

    def test_a_rollup_that_left_nothing_out_reads_zero(self):
        _mirrored(self.seat, "sub_seat_usd", "usd", DOLLARS)

        body = self._business_margin()

        self.assertEqual((body["seats"][0][COUNT], body["totals"][COUNT]), (0, 0))

    def test_the_unprofitable_list_carries_the_count_its_flag_was_raised_on(self):
        from apps.subscriptions.economics.models import CustomerEconomics
        from apps.subscriptions.economics.services import MarginService
        _mirrored(self.seat, "sub_seat_eur", "eur", EUROS)
        econ = MarginService.snapshot_customer(
            self.tenant.id, self.seat.id, OPENS, CLOSES + timedelta(days=1))
        self.assertEqual((econ.subscription_revenue_micros,
                          econ.foreign_currency_subscription_count), (0, 1))
        CustomerEconomics.objects.filter(pk=econ.pk).update(is_unprofitable=True)

        (row,) = self._get(f"/api/v1/margin/unprofitable?period_start={OPENS}")[
            "customers"]

        self.assertEqual(row[COUNT], 1)
