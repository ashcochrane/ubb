"""A top-up attempt names the automatic trigger once (R10-W4).

The automatic top-up is spelled `auto_top_up` everywhere UBB names it; a top-up
attempt's trigger was the last stored value still spelled run-together. These
pin the end state at the table: an automatic attempt is stored under the one
spelling, the run-together one is no choice the field offers, and the
one-pending-automatic-attempt guarantee holds over the canonical value, under
its canonical name `uq_one_pending_auto_top_up_per_customer`.

Before the cutover (#190) these cases ran `topups/0006` for real, through the
executor and back, moving every stored trigger to the new spelling and
recreating the constraint over it; that data step left with the squashed
chain, and what it left behind is pinned below.
"""
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.billing.topups.models import (
    TOP_UP_ATTEMPT_TRIGGERS, TRIGGER_AUTO_TOP_UP, TopUpAttempt)
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

#: The run-together spelling the trigger stored before R10-W4 — derived rather
#: than written, so this file never spells the retired token.
OLD_TRIGGER = TRIGGER_AUTO_TOP_UP.replace("top_up", "topup")
ONE_PENDING = "uq_one_pending_auto_top_up_per_customer"


class TheTriggerIsStoredUnderItsOneSpellingTest(TestCase):

    def setUp(self):
        tenant = Tenant.objects.create(name="Top-ups")
        self.customer = Customer.objects.create(tenant=tenant, external_id="c1")
        self.other = Customer.objects.create(tenant=tenant, external_id="c2")

    def _attempt(self, customer, trigger):
        return TopUpAttempt.objects.create(
            customer=customer, billing_owner_id=customer.id,
            amount_micros=1_000_000, trigger=trigger, status="pending")

    def _stored_trigger(self, attempt):
        with connection.cursor() as cursor:
            cursor.execute("SELECT trigger FROM ubb_top_up_attempt WHERE id = %s",
                           [str(attempt.pk)])
            return cursor.fetchone()[0]

    def test_an_automatic_attempt_is_stored_under_the_canonical_trigger(self):
        self.assertNotEqual(OLD_TRIGGER, TRIGGER_AUTO_TOP_UP)  # the derivation is live
        offered = {value for value, _ in TOP_UP_ATTEMPT_TRIGGERS}
        self.assertIn(TRIGGER_AUTO_TOP_UP, offered)
        self.assertNotIn(OLD_TRIGGER, offered)

        automatic = self._attempt(self.customer, TRIGGER_AUTO_TOP_UP)
        manual = self._attempt(self.other, "manual")

        self.assertEqual(self._stored_trigger(automatic), TRIGGER_AUTO_TOP_UP)
        self.assertEqual(self._stored_trigger(manual), "manual")

    def test_a_second_pending_automatic_attempt_is_refused_by_name(self):
        """The customer's one place: a second pending automatic attempt for the
        same customer is refused by the database, by name — and another
        customer's first one is admitted beside it."""
        self._attempt(self.customer, TRIGGER_AUTO_TOP_UP)

        with self.assertRaisesRegex(IntegrityError, ONE_PENDING):
            with transaction.atomic():
                self._attempt(self.customer, TRIGGER_AUTO_TOP_UP)
        self._attempt(self.other, TRIGGER_AUTO_TOP_UP)
        self.assertEqual(
            TopUpAttempt.objects.filter(trigger=TRIGGER_AUTO_TOP_UP,
                                        status="pending").count(), 2)
