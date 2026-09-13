"""Stops and breaches and Utilisation and headroom exist on the wire, at
their own prefix (#465, slice 6 §14; Testing Decisions claims 13 and 14).

Driven through the real routes — the recording route trips a ceiling and the
wallet floor on the live lane, a delivered fixed-price unit's Charge crosses
a pool on the durable drawdown, the credit route clears the floors — and
read back through `GET /api/v1/spend-controls/…`, the composition layer's
join of three products' read contracts.

WHAT "UNGATED" IS PROVED AGAINST (the lifecycle module's shape, ADR-0011
§1): a metering-only tenant, a billing tenant, and the tenant a product gate
would actually refuse — one that does not meter, written through the
queryset because `Tenant.clean` refuses to author it — each answer 200, with
the metering-gated task analytics report on the same row as the control.
"""
import json
import uuid
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import Client, TestCase

from apps.billing.gating.models import CustomerSpendPool
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.metering.pricing.models import Charge
from apps.metering.pricing.tests._helpers import (
    a_price_for_whole_work, a_rule_that_prices_what_it_measures, what_it_bills)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import UsageRecorded
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work import reasons
from apps.platform.work.models import Task, TaskType
from apps.platform.work.services import TaskService
from core.vocabulary import (
    CEILING_BASIS_COST, CEILING_STATUS_CEILING_REACHED,
    CEILING_STATUS_INDETERMINATE, CEILING_STATUS_NOT_APPLICABLE,
    CEILING_STATUS_WITHIN_CEILING, CONTROL_FAMILY_ADMISSION_CONTROL,
    CONTROL_FAMILY_CEILING, CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
    CONTROL_FAMILY_WALLET_POLICY, PRICING_MODE_FIXED,
    SPEND_POOL_ENFORCE_MODE_BLOCKING, TASK_OUTCOME_DELIVERED,
    TASK_STATUS_KILLED, TASK_TYPE_KIND_TASK, TRIGGER_SOURCE_USAGE_INGEST)
from apps.platform.customers.models import ACCOUNT_TYPE_BUSINESS, ACCOUNT_TYPE_SEAT

STOPS = "/api/v1/spend-controls/stops-and-breaches"
UTILISATION = "/api/v1/spend-controls/utilisation-and-headroom"
DOORBELL = "apps.platform.events.tasks.process_single_event"
FLOOR = 5_000_000
SOFT = 2_000_000
SOLD_WHOLE = "transcode"
THE_AGREED_PRICE = 8_000_000


def _wire(instant):
    """An instant as the response renders it — millisecond precision, `Z`."""
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SpendControlReportsTestBase(TestCase):
    PRODUCTS = ["metering", "billing"]
    BILLING_MODE = "prepaid"
    WALLET = 20_000_000

    def setUp(self):
        cache.clear()
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Reports", products=self.PRODUCTS, billing_mode=self.BILLING_MODE,
            enforcement_mode="enforcing")
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        if "billing" in self.PRODUCTS:
            Wallet.objects.create(customer=self.customer, balance_micros=self.WALLET)
            CustomerBillingProfile.objects.create(
                customer=self.customer, min_balance_micros=FLOOR,
                soft_min_balance_micros=SOFT)
        declares_a_caller_supplied_cost(self.tenant, DECLARED)
        a_rule_that_prices_what_it_measures(self.tenant)
        self._drained = set()

    def tearDown(self):
        cache.clear()

    def _headers(self):
        return {"content_type": "application/json",
                "HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _unit(self, ceiling=10_000_000, customer=None, task_type="", parent=None):
        customer = customer or self.customer
        return TaskService.create_task(
            self.tenant, customer, balance_snapshot_micros=self.WALLET,
            task_cogs_ceiling_micros=ceiling, task_type=task_type,
            billing_owner_id=customer.id, parent=parent)

    def _record(self, *, bills, customer=None, task_id=None, **extra):
        data = {"customer_id": str((customer or self.customer).id),
                "idempotency_key": f"idem-{uuid.uuid4()}",
                "event_type": DECLARED, "provider_cost_micros": 1_000_000}
        if task_id is not None:
            data["task_id"] = str(task_id)
        data.update(what_it_bills({"bills": bills}))
        data.update(extra)
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            response = self.http.post("/api/v1/metering/usage",
                                      data=json.dumps(data), **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _drain(self):
        rows = (OutboxEvent.objects.filter(event_type=UsageRecorded.EVENT_TYPE,
                                           tenant_id=self.tenant.id)
                .exclude(id__in=self._drained))
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            for row in rows.order_by("created_at"):
                handle_usage_recorded_billing(str(row.id), row.payload)
                self._drained.add(row.id)

    def _credit(self, amount):
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            response = self.http.post("/api/v1/billing/credit", data=json.dumps({
                "customer_id": self.customer.external_id, "amount_micros": amount,
                "source": "test", "reference": "r1",
                "idempotency_key": f"c-{uuid.uuid4()}"}), **self._headers())
        self.assertEqual(response.status_code, 200, response.content)

    def _get(self, path, query=""):
        return self.http.get(path + query, **self._headers())

    def _report(self, path=STOPS, query=""):
        response = self._get(path, query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _rows(self, query="", family=None):
        rows = self._report(STOPS, query)["rows"]
        return [r for r in rows if family is None or r["control_family"] == family]

    def _a_pooled_business_and_its_seat(self):
        """A business whose seats' charges are its own, and one seat of it."""
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type=ACCOUNT_TYPE_BUSINESS,
            billing_topology="pooled")
        Wallet.objects.create(customer=business, balance_micros=self.WALLET)
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type=ACCOUNT_TYPE_SEAT,
            parent=business)
        return business, seat


class ACeilingEpisodeTest(SpendControlReportsTestBase):
    def test_a_ceiling_row_is_explained_by_its_unit_and_the_events_after_the_stop(self):
        unit = self._unit(ceiling=10_000_000, task_type="pipeline")
        tip = self._record(bills=6_000_000, task_id=unit.id,
                           provider_cost_micros=11_000_000)
        late = self._record(bills=3_000_000, task_id=unit.id,
                            provider_cost_micros=2_000_000)
        unit.refresh_from_db()
        self.assertEqual(unit.status, TASK_STATUS_KILLED)

        [row] = self._rows()
        self.assertEqual(row["control_family"], CONTROL_FAMILY_CEILING)
        self.assertEqual(row["reason_code"], reasons.TASK_COGS_CEILING)
        self.assertEqual(row["ceiling_basis"], CEILING_BASIS_COST)
        self.assertEqual(row["trigger_source"], TRIGGER_SOURCE_USAGE_INGEST)
        self.assertEqual(row["control_id"], str(self.tenant.id))
        self.assertEqual(row["task_id"], str(unit.id))
        self.assertIsNone(row["parent_task_id"])
        self.assertEqual(row["customer_id"], str(self.customer.id))
        self.assertEqual(row["task_type"], "pipeline")
        self.assertEqual(row["stop_scope"], "task")
        self.assertEqual(row["task_cogs_ceiling_micros"], 10_000_000)
        # The wire carries milliseconds (Django's JSON encoder), the row
        # microseconds: compare at the wire's precision.
        self.assertEqual(row["opened_at"], _wire(unit.completed_at))
        # The pair the ceiling fired on, and the pair the unit ended on.
        self.assertEqual(row["crossed_provider_cost_micros"], 11_000_000)
        self.assertEqual(row["crossed_unresolved_event_count"], 0)
        self.assertEqual(row["final_provider_cost_micros"], 13_000_000)
        self.assertEqual(row["final_unresolved_event_count"], 0)
        events = row["itemised"]["events"]
        self.assertEqual([(e["event_id"], e["arrived_after"]) for e in events],
                         [(tip["event_id"], False), (late["event_id"], True)])
        self.assertEqual(row["itemised"]["event_count"], 2)
        self.assertEqual(row["itemised"]["provider_cost_micros"], 13_000_000)
        self.assertEqual(row["itemised"]["billed_cost_micros"], 9_000_000)
        self.assertEqual(row["itemised"]["unresolved_event_count"], 0)
        self.assertEqual(row["itemised"]["unpriced_event_count"], 0)
        self.assertIsNone(events[0]["charge_id"])
        [total] = self._report()["totals"]
        self.assertEqual(total, {
            "control_family": CONTROL_FAMILY_CEILING, "event_count": 2,
            "billed_cost_micros": 9_000_000, "unpriced_event_count": 0,
            "provider_cost_micros": 13_000_000, "unresolved_event_count": 0})

    def test_an_indeterminate_ceiling_is_never_a_breach_and_an_expiry_is_neither(self):
        """TD claim 13: a unit whose known cost sits below its ceiling with
        an unresolved cost beside it is `indeterminate`, is not stopped and
        never appears; a window running out writes `expired` and appears in
        neither report either."""
        indeterminate = self._unit(ceiling=10_000_000)
        self._record(bills=1_000_000, task_id=indeterminate.id,
                     provider_cost_micros=None)
        indeterminate.refresh_from_db()
        self.assertEqual(indeterminate.ceiling_assessment.status,
                         CEILING_STATUS_INDETERMINATE)
        expired = self._unit(ceiling=10_000_000)
        TaskService.expire_and_announce(
            expired.id, reasons.ABSOLUTE_DEADLINE, tenant_id=self.tenant.id,
            customer_id=self.customer.id, control_id=str(self.tenant.id))

        self.assertEqual(self._rows(), [])
        self.assertEqual(self._rows(f"?control_family={CONTROL_FAMILY_ADMISSION_CONTROL}"), [])


class AWalletPolicyEpisodeTest(SpendControlReportsTestBase):
    def test_a_hard_floor_row_itemises_its_events_and_a_soft_floor_row_is_a_marker(self):
        # 20M - 26M = -6M: past the hard floor's line (-5M) on the live lane;
        # the soft floor's only detector is the durable drawdown.
        crossing = self._record(bills=26_000_000)
        late = self._record(bills=1_000_000)
        self._drain()
        self._credit(30_000_000)

        by_kind = {(r["soft_floor"]): r
                   for r in self._rows(family=CONTROL_FAMILY_WALLET_POLICY)}
        hard, soft = by_kind[False], by_kind[True]
        self.assertEqual(hard["reason_code"], reasons.HARD_FLOOR)
        self.assertEqual(hard["customer_id"], str(self.customer.id))
        self.assertEqual(hard["episode_seq"], 1)
        self.assertEqual(hard["control_id"],
                         str(CustomerBillingProfile.objects.get(customer=self.customer).id))
        self.assertEqual(hard["floor_micros"], FLOOR)
        self.assertEqual(hard["balance_at_crossing_micros"], -6_000_000)
        self.assertIsNotNone(hard["opened_at"])
        self.assertIsNotNone(hard["closed_at"])
        self.assertEqual([(e["event_id"], e["arrived_after"])
                          for e in hard["itemised"]["events"]],
                         [(crossing["event_id"], False), (late["event_id"], True)])
        self.assertEqual(hard["itemised"]["billed_cost_micros"], 27_000_000)
        self.assertIsNone(soft["reason_code"])
        self.assertIsNone(soft["control_id"])
        self.assertEqual(soft["floor_micros"], SOFT)
        self.assertEqual(soft["itemised"]["events"], [])
        self.assertEqual(soft["itemised"]["event_count"], 0)
        self.assertIsNotNone(soft["closed_at"])
        [total] = self._report()["totals"]
        self.assertEqual(total["control_family"], CONTROL_FAMILY_WALLET_POLICY)
        self.assertEqual(total["event_count"], 2)


class ACustomerSpendPoolEpisodeTest(SpendControlReportsTestBase):
    WALLET = 100_000_000

    def setUp(self):
        super().setUp()
        TaskType.objects.create(tenant=self.tenant, key=SOLD_WHOLE,
                                kind=TASK_TYPE_KIND_TASK,
                                pricing_mode=PRICING_MODE_FIXED, uncapped=True)
        a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                               amount_micros=THE_AGREED_PRICE)
        self.pool = CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.customer, cap_micros=THE_AGREED_PRICE,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)

    def _start(self, **body):
        body.setdefault("customer_id", str(self.customer.id))
        body.setdefault("idempotency_key", f"attempt-{uuid.uuid4()}")
        response = self.http.post("/api/v1/tasks", data=json.dumps(body), **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["task_id"]

    def _close(self, unit):
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            response = self.http.post(
                f"/api/v1/tasks/{unit}/close",
                data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}), **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_a_pool_row_is_explained_by_its_charge_and_that_charges_posting(self):
        """TD claim 13: the delivered unit's Charge reaches the pool through
        its projection and the drawdown — off the recording route, so no
        stop-context marks it — and the row still names that Charge and its
        posting, never an arbitrary event; the active unit the crossing
        swept is counted as the outcome."""
        running = self._start()
        delivered = self._start(task_type=SOLD_WHOLE)
        self.assertTrue(self._close(delivered)["charge_created"])
        self._drain()
        after = self._record(bills=1_000_000)
        charge = Charge.objects.get(task_id=delivered)
        projected = Posting.objects.get(idempotency_key=charge.idempotency_key)
        self.assertEqual(Task.objects.get(id=running).status, TASK_STATUS_KILLED)

        [row] = self._rows(family=CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
        self.assertEqual(row["reason_code"], reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(row["control_id"], str(self.pool.id))
        self.assertEqual(row["customer_id"], str(self.customer.id))
        self.assertEqual(row["episode_seq"], 1)
        self.assertEqual(row["cap_micros"], THE_AGREED_PRICE)
        self.assertEqual(row["period"], row["opened_at"][:7])
        self.assertIsNone(row["closed_at"])
        self.assertEqual(row["crossing_charge_id"], str(charge.id))
        self.assertEqual(row["crossing_posting_id"], str(projected.id))
        self.assertFalse(row["crossing_marked"])
        self.assertEqual(row["work_stopped_count"], 1)
        events = row["itemised"]["events"]
        self.assertEqual([(e["event_id"], e["arrived_after"], e["charge_id"]) for e in events],
                         [(str(projected.id), False, str(charge.id)),
                          (after["event_id"], True, None)])
        self.assertEqual(row["spent_after_micros"], 1_000_000)
        self.assertEqual(row["unpriced_after_count"], 0)
        self.assertEqual(row["itemised"]["billed_cost_micros"], THE_AGREED_PRICE + 1_000_000)
        # The pool's kill is never a Ceiling row.
        self.assertEqual(self._rows(family=CONTROL_FAMILY_CEILING), [])

    def test_a_crossing_the_recording_route_marked_names_the_marked_posting(self):
        unit = self._start()
        ack = self._record(bills=THE_AGREED_PRICE, task_id=unit)
        self.assertTrue(ack["stop"])

        [row] = self._rows(family=CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
        self.assertEqual(row["crossing_posting_id"], ack["event_id"])
        self.assertIsNone(row["crossing_charge_id"])
        self.assertTrue(row["crossing_marked"])
        self.assertEqual(row["work_stopped_count"], 1)

    def test_a_pooled_seats_own_pool_line_survives_the_customer_filter(self):
        """A seat's pool is declared on the seat while its floor is its
        billing owner's; asking for the seat asks for both (review pass)."""
        business, seat = self._a_pooled_business_and_its_seat()
        CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=seat, cap_micros=1_000_000,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        self._record(bills=1_000_000, customer=seat)
        self._drain()

        rows = self._rows(f"?customer_id={seat.id}", family=CONTROL_FAMILY_CUSTOMER_SPEND_POOL)
        self.assertEqual([r["customer_id"] for r in rows], [str(seat.id)])
        self.assertFalse(self._rows(f"?customer_id={business.id}",
                                    family=CONTROL_FAMILY_CUSTOMER_SPEND_POOL))


class TheFiltersTest(SpendControlReportsTestBase):
    def setUp(self):
        super().setUp()
        self.other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        Wallet.objects.create(customer=self.other, balance_micros=self.WALLET)
        self.mine = self._unit(ceiling=1_000_000, task_type="a")
        self._record(bills=1_000_000, task_id=self.mine.id, provider_cost_micros=2_000_000)
        self.theirs = self._unit(ceiling=1_000_000, task_type="b", customer=self.other)
        self._record(bills=1_000_000, task_id=self.theirs.id, customer=self.other,
                     provider_cost_micros=2_000_000)
        # The other customer also crosses its floor: 20M - 26M.
        self._record(bills=26_000_000, customer=self.other)

    def _ids(self, query=""):
        return sorted((r["control_family"], r.get("task_id") or r["customer_id"])
                      for r in self._rows(query))

    def test_each_filter_narrows(self):
        everything = self._ids()
        self.assertEqual(everything, sorted([
            (CONTROL_FAMILY_CEILING, str(self.mine.id)),
            (CONTROL_FAMILY_CEILING, str(self.theirs.id)),
            (CONTROL_FAMILY_WALLET_POLICY, str(self.other.id))]))
        self.assertEqual(self._ids(f"?customer_id={self.other.id}"), sorted([
            (CONTROL_FAMILY_CEILING, str(self.theirs.id)),
            (CONTROL_FAMILY_WALLET_POLICY, str(self.other.id))]))
        self.assertEqual(self._ids("?task_type=a"),
                         [(CONTROL_FAMILY_CEILING, str(self.mine.id))])
        self.assertEqual(self._ids(f"?control_family={CONTROL_FAMILY_WALLET_POLICY}"),
                         [(CONTROL_FAMILY_WALLET_POLICY, str(self.other.id))])
        self.assertEqual(self._ids(f"?control_family={CONTROL_FAMILY_CUSTOMER_SPEND_POOL}"), [])
        self.assertEqual(self._ids("?since=2099-01-01T00:00:00Z&until=2099-02-01T00:00:00Z"), [])
        self.assertEqual(self._ids("?until=2000-01-01T00:00:00Z"), [])

    def test_a_business_filter_itemises_every_seats_events_and_the_window_keeps_them(self):
        """The business's floor episode is explained by the SEAT's events
        tagged into it, and a window that selects the episode keeps every
        event of it, even one that landed after `until` (review pass)."""
        business, seat = self._a_pooled_business_and_its_seat()
        CustomerBillingProfile.objects.create(customer=business, min_balance_micros=FLOOR)
        crossing = self._record(bills=26_000_000, customer=seat)
        late = self._record(bills=1_000_000, customer=seat)

        [row] = self._rows(f"?customer_id={business.id}", family=CONTROL_FAMILY_WALLET_POLICY)
        self.assertEqual(row["customer_id"], str(business.id))
        self.assertEqual([e["event_id"] for e in row["itemised"]["events"]],
                         [crossing["event_id"], late["event_id"]])
        # The window selects the episode; the episode keeps its events — the
        # tipping event landed an instant BEFORE the episode opened, so a
        # window starting at the opening would have dropped it under a
        # window on the events themselves.
        [again] = self._rows(f"?customer_id={business.id}&since={row['opened_at']}",
                             family=CONTROL_FAMILY_WALLET_POLICY)
        self.assertEqual(again["itemised"]["event_count"], 2)

    def test_the_totals_cover_exactly_the_rows_shown(self):
        report = self._report(STOPS, f"?control_family={CONTROL_FAMILY_CEILING}")
        self.assertEqual([t["control_family"] for t in report["totals"]],
                         [CONTROL_FAMILY_CEILING])
        self.assertEqual(report["totals"][0]["event_count"], 2)
        self.assertEqual(self._report(STOPS, "?until=2000-01-01T00:00:00Z")["totals"], [])

    def test_the_window_is_bounded_and_echoed(self):
        report = self._report(STOPS)
        self.assertIn("since", report)
        self.assertIn("until", report)
        stated = self._report(STOPS, "?since=2026-01-01T00:00:00Z&until=2026-02-01T00:00:00Z")
        self.assertEqual(stated["since"], "2026-01-01T00:00:00Z")
        self.assertEqual(stated["until"], "2026-02-01T00:00:00Z")
        for query in ("?since=2026-02-01T00:00:00Z&until=2026-01-01T00:00:00Z",
                      "?since=2024-01-01T00:00:00Z&until=2026-01-01T00:00:00Z"):
            for path in (STOPS, UTILISATION):
                response = self._get(path, query)
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "validation_error")

    def test_an_unknown_family_and_an_unknown_customer_are_refused(self):
        self.assertEqual(self._get(STOPS, "?control_family=nope").status_code, 422)
        self.assertEqual(self._get(STOPS, f"?customer_id={uuid.uuid4()}").status_code, 404)


class UtilisationAndHeadroomTest(SpendControlReportsTestBase):
    def test_the_average_is_per_unit_then_across_every_unit(self):
        """TD claim 13: one chatty unit (ten events, 90% used) and one quiet
        unit (one event, 10% used) average 50 — each unit weighs one, so the
        chatty one does not dominate; the reached count and the indeterminate
        count equal the count of work whose status at completion was that."""
        chatty = self._unit(ceiling=10_000_000)
        for _ in range(9):
            self._record(bills=100_000, task_id=chatty.id, provider_cost_micros=1_000_000)
        quiet = self._unit(ceiling=10_000_000)
        self._record(bills=100_000, task_id=quiet.id, provider_cost_micros=1_000_000)
        reached = self._unit(ceiling=1_000_000)
        self._record(bills=100_000, task_id=reached.id, provider_cost_micros=2_000_000)
        indeterminate = self._unit(ceiling=10_000_000)
        self._record(bills=100_000, task_id=indeterminate.id, provider_cost_micros=None)
        uncapped = self._unit(ceiling=None)
        still_running = self._unit(ceiling=10_000_000)
        for unit in (chatty, quiet, indeterminate, uncapped):
            response = self.http.post(
                f"/api/v1/tasks/{unit.id}/close",
                data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}), **self._headers())
            self.assertEqual(response.status_code, 200, response.content)

        report = self._report(UTILISATION)
        rows = {r["task_id"]: r for r in report["rows"]}
        self.assertNotIn(str(still_running.id), rows)
        self.assertEqual(rows[str(chatty.id)]["ceiling_used_percentage"], 90)
        self.assertEqual(rows[str(chatty.id)]["ceiling_remaining_micros"], 1_000_000)
        self.assertEqual(rows[str(chatty.id)]["ceiling_status"], CEILING_STATUS_WITHIN_CEILING)
        self.assertEqual(rows[str(quiet.id)]["ceiling_used_percentage"], 10)
        self.assertEqual(rows[str(reached.id)]["ceiling_status"], CEILING_STATUS_CEILING_REACHED)
        self.assertEqual(rows[str(reached.id)]["ceiling_used_percentage"], 200)
        self.assertEqual(rows[str(reached.id)]["ceiling_remaining_micros"], 0)
        self.assertEqual(rows[str(indeterminate.id)]["ceiling_status"],
                         CEILING_STATUS_INDETERMINATE)
        self.assertEqual(rows[str(indeterminate.id)]["final_unresolved_event_count"], 1)
        self.assertEqual(rows[str(uncapped.id)]["ceiling_status"], CEILING_STATUS_NOT_APPLICABLE)
        self.assertIsNone(rows[str(uncapped.id)]["ceiling_used_percentage"])
        self.assertIsNone(rows[str(uncapped.id)]["ceiling_remaining_micros"])
        self.assertIsNone(rows[str(uncapped.id)]["task_cogs_ceiling_micros"])
        self.assertEqual(report["unit_count"], 5)
        self.assertEqual(report["evaluated_count"], 4)
        self.assertEqual(report["not_applicable_count"], 1)
        self.assertEqual(report["ceiling_reached_count"], 1)
        self.assertEqual(report["ceiling_reached_share_percentage"], 20)
        self.assertEqual(report["indeterminate_count"], 1)
        self.assertEqual(report["indeterminate_share_percentage"], 20)
        self.assertEqual(report["within_ceiling_count"], 2)
        # (90 + 10 + 200 + 0) // 4 = 75: per unit, then across every unit
        # that had a ceiling — the chatty unit weighs exactly one.
        self.assertEqual(report["average_final_utilisation_percentage"], 75)
        # The indeterminate unit's known total is nothing (its one cost is
        # unresolved), so its headroom is the whole ceiling — a floor, as the
        # status beside it says: (1M + 9M + 0 + 10M) // 4.
        self.assertEqual(report["average_unused_headroom_micros"],
                         (1_000_000 + 9_000_000 + 0 + 10_000_000) // 4)
        self.assertIsNone(report["customer_spend_pool"])

    def test_a_null_is_never_coerced_to_zero(self):
        uncapped = self._unit(ceiling=None)
        response = self.http.post(
            f"/api/v1/tasks/{uncapped.id}/close",
            data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}), **self._headers())
        self.assertEqual(response.status_code, 200, response.content)

        report = self._report(UTILISATION)
        self.assertEqual(report["unit_count"], 1)
        self.assertEqual(report["evaluated_count"], 0)
        self.assertIsNone(report["average_final_utilisation_percentage"])
        self.assertIsNone(report["average_unused_headroom_micros"])
        self.assertEqual(report["ceiling_reached_share_percentage"], 0)
        empty = self._report(UTILISATION, "?until=2000-01-01T00:00:00Z")
        self.assertEqual(empty["unit_count"], 0)
        self.assertIsNone(empty["ceiling_reached_share_percentage"])
        self.assertIsNone(empty["indeterminate_share_percentage"])

    def test_the_pool_status_pair_rides_beside_the_rows_for_a_named_customer(self):
        CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.customer, cap_micros=10_000_000,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        self._record(bills=2_500_000)

        pool = self._report(UTILISATION, f"?customer_id={self.customer.id}")["customer_spend_pool"]
        self.assertEqual(pool["cap_micros"], 10_000_000)
        self.assertEqual(pool["known_period_charges_micros"], 2_500_000)
        self.assertEqual(pool["unresolved_posting_count"], 0)
        self.assertEqual(pool["used_percentage"], 25)
        self.assertEqual(pool["remaining_micros"], 7_500_000)
        self.assertFalse(pool["blocking_occurred"])
        self.assertIsNone(self._report(UTILISATION)["customer_spend_pool"])
        other = Customer.objects.create(tenant=self.tenant, external_id="no-pool")
        self.assertIsNone(self._report(
            UTILISATION, f"?customer_id={other.id}")["customer_spend_pool"])


class TheTaskAnalyticsRowLostItsReachedCountTest(SpendControlReportsTestBase):
    def test_claim_14_in_both_directions(self):
        unit = self._unit(ceiling=1_000_000, task_type="a")
        self._record(bills=1_000_000, task_id=unit.id, provider_cost_micros=2_000_000)
        rows = self._report("/api/v1/metering/analytics/tasks", "?group_by=task_type")["rows"]
        self.assertEqual(len(rows), 1)
        self.assertNotIn("limit_hit_count", rows[0])
        self.assertEqual(self._report(UTILISATION)["ceiling_reached_count"], 1)


@pytest.mark.django_db
class TestBothReadsAreUngated:
    """Ungated, proved against three postures (ADR-0011 §1's shape)."""

    def _tenant(self, products):
        tenant = Tenant.objects.create(name="T", products=products)
        _, raw_key = TenantApiKey.create_key(tenant)
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        unit = TaskService.create_task(
            tenant, customer, balance_snapshot_micros=0, task_cogs_ceiling_micros=1,
            billing_owner_id=customer.id)
        Task.objects.filter(id=unit.id).update(total_provider_cost_micros=2)
        assert TaskService.kill_and_announce(
            unit.id, reasons.TASK_COGS_CEILING, tenant_id=tenant.id,
            customer_id=customer.id, trigger_source=TRIGGER_SOURCE_USAGE_INGEST,
            control_id=str(tenant.id))
        return tenant, {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}

    def _families(self, headers):
        response = Client().get(STOPS, **headers)
        assert response.status_code == 200, response.content
        return sorted({r["control_family"] for r in response.json()["rows"]})

    def test_a_metering_only_tenant_gets_ceiling_rows_and_empty_money_families(self):
        tenant, headers = self._tenant(["metering"])
        assert self._families(headers) == [CONTROL_FAMILY_CEILING]
        for family in (CONTROL_FAMILY_CUSTOMER_SPEND_POOL, CONTROL_FAMILY_WALLET_POLICY):
            response = Client().get(STOPS, {"control_family": family}, **headers)
            assert response.status_code == 200
            assert response.json()["rows"] == []
        assert Client().get(UTILISATION, **headers).status_code == 200

    def test_a_billing_tenant_reaches_both(self):
        tenant, headers = self._tenant(["metering", "billing"])
        assert self._families(headers) == [CONTROL_FAMILY_CEILING]
        assert Client().get(UTILISATION, **headers).status_code == 200

    def test_a_tenant_that_does_not_meter_reaches_both_while_the_gated_report_refuses_it(self):
        tenant, headers = self._tenant(["metering"])
        Tenant.objects.filter(id=tenant.id).update(products=["billing"])
        assert self._families(headers) == [CONTROL_FAMILY_CEILING]
        assert Client().get(UTILISATION, **headers).status_code == 200
        assert Client().get("/api/v1/metering/analytics/tasks", **headers).status_code == 403
