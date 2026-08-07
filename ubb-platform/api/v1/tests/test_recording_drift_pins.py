"""Ruling A (#233, slice 1 / #192) — can the SURVIVING recording path strand a
live balance?

The upward live-balance repair (``apps/billing/gating/repair.py``, #45) exists
because a wallet counter can be left reading BELOW the truth: money the tenant
has not spent shows as spent, and once the drift is large enough the tenant is
FALSELY STOPPED. Its docstring, as it read when this ruling was taken, named
exactly one cause — quoted verbatim below as the evidence the ruling overturned,
so the symbols in it are deliberately not updated (the table it names was
dropped in #238, and the docstring itself was corrected in #234):

    "An orphaned hold — acquired on the fast lane, its ``RawIngestEvent`` row
    rolled back with a crashed request — leaves the prepaid live counter
    permanently below reality: the stingy direction, false stops when it
    drifts far enough."

That lane is being deleted. #149 §6.6, #149 §12 and #155 §11 each flag the same
unanswered question and none of them answers it: whether the surviving
SYNCHRONOUS path can produce the same class of drift — a counter written, its
event row then rolled back. This module answers it.

**Ruling: A2 — the drift CAN occur on the surviving path.** The repair's stated
cause is therefore incomplete: the reservation is one cause, not the cause.
Correcting the repair's own docstring belongs to the ticket that narrows it,
not here — this module deletes and edits nothing.

WHY THIS SEAM. The question is a property of the PATH, not of the counter, so
the case is driven through ``POST /api/v1/metering/usage`` with the Django test
client rather than written against ``LiveCounter``. A test at the counter would
prove only that Redis has no rollback — which nobody doubts. What is in
question is whether a tenant's own request can reach that state, and that is
answerable only where the request crosses.

THE MECHANISM (``usage_service.py``). ``UsageService.record_usage`` is
``@transaction.atomic``. The ``UsageEvent`` row is created inside an INNER
atomic — a savepoint — and the live-counter debit is issued AFTER that
savepoint commits while the OUTER transaction is still open. Everything from
the debit to the outer commit is therefore a window in which the row can still
be rolled back and the Redis debit, which has no rollback, cannot. Stop-context
tagging and (for a backdated event) a dirty-period marker run inside that
window; the outbox insert is the LAST database write in it. The failure
injected below is that outbox insert — in production a real row against a real
table, so failing it models an ordinary infrastructure failure, and being last
it exercises the widest form of the window.

THIS MODULE STAYS after slice 1. It pins a property of the surviving path that
a later change could break: deferring the debit until after the transaction
commits would close the window and turn this into A1, and these cases would go
red and force the ruling to be revisited rather than quietly passing.
"""
import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError
from django.test import Client, TestCase

from api.v1.schemas import RecordUsageRequest
from apps.billing.gating.services.live_counter import Door
from apps.billing.wallets.models import Wallet
from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.reasons import CUSTOMER_WIDE_STOP

WALLET_MICROS = 100_000_000  # $100 of real, unspent money
BILLED_MICROS = 30_000_000  # $30 the tenant is charged for the failed request
# Enough to drive the live counter below the floor before the rollback, so the
# crossing check fires on the debit of a request that is never recorded.
OVERSPEND_MICROS = WALLET_MICROS + 50_000_000


def _correlation_values():
    """Every required plain-string field on the recording request, each given
    a unique value.

    Read off the schema rather than spelled out. One of them is a retired term
    whose migration is owed by a later slice, and the ledger that owes it only
    ever shrinks — a new file that named it would grow the term's recorded
    extent instead. Reading the names here also means that slice's deletion
    needs no edit in this module.
    """
    return {name: f"{name}-{uuid.uuid4()}"
            for name, field in RecordUsageRequest.model_fields.items()
            if field.is_required() and field.annotation is str}


class RecordingDriftPinTest(TestCase):
    """The tenant is prepaid and enforcing, so the fast lane is on and the
    live balance counter is the thing a stop verdict is read from."""

    def setUp(self):
        cache.clear()  # FLUSHDB: the ubb:* keys are raw-client, not cache.*
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Drift", products=["metering", "billing"],
            billing_mode="prepaid", enforcement_mode="enforcing")
        _key, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=WALLET_MICROS)

    def tearDown(self):
        cache.clear()

    # -- the seam: the tenant's own request, over HTTP --------------------

    def _record(self, billed_micros=BILLED_MICROS):
        return self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "provider_cost_micros": 10_000_000,
                "billed_cost_micros": billed_micros,
                **_correlation_values(),
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _record_crashing_after_the_counter_write(self, billed_micros):
        """The same request, with the outbox insert failing.

        The outbox write is the last DB write the recording core performs
        after the live-counter debit and before the transaction commits — so
        failing it rolls the event row back from a state where the counter has
        ALREADY moved.
        """
        with patch("apps.metering.usage.services.usage_service.write_event",
                   side_effect=IntegrityError("outbox insert failed")):
            return self._record(billed_micros)

    def _live_balance(self):
        """The live counter as the stop verdict reads it.

        ``None`` is the A1 reading — the counter was never touched for this
        owner — so the assertions below deliberately compare against a number
        rather than merely checking for movement.
        """
        return Door.balance(self.customer.id)

    def _durable_balance(self):
        return Wallet.objects.get(pk=self.wallet.pk).balance_micros

    # -- the control ------------------------------------------------------

    def test_control_a_successful_request_moves_the_row_and_the_counter(self):
        """Without the injected failure, row and counter move together — so a
        drift observed below is the rollback's doing and not the fixture's."""
        resp = self._record()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual(self._live_balance(), WALLET_MICROS - BILLED_MICROS)

    # -- Ruling A: the drift check ----------------------------------------

    def test_a_rollback_after_the_counter_write_strands_the_live_balance(self):
        """RULING A2. A crash after the debit leaves the counter $30 below the
        truth: no event row, no durable spend, and a live balance that says
        the money is gone."""
        resp = self._record_crashing_after_the_counter_write(BILLED_MICROS)

        # The tenant is told the request was not recorded, and for the durable
        # record that is true — the row rolled back with the transaction.
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["code"], "internal_error")
        self.assertEqual(UsageEvent.objects.count(), 0)
        self.assertEqual(self._durable_balance(), WALLET_MICROS)

        # For the live counter it is not true. Redis has no rollback, and the
        # debit was issued outside the savepoint that carried the row.
        self.assertEqual(self._live_balance(), WALLET_MICROS - BILLED_MICROS)
        self.assertEqual(
            self._durable_balance() - self._live_balance(), BILLED_MICROS,
            "the live counter should read exactly the rolled-back event below "
            "the durable balance — that is the stranded amount")

    def test_the_stranded_balance_falsely_stops_a_tenant_with_a_full_wallet(self):
        """The harm the repair exists to undo, reproduced on the surviving
        path: the crossing check runs on the debit, so the rolled-back request
        can also set the cooperative stop flag — which likewise does not roll
        back."""
        self._record_crashing_after_the_counter_write(OVERSPEND_MICROS)

        self.assertEqual(UsageEvent.objects.count(), 0)
        self.assertEqual(self._durable_balance(), WALLET_MICROS)
        self.assertEqual(self._live_balance(), WALLET_MICROS - OVERSPEND_MICROS)
        self.assertLess(self._live_balance(), 0, "the debit crossed the floor")
        self.assertEqual(Door.stop_reason(self.customer.id), CUSTOMER_WIDE_STOP)

        # The next request is legitimate and the wallet is untouched, but the
        # verdict rides the stranded counter. One-rule still holds: the event
        # is recorded and answered 200 — it is the verdict that is wrong.
        resp = self._record(billed_micros=1_000_000)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], CUSTOMER_WIDE_STOP)
        self.assertEqual(body["stop_scope"], "customer")
