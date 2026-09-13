"""Metering's read behind Stops and breaches (#465, slice 6 §14): every
posting the stop-context tagging marked, as plain rows the composition layer
buckets into episodes — with the Charge a projected posting came from, so a
pool episode can name the Charge that crossed it and that Charge's posting
(#153 §10.2) rather than an arbitrary event.
"""
import uuid

from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import Charge
from apps.metering.queries import charge_that_reached, stop_context_postings
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task
from core.vocabulary import (
    COSTING_STATUS_KNOWN, PRICING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN,
    TASK_STATUS_COMPLETED,
    USAGE_EVENT_KIND_TASK_CHARGE)


class StopContextPostingsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _posting(self, *, context, customer=None, effective_at=None, **columns):
        customer = customer or self.customer
        columns.setdefault("billed_cost_micros", 1_000)
        columns.setdefault("provider_cost_micros", 500)
        return Posting.objects.create(
            tenant=self.tenant, customer=customer, idempotency_key=str(uuid.uuid4()),
            effective_at=effective_at or timezone.now(),
            billing_owner_id=customer.id, stop_context=context, **columns)

    def test_only_tagged_postings_are_listed_with_their_context_and_both_pairs(self):
        tagged = self._posting(context=[{"stop_scope": "task", "arrived_after": True}])
        self._posting(context=None)

        [row] = stop_context_postings(self.tenant.id)
        self.assertEqual(row["event_id"], str(tagged.id))
        self.assertEqual(row["customer_id"], str(self.customer.id))
        self.assertEqual(row["billing_owner_id"], str(self.customer.id))
        self.assertEqual(row["effective_at"], tagged.effective_at)
        self.assertEqual(row["billed_cost_micros"], 1_000)
        self.assertEqual(row["pricing_status"], tagged.pricing_status)
        self.assertEqual(row["provider_cost_micros"], 500)
        self.assertEqual(row["costing_status"], tagged.costing_status)
        self.assertEqual(row["stop_context"], tagged.stop_context)
        self.assertIsNone(row["charge_id"])

    def test_a_projected_posting_names_the_charge_it_came_from(self):
        work = Task.objects.create(
            tenant=self.tenant, customer=self.customer, balance_snapshot_micros=0,
            status=TASK_STATUS_COMPLETED, completed_at=timezone.now())
        charge = Charge.objects.create(
            tenant=self.tenant, task=work, amount_micros=8_000_000, currency="usd",
            agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=work.created_at, charged_at=work.completed_at,
            idempotency_key=str(uuid.uuid4()))
        projected = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key=charge.idempotency_key, kind=USAGE_EVENT_KIND_TASK_CHARGE,
            billed_cost_micros=8_000_000, pricing_status=PRICING_STATUS_KNOWN,
            provider_cost_micros=0, costing_status=COSTING_STATUS_KNOWN,
            task=work, effective_at=work.completed_at, billing_owner_id=self.customer.id,
            stop_context=[{"stop_scope": "customer", "arrived_after": False}])

        [row] = stop_context_postings(self.tenant.id)
        self.assertEqual(row["event_id"], str(projected.id))
        self.assertEqual(row["charge_id"], str(charge.id))

    def test_the_customer_filter_and_the_window_each_narrow(self):
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        early = timezone.now() - timezone.timedelta(days=2)
        mine = self._posting(context=[{"stop_scope": "task"}], effective_at=early)
        theirs = self._posting(context=[{"stop_scope": "task"}], customer=other)

        def ids(**filters):
            return [r["event_id"] for r in stop_context_postings(self.tenant.id, **filters)]

        self.assertEqual(ids(), [str(mine.id), str(theirs.id)])
        self.assertEqual(ids(customer_id=other.id), [str(theirs.id)])
        self.assertEqual(ids(since=theirs.effective_at), [str(theirs.id)])
        self.assertEqual(ids(until=theirs.effective_at), [str(mine.id)])


class ChargeThatReachedTest(TestCase):
    """The drawdown replayed up to an instant: the first posting at which the
    customer's resolved period charges reach a pool's stop line."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _posting(self, amount, *, customer=None, owner=None, status=PRICING_STATUS_KNOWN):
        customer = customer or self.customer
        return Posting.objects.create(
            tenant=self.tenant, customer=customer, idempotency_key=str(uuid.uuid4()),
            effective_at=timezone.now(), billed_cost_micros=amount,
            pricing_status=status, billing_owner_id=(owner or customer).id)

    def test_the_first_posting_to_reach_the_line_is_the_charge_that_crossed(self):
        self._posting(3_000_000)
        crossing = self._posting(3_000_000)
        self._posting(3_000_000)

        found = charge_that_reached(self.tenant.id, self.customer.id,
                                    stop_threshold_micros=5_000_000, at=timezone.now())
        self.assertEqual(found["event_id"], str(crossing.id))
        self.assertIsNone(found["charge_id"])
        self.assertEqual(found["billed_cost_micros"], 3_000_000)

    def test_an_unresolved_price_is_never_summed_as_zero_and_a_line_not_reached_is_none(self):
        self._posting(None, status=PRICING_STATUS_UNKNOWN)
        self._posting(4_000_000)
        self.assertIsNone(charge_that_reached(
            self.tenant.id, self.customer.id, stop_threshold_micros=5_000_000,
            at=timezone.now()))

    def test_a_business_is_reached_by_its_seats_charges(self):
        business = Customer.objects.create(tenant=self.tenant, external_id="biz")
        seat = Customer.objects.create(tenant=self.tenant, external_id="seat")
        self._posting(6_000_000, customer=seat, owner=business)
        found = charge_that_reached(self.tenant.id, business.id,
                                    stop_threshold_micros=5_000_000, at=timezone.now())
        self.assertEqual(found["customer_id"], str(seat.id))

    def test_nothing_recorded_after_the_instant_counts(self):
        before = timezone.now()
        self._posting(6_000_000)
        self.assertIsNone(charge_that_reached(
            self.tenant.id, self.customer.id, stop_threshold_micros=5_000_000, at=before))
