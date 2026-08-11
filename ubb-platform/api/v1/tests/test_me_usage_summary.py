"""GET /api/v1/me/usage-summary — month-to-date rollup for end customers (F5.1)."""
import datetime

from django.test import TestCase, Client
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import Posting
from core.widget_auth import create_widget_token


class WidgetUsageSummaryTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
        )
        self.business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled",
        )
        self.seat_a = Customer.objects.create(
            tenant=self.tenant, external_id="seat-a", account_type="seat",
            parent=self.business,
        )
        self.seat_b = Customer.objects.create(
            tenant=self.tenant, external_id="seat-b", account_type="seat",
            parent=self.business,
        )

    def _event(self, customer, key, *, event_type="", billed=0):
        return Posting.objects.create(
            tenant=self.tenant, customer=customer,
            request_id=f"r-{key}", idempotency_key=f"i-{key}",
            event_type=event_type, billed_cost_micros=billed,
        )

    def _get(self, customer):
        token = create_widget_token(
            self.tenant.widget_secret, str(customer.id), str(self.tenant.id))
        return self.http_client.get(
            "/api/v1/me/usage-summary", HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_seat_sees_only_its_own_rollup(self):
        self._event(self.seat_a, "a1", event_type="tokens", billed=100_000)
        self._event(self.seat_b, "b1", event_type="tokens", billed=200_000)
        resp = self._get(self.seat_a)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_billed_micros"], 100_000)
        self.assertEqual(len(body["metrics"]), 1)
        self.assertEqual(body["metrics"][0]["event_type"], "tokens")

    def test_business_token_aggregates_seats(self):
        self._event(self.seat_a, "a1", event_type="tokens", billed=100_000)
        self._event(self.seat_b, "b1", event_type="tokens", billed=200_000)
        self._event(self.seat_b, "b2", event_type="images", billed=1_000_000)
        resp = self._get(self.business)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_billed_micros"], 1_300_000)
        rows = {m["event_type"]: m for m in body["metrics"]}
        self.assertEqual(rows["tokens"]["billed_cost_micros"], 300_000)
        self.assertEqual(rows["tokens"]["event_count"], 2)

    def test_prior_month_event_excluded(self):
        self._event(self.seat_a, "now", event_type="tokens", billed=50_000)
        old = self._event(self.seat_a, "old", event_type="tokens", billed=990_000)
        first_of_month = timezone.now().date().replace(day=1)
        Posting.objects.filter(id=old.id).update(
            effective_at=timezone.now().replace(
                year=first_of_month.year, month=first_of_month.month, day=1)
            - datetime.timedelta(days=2))
        resp = self._get(self.seat_a)
        body = resp.json()
        self.assertEqual(body["total_billed_micros"], 50_000)
        self.assertEqual(body["period_start"], first_of_month.isoformat())

    def test_totals_equal_sum_of_metric_rows(self):
        self._event(self.seat_a, "1", event_type="tokens", billed=100_000)
        self._event(self.seat_a, "2", event_type="images", billed=400_000)
        self._event(self.seat_a, "3", event_type="", billed=7_000)
        body = self._get(self.seat_a).json()
        self.assertEqual(body["total_billed_micros"],
                         sum(m["billed_cost_micros"] for m in body["metrics"]))
        self.assertEqual(body["currency"], "usd")

    def test_metering_only_tenant_can_read_usage_summary(self):
        """Deliberate gate choice: usage summary is metering-scoped, not
        billing-scoped — a meter-only tenant's customers still see usage."""
        tenant = Tenant.objects.create(name="MeterOnly", products=["metering"])
        customer = Customer.objects.create(tenant=tenant, external_id="m1")
        Posting.objects.create(
            tenant=tenant, customer=customer, request_id="r", idempotency_key="i",
            event_type="tokens", billed_cost_micros=30_000)
        token = create_widget_token(
            tenant.widget_secret, str(customer.id), str(tenant.id))
        resp = self.http_client.get(
            "/api/v1/me/usage-summary", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total_billed_micros"], 30_000)

    def test_the_response_carries_money_and_counts_and_no_quantity(self):
        """#272, at the surface the ruling was decided on.

        This response is where the retirement was argued and where its reviewed
        contract break was taken — the reasoning is in the block in
        `openapi/oasdiff-err-ignore.txt`.

        Pinned as the WHOLE key set rather than as an absence, so that adding
        the field back has to come past a test that says this was decided, and
        so that a reader sees what the response actually is.
        """
        self._event(self.seat_a, "1", event_type="tokens", billed=100_000)
        body = self._get(self.seat_a).json()

        self.assertEqual(set(body), {"period_start", "period_end",
                                     "total_billed_micros", "currency",
                                     "metrics"})
        self.assertEqual(set(body["metrics"][0]),
                         {"event_type", "billed_cost_micros", "event_count"})

    def test_no_token_returns_401(self):
        resp = self.http_client.get("/api/v1/me/usage-summary")
        self.assertEqual(resp.status_code, 401)
