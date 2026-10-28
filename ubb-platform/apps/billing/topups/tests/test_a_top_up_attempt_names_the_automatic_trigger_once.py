"""A top-up attempt names the automatic trigger once (R10-W4, `topups/0006`).

The automatic top-up is spelled `auto_top_up` everywhere UBB names it; a top-up
attempt's trigger was the last stored value still spelled run-together. These
run `topups/0006` for real, through the executor and back, and pin that the
one-pending-automatic-attempt guarantee survives the move — over the new value,
under its canonical name.
"""
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase

from apps.billing.topups.models import TRIGGER_AUTO_TOP_UP, TopUpAttempt
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

#: The run-together spelling the trigger stored before R10-W4 — derived rather
#: than written, so this file never spells the retired token.
OLD_TRIGGER = TRIGGER_AUTO_TOP_UP.replace("top_up", "topup")
ONE_PENDING = "uq_one_pending_auto_top_up_per_customer"


class TheMigrationMovesEveryStoredTriggerTest(TestCase):

    BEFORE = ("topups", "0005_topupattempt_billing_owner_id")
    AFTER = ("topups", "0006_a_top_up_attempt_names_the_automatic_trigger_once")

    def setUp(self):
        tenant = Tenant.objects.create(name="Top-ups")
        self.customer = Customer.objects.create(tenant=tenant, external_id="c1")
        self.other = Customer.objects.create(tenant=tenant, external_id="c2")

    def tearDown(self):
        self._migrate_to(self.AFTER)

    def _migrate_to(self, target):
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        MigrationExecutor(connection).migrate([target])

    def _attempt(self, customer, trigger):
        return TopUpAttempt.objects.create(
            customer=customer, billing_owner_id=customer.id,
            amount_micros=1_000_000, trigger=trigger, status="pending")

    def _stored_trigger(self, attempt):
        with connection.cursor() as cursor:
            cursor.execute("SELECT trigger FROM ubb_top_up_attempt WHERE id = %s",
                           [str(attempt.pk)])
            return cursor.fetchone()[0]

    def test_the_stored_trigger_moves_back_and_forth_and_nothing_else_does(self):
        automatic = self._attempt(self.customer, TRIGGER_AUTO_TOP_UP)
        manual = self._attempt(self.other, "manual")

        self._migrate_to(self.BEFORE)
        self.assertEqual(self._stored_trigger(automatic), OLD_TRIGGER)
        self.assertEqual(self._stored_trigger(manual), "manual")

        self._migrate_to(self.AFTER)
        self.assertEqual(self._stored_trigger(automatic), TRIGGER_AUTO_TOP_UP)
        self.assertEqual(self._stored_trigger(manual), "manual")

    def test_a_moved_pending_attempt_still_holds_the_customers_one_place(self):
        """A row stored under the old spelling, moved by the migration, is one
        the recreated constraint sees: a second pending automatic attempt for
        the same customer is refused, by name."""
        self._migrate_to(self.BEFORE)
        self._attempt(self.customer, OLD_TRIGGER)

        self._migrate_to(self.AFTER)
        with self.assertRaisesRegex(IntegrityError, ONE_PENDING):
            with transaction.atomic():
                self._attempt(self.customer, TRIGGER_AUTO_TOP_UP)
        self._attempt(self.other, TRIGGER_AUTO_TOP_UP)
