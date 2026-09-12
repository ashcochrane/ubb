"""The affordability question, asked at the read floor (#463, slice 6 §13;
Testing Decisions claims 8 and 9).

`GET /api/v1/billing/customers/{customer_id}/affordability` answers the
money-shaped verdict — the standing, worded by the line holding the
customer; the stop in force; the hard floor; the soft floor at the altitude
`parent_task_id` names; the pool — and nothing else. It registers no unit of
work, it moves no admission window, and the product gate refuses it to a
tenant without `billing`. Every case drives the real route and asserts what
a caller reads back; every verdict word is the registry's, asserted by
constant identity and never by a spelled string.

The module says "a unit of work" and "contained work" throughout.
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase

from api.v1.tests._helpers import (
    SOLD_PER_EVENT, SOLD_WHOLE, THE_AGREED_PRICE, a_tenant_selling_whole_work)
from apps.billing.gating.models import CustomerSpendPool
from apps.billing.gating.services.customer_spend_pool_service import (
    CustomerSpendPoolService)
from apps.billing.gating.services.stop_signal_service import StopSignalService
from apps.billing.wallets.models import CustomerBillingProfile
from apps.platform.customers.models import (
    CUSTOMER_STATUS_CLOSED, CUSTOMER_STATUS_SUSPENDED, Customer)
from apps.platform.membership.roles import READ
from apps.platform.tenants.models import TenantApiKey
from apps.platform.work import admission, reasons
from apps.platform.work.models import Task
from core.vocabulary import (
    AFFORDABILITY_REASON_ACCOUNT_CLOSED,
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
    AFFORDABILITY_REASON_INSUFFICIENT_FUNDS,
    AFFORDABILITY_REASON_SOFT_FLOOR_REACHED,
    SPEND_POOL_ENFORCE_MODE_BLOCKING)

#: A balance that affords a few whole-work starts with room to spare.
BALANCE = 3 * THE_AGREED_PRICE
#: The customer's two floors, as the billing profile states them: the allowed
#: overdraft, so the hard line sits at -HARD and the wind-down line at -SOFT.
HARD = 5_000_000
SOFT = 2_000_000
#: A balance past the wind-down line and above the hard line.
WINDING_DOWN = -3_000_000

#: Every key the answer carries — money and a verdict, never a unit of work.
THE_ANSWER = {"allowed", "reason", "balance_micros", "available_micros",
              "min_balance_micros", "soft_min_balance_micros"}


class TheAffordabilityQuestionTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.fixture = a_tenant_selling_whole_work(
            billing_mode="prepaid", enforcement_mode="enforcing",
            balance_micros=BALANCE)
        self.tenant = self.fixture.tenant
        self.customer = self.fixture.customer
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=HARD,
            soft_min_balance_micros=SOFT)

    def tearDown(self):
        cache.clear()

    # -- the seams ----------------------------------------------------------

    def _ask(self, customer=None, *, auth=None, **query):
        customer = customer or self.customer
        return self.client.get(
            f"/api/v1/billing/customers/{customer.id}/affordability",
            query, **(auth or self.fixture.auth()))

    def _answer(self, **query):
        response = self._ask(**query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _start(self, **body):
        body.setdefault("task_type", SOLD_PER_EVENT)
        response = self.client.post(
            "/api/v1/tasks", data=json.dumps(self.fixture.start_body(**body)),
            content_type="application/json", **self.fixture.auth())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["task_id"]

    def _set_balance(self, balance_micros):
        self.fixture.wallet.balance_micros = balance_micros
        self.fixture.wallet.save(update_fields=["balance_micros"])

    # -- claim 9: the read floor, the gate, and what it registers -----------

    def test_it_answers_at_the_read_floor(self):
        """A key that may only read asks it and is answered; the same key
        may not start work, which is what makes the floor a claim rather
        than a default."""
        key, raw = TenantApiKey.create_key(self.tenant, label="reader")
        key.role = READ
        key.save(update_fields=["role"])
        auth = {"HTTP_AUTHORIZATION": f"Bearer {raw}"}

        self.assertEqual(self._ask(auth=auth).status_code, 200)
        start = self.client.post(
            "/api/v1/tasks", data=json.dumps(self.fixture.start_body()),
            content_type="application/json", **auth)
        self.assertEqual(start.status_code, 403, start.content)

    def test_a_tenant_without_billing_is_refused_by_the_product_gate(self):
        """Everything the answer reports is about a wallet, and a tenant that
        does not bill through UBB has none to ask about."""
        without = a_tenant_selling_whole_work(
            products=("metering",), billing_mode=None,
            name="No wallet", external_id="c2")
        response = self._ask(without.customer, auth=without.auth())
        self.assertEqual(response.status_code, 403, response.content)

    def test_it_registers_nothing(self):
        answer = self._answer()
        self.assertTrue(answer["allowed"])
        self.assertEqual(Task.objects.count(), 0)

    def test_the_answer_names_no_unit_of_work(self):
        """The whole key set, pinned: an answer that grew a member naming a
        unit would be a registration riding back on an advisory call."""
        self.assertEqual(set(self._answer()), THE_ANSWER)

    def test_an_unknown_customer_is_not_found(self):
        stranger = Customer.objects.create(
            tenant=a_tenant_selling_whole_work(
                billing_mode="prepaid", name="Other", external_id="c3").tenant,
            external_id="c4")
        self.assertEqual(self._ask(stranger).status_code, 404)

    # -- claim 8's last clause: the window does not move --------------------

    def test_asking_twice_moves_no_admission_window(self):
        """A bound of one, two questions, and the one start the bound admits
        is still there to be admitted: the question consumed nothing."""
        self.tenant.max_task_starts_per_minute = 1
        self.tenant.save(update_fields=["max_task_starts_per_minute"])
        starts_key, _ = admission.window_keys(self.customer.id)

        self.assertTrue(self._answer()["allowed"])
        self.assertTrue(self._answer()["allowed"])

        self.assertIsNone(cache.get(starts_key))
        self._start()
        self.assertEqual(cache.get(starts_key), 1)

    # -- claim 9: available money is the balance less open reservations -----

    def test_available_is_the_balance_less_open_reservations(self):
        """A prepaid start of work sold at one agreed price reserves that
        price (#461); the question reports the balance untouched and the
        available amount with the reservation taken out."""
        self._start(task_type=SOLD_WHOLE)

        answer = self._answer()

        self.assertTrue(answer["allowed"])
        self.assertEqual(answer["balance_micros"], BALANCE)
        self.assertEqual(answer["available_micros"], BALANCE - THE_AGREED_PRICE)

    # -- the verdict, in the registry's words --------------------------------

    def test_the_hard_floor(self):
        self._set_balance(-HARD - 1)

        answer = self._answer()

        self.assertFalse(answer["allowed"])
        self.assertEqual(answer["reason"], AFFORDABILITY_REASON_INSUFFICIENT_FUNDS)
        self.assertEqual(answer["balance_micros"], -HARD - 1)
        self.assertEqual(answer["available_micros"], -HARD - 1)
        self.assertEqual(answer["min_balance_micros"], HARD)
        self.assertEqual(answer["soft_min_balance_micros"], SOFT)

    def test_the_soft_floor_at_the_altitude_the_parent_names(self):
        """Past the wind-down line a NEW top-level start is refused while
        contained work under a running parent passes — so the same balance
        is answered two ways, and the soft floor reported is the one that
        was tested: the figure for top-level work, none for contained work."""
        parent = self._start()
        self._set_balance(WINDING_DOWN)

        top_level = self._answer()
        contained = self._answer(parent_task_id=parent)

        self.assertFalse(top_level["allowed"])
        self.assertEqual(top_level["reason"], AFFORDABILITY_REASON_SOFT_FLOOR_REACHED)
        self.assertEqual(top_level["soft_min_balance_micros"], SOFT)
        self.assertEqual(top_level["min_balance_micros"], HARD)

        self.assertTrue(contained["allowed"])
        self.assertIsNone(contained["reason"])
        self.assertIsNone(contained["soft_min_balance_micros"])
        self.assertEqual(contained["min_balance_micros"], HARD)
        self.assertEqual(contained["balance_micros"], WINDING_DOWN)

    def test_the_pool(self):
        """The seat's own pool, blocking, with the period's charges at its
        cap: refused in the pool's word, with the money read beside it."""
        CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.customer, cap_micros=1_000_000,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        with mock.patch.object(CustomerSpendPoolService, "current_spend",
                               return_value=1_000_000):
            answer = self._answer()

        self.assertFalse(answer["allowed"])
        self.assertEqual(answer["reason"],
                         AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED)
        self.assertEqual(answer["balance_micros"], BALANCE)
        self.assertEqual(answer["min_balance_micros"], HARD)

    def test_a_suspension_is_worded_by_the_line_holding_the_customer(self):
        """#459's rule, mirrored at the read floor: a customer the pool
        alone is holding is refused in the pool's word, every other
        suspension in the wallet's — read off the OPEN ledger lines. A
        standing refusal is made before any wallet is read, so the money
        beside it is null."""
        self.customer.status = CUSTOMER_STATUS_SUSPENDED
        self.customer.save(update_fields=["status"])
        unlined = self._answer()

        pool = CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.customer, cap_micros=1_000_000,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        StopSignalService.drive_stop(
            self.customer.id, self.tenant, line=reasons.CUSTOMER_SPEND_POOL,
            control_id=pool.id)
        held_by_the_pool = self._answer()

        self.assertFalse(unlined["allowed"])
        self.assertEqual(unlined["reason"], AFFORDABILITY_REASON_INSUFFICIENT_FUNDS)
        self.assertFalse(held_by_the_pool["allowed"])
        self.assertEqual(held_by_the_pool["reason"],
                         AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED)
        for answer in (unlined, held_by_the_pool):
            self.assertIsNone(answer["balance_micros"])
            self.assertIsNone(answer["available_micros"])
            self.assertIsNone(answer["min_balance_micros"])
            self.assertIsNone(answer["soft_min_balance_micros"])

    def test_a_closed_customer(self):
        self.customer.status = CUSTOMER_STATUS_CLOSED
        self.customer.save(update_fields=["status"])

        answer = self._answer()

        self.assertFalse(answer["allowed"])
        self.assertEqual(answer["reason"], AFFORDABILITY_REASON_ACCOUNT_CLOSED)
        self.assertIsNone(answer["balance_micros"])

    def test_a_postpaid_tenant_has_a_balance_and_no_floors(self):
        """Postpaid reserves nothing and has no wallet floors (`check`'s
        fork), so its floors are reported as absent rather than as figures
        that were never tested; its balance is still read."""
        postpaid = a_tenant_selling_whole_work(
            billing_mode="postpaid", balance_micros=0,
            name="Invoiced", external_id="c5")
        response = self._ask(postpaid.customer, auth=postpaid.auth())
        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()

        self.assertTrue(answer["allowed"])
        self.assertEqual(answer["balance_micros"], 0)
        self.assertEqual(answer["available_micros"], 0)
        self.assertIsNone(answer["min_balance_micros"])
        self.assertIsNone(answer["soft_min_balance_micros"])
