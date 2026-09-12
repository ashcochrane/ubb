"""Three concurrent prepaid starts against a balance that affords two: exactly
two succeed (#461, slice 6 §5, #139 §4.1 — the money invariant the
reservation exists for, under a real race).

Same harness as the three money-race modules that stay
(`apps/billing/tests/test_concurrency_races.py`, its grants twin, and
`apps/billing/invoicing/tests/test_concurrency_postpaid.py`):
`TransactionTestCase` so the fixture is COMMITTED before the workers start
and they see each other through real Postgres row locking; a
`threading.Barrier` releasing every worker into the critical section at
once, which is what maximises the race window; each worker closing its
thread-local connection. It drives the START ROUTE rather than a service,
because the invariant lives at the start — the verdict, the unit's row and
the reservation are one transaction there, and a race between services
would prove a narrower thing than the one a tenant's three workers make.

THE CONTROL BESIDE IT: the same three workers against a balance that affords
three all succeed, so the refusal above is the reservation's and not the
harness's.
"""
import json
import threading
import uuid

from django.db import connection
from django.test import Client, TransactionTestCase

from apps.billing.wallets.models import Wallet, WalletReservation
from apps.metering.pricing.tests._helpers import a_price_for_whole_work
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import Task, TaskType
from core.vocabulary import (
    AFFORDABILITY_REASON_INSUFFICIENT_FUNDS, PRICING_MODE_FIXED,
    TASK_TYPE_KIND_TASK)

SOLD_WHOLE = "transcode"
THE_AGREED_PRICE = 8_000_000
WORKERS = 3


class ConcurrentPrepaidStartsTest(TransactionTestCase):

    def _a_customer_whose_balance_affords(self, how_many):
        self.tenant = Tenant.objects.create(
            name="RACE_RESERVE", products=["metering", "billing"],
            billing_mode="prepaid")
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="race_c1")
        TaskType.objects.create(tenant=self.tenant, key=SOLD_WHOLE,
                                kind=TASK_TYPE_KIND_TASK,
                                pricing_mode=PRICING_MODE_FIXED, uncapped=True)
        a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                               amount_micros=THE_AGREED_PRICE)
        # The floor is zero, so "affords N" is N prices exactly: the N+1th
        # start would leave the available amount below the line.
        Wallet.objects.create(customer=self.customer,
                              balance_micros=how_many * THE_AGREED_PRICE)

    def _race(self):
        barrier = threading.Barrier(WORKERS)
        answers, errors = [], []

        def worker():
            try:
                body = {"customer_id": str(self.customer.id),
                        "task_type": SOLD_WHOLE,
                        "idempotency_key": f"attempt-{uuid.uuid4()}"}
                barrier.wait()
                response = Client().post(
                    "/api/v1/tasks", data=json.dumps(body),
                    content_type="application/json",
                    HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
                answers.append((response.status_code, response.json()))
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [], f"workers raised: {errors}")
        return answers

    def test_three_starts_against_a_balance_that_affords_two(self):
        self._a_customer_whose_balance_affords(2)

        answers = self._race()

        self.assertEqual(sorted(status for status, _ in answers), [200, 200, 409])
        refused = next(body for status, body in answers if status == 409)
        self.assertEqual(refused["reason"], AFFORDABILITY_REASON_INSUFFICIENT_FUNDS)
        # Exactly two pieces of work, exactly two reservations, for exactly
        # the balance.
        self.assertEqual(Task.objects.filter(tenant=self.tenant).count(), 2)
        rows = WalletReservation.objects.filter(owner=self.customer,
                                                released_at__isnull=True)
        self.assertEqual(rows.count(), 2)
        self.assertEqual(sum(row.amount_micros for row in rows),
                         2 * THE_AGREED_PRICE)
        # And the balance itself never moved: a reservation is not a debit.
        self.assertEqual(Wallet.objects.get(customer=self.customer).balance_micros,
                         2 * THE_AGREED_PRICE)

    def test_the_control_three_starts_against_a_balance_that_affords_three(self):
        self._a_customer_whose_balance_affords(3)

        answers = self._race()

        self.assertEqual([status for status, _ in answers], [200, 200, 200])
        self.assertEqual(WalletReservation.objects.filter(
            owner=self.customer, released_at__isnull=True).count(), 3)
