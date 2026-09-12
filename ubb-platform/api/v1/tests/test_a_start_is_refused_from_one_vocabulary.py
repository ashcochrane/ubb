"""A start is refused from one vocabulary (#463, slice 6 §1, §13).

Every refusal `POST /api/v1/tasks` can give — by the wallet, by the pool, by
the throttle, by the customer's standing and by the shape of the work — is
a value of the registry's `affordability_reason`, produced by constant on
whichever side of the product boundary produces it: the kernel's admission
check (the rate, the standing), its work service (a parent that is not
running; a depth work cannot nest to), billing's money verdict (the floors,
the pool, and the wording of a suspension). This module drives each through
the real route and asserts the word by CONSTANT IDENTITY, never by a
spelled string — the whole point of one vocabulary is that a rename of the
constant renames every producer and every assertion at once — and closes
by asserting that everything it saw is a registry value.

The pieces of refusal each have their own module (the admission check's,
the reservation's, the pool's, the containment pins'); this one is the
place they are read side by side. It says "a unit of work" and "contained
work" throughout.
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase

from api.v1.tests._helpers import (
    SOLD_PER_EVENT, THE_AGREED_PRICE, a_tenant_selling_whole_work)
from apps.billing.gating.models import CustomerSpendPool
from apps.billing.gating.services.customer_spend_pool_service import (
    CustomerSpendPoolService)
from apps.platform.customers.models import (
    CUSTOMER_STATUS_CLOSED, CUSTOMER_STATUS_SUSPENDED)
from core.vocabulary import (
    AFFORDABILITY_REASON_ACCOUNT_CLOSED,
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
    AFFORDABILITY_REASON_INSUFFICIENT_FUNDS,
    AFFORDABILITY_REASON_KNOWN_VALUES,
    AFFORDABILITY_REASON_PARENT_TASK_NOT_ACTIVE,
    AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED,
    AFFORDABILITY_REASON_SUBTASK_DEPTH_EXCEEDED,
    SPEND_POOL_ENFORCE_MODE_BLOCKING, TASK_OUTCOME_DELIVERED)


class AStartIsRefusedFromOneVocabularyTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.fixture = a_tenant_selling_whole_work(
            billing_mode="prepaid", balance_micros=THE_AGREED_PRICE)
        self.tenant = self.fixture.tenant
        self.customer = self.fixture.customer
        #: Every word a refusal in this module carried.
        self.seen = set()

    def tearDown(self):
        cache.clear()
        self.assertTrue(self.seen <= AFFORDABILITY_REASON_KNOWN_VALUES, self.seen)

    # -- the seams ----------------------------------------------------------

    def _start(self, **body):
        body.setdefault("task_type", SOLD_PER_EVENT)
        return self.client.post(
            "/api/v1/tasks", data=json.dumps(self.fixture.start_body(**body)),
            content_type="application/json", **self.fixture.auth())

    def _started(self, **body):
        response = self._start(**body)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["task_id"]

    def _refused(self, status=409, **body):
        """The refusal's word, read off the problem — `reason` on the 409 the
        customer's state or the work's shape answers with, the code itself on
        the rate's 429 (the one refusal that is a problem code as well as a
        registry value)."""
        response = self._start(**body)
        self.assertEqual(response.status_code, status, response.content)
        problem = response.json()
        word = problem["reason"] if status == 409 else problem["code"]
        self.seen.add(word)
        return word

    def _set_balance(self, balance_micros):
        self.fixture.wallet.balance_micros = balance_micros
        self.fixture.wallet.save(update_fields=["balance_micros"])

    # -- the five producers -------------------------------------------------

    def test_by_the_wallet(self):
        """Past the hard floor — the tenant's default of nothing owed — the
        money verdict refuses in the wallet's word."""
        self._set_balance(-1)
        self.assertEqual(self._refused(), AFFORDABILITY_REASON_INSUFFICIENT_FUNDS)

    def test_by_the_pool(self):
        CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=self.customer, cap_micros=1_000_000,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING)
        with mock.patch.object(CustomerSpendPoolService, "current_spend",
                               return_value=1_000_000):
            word = self._refused()
        self.assertEqual(word, AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED)

    def test_by_the_throttle(self):
        """The kernel's admission check: a bound of one, and the second
        top-level start in the window is a 429 whose code is the registry's
        own word."""
        self.tenant.max_task_starts_per_minute = 1
        self.tenant.save(update_fields=["max_task_starts_per_minute"])
        self._started()
        self.assertEqual(self._refused(status=429),
                      AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED)

    def test_by_the_shape_of_the_work(self):
        """The kernel's work service: contained work under a parent that has
        ended, and work that would nest deeper than one level."""
        ended = self._started()
        close = self.client.post(
            f"/api/v1/tasks/{ended}/close",
            data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
            content_type="application/json", **self.fixture.auth())
        self.assertEqual(close.status_code, 200, close.content)
        self.assertEqual(self._refused(parent_task_id=ended),
                      AFFORDABILITY_REASON_PARENT_TASK_NOT_ACTIVE)

        parent = self._started()
        contained = self._started(parent_task_id=parent)
        self.assertEqual(self._refused(parent_task_id=contained),
                      AFFORDABILITY_REASON_SUBTASK_DEPTH_EXCEEDED)

    def test_by_the_customers_standing(self):
        """The kernel refuses the standing; for a tenant with a wallet the
        money verdict WORDS a suspension by the line holding the customer
        (#459, #462) — none open here, so the wallet's word — and a closure
        in the registry's own."""
        self.customer.status = CUSTOMER_STATUS_SUSPENDED
        self.customer.save(update_fields=["status"])
        self.assertEqual(self._refused(), AFFORDABILITY_REASON_INSUFFICIENT_FUNDS)

        self.customer.status = CUSTOMER_STATUS_CLOSED
        self.customer.save(update_fields=["status"])
        self.assertEqual(self._refused(), AFFORDABILITY_REASON_ACCOUNT_CLOSED)
