"""Migration `0014` keys the signal ledger by family and line (#458, slice 6
§9, ADR-0007 §1).

⚠ NOTHING HERE SPELLS THE OLD FAMILY WORDS. Both are read off the migration's
own constants, and every current word is asserted by CONSTANT IDENTITY
against the service and the registry — the migration's second encoding is
held to the first, which is the rule the stored-cause migration's tests set
for a migration that cannot import the code.

⚠ WHAT THESE CASES DO NOT COVER, said rather than left to be discovered: they
call the migration's two data functions with the live app registry, exactly
as `work/0026`'s tests do, so nothing drives `0014` through the migration
RUNNER — the rename, the two added columns and the constraint swap are the
runner's, and `makemigrations --check` plus the constraint case in
`test_stop_signal_ledger.py` cover that half. The live model already has the
renamed column, so a row planted here under an old family word is exactly
the shape the data pass meets one operation later.
"""
import importlib

from django.apps import apps as global_apps
from django.test import TestCase
from django.utils import timezone

from apps.billing.gating.models import CONTROL_FAMILIES, StopSignalState
from apps.billing.gating.services import stop_signal_service as service
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import RefundRequested, StopCleared, StopFired
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons
from core.vocabulary import (
    CONTROL_FAMILY_VALUES, CUSTOMER_BILLING_MODE_POSTPAID,
    CUSTOMER_BILLING_MODE_PREPAID)

MIGRATION = importlib.import_module(
    "apps.billing.gating.migrations.0014_the_signal_ledger_keys_by_family_and_line")


class TheMapIsTheRegistrysWordsTest(TestCase):
    def test_the_families_are_the_registrys_four(self):
        self.assertEqual(
            {identity for identity, _ in MIGRATION.CONTROL_FAMILY_CHOICES},
            CONTROL_FAMILY_VALUES)
        self.assertEqual(MIGRATION.CONTROL_FAMILY_CHOICES, CONTROL_FAMILIES)

    def test_the_lines_are_the_services_three(self):
        self.assertEqual(MIGRATION.LINE_HARD_FLOOR, service.LINE_HARD_FLOOR)
        self.assertEqual(MIGRATION.LINE_CUSTOMER_SPEND_POOL,
                         service.LINE_CUSTOMER_SPEND_POOL)
        self.assertEqual(MIGRATION.LINE_SOFT_FLOOR, service.LINE_SOFT_FLOOR)
        self.assertEqual(MIGRATION.OLD_SOFT_FLOOR_REACHED, service.SOFT_FLOOR_REACHED)

    def test_the_family_of_each_line_is_the_services_answer(self):
        for line in (service.LINE_HARD_FLOOR, service.LINE_CUSTOMER_SPEND_POOL,
                     service.LINE_SOFT_FLOOR):
            self.assertEqual(MIGRATION.family_of_line(line),
                             service.family_of_line(line), line)

    def test_the_split_is_by_mode_and_by_nothing_else(self):
        self.assertEqual(MIGRATION.stop_line(CUSTOMER_BILLING_MODE_POSTPAID),
                         reasons.CUSTOMER_SPEND_POOL)
        for mode in (CUSTOMER_BILLING_MODE_PREPAID,
                     Tenant._meta.get_field("billing_mode").default):
            self.assertEqual(MIGRATION.stop_line(mode), reasons.HARD_FLOOR, mode)

    def test_the_pair_it_reads_is_the_customer_stop_pair(self):
        self.assertEqual(set(MIGRATION.PAIR),
                         {StopFired.EVENT_TYPE, StopCleared.EVENT_TYPE})

    def test_the_operations_carry_the_rows_and_state_their_reason(self):
        from django.db.migrations import RenameField, RunPython
        operations = MIGRATION.Migration.operations
        self.assertTrue(any(isinstance(op, RenameField) for op in operations))
        runs = [op for op in operations if isinstance(op, RunPython)]
        self.assertEqual(len(runs), 1)
        self.assertIsNotNone(runs[0].reverse_code)
        self.assertIn("ADR-0007", MIGRATION.__doc__)


class MigrationTestBase(TestCase):
    def setUp(self):
        self.prepaid = Tenant.objects.create(
            name="Prepaid", products=["metering", "billing"],
            billing_mode=CUSTOMER_BILLING_MODE_PREPAID)
        self.postpaid = Tenant.objects.create(
            name="Postpaid", products=["metering", "billing"],
            billing_mode=CUSTOMER_BILLING_MODE_POSTPAID)
        self.pre = Customer.objects.create(tenant=self.prepaid, external_id="pre")
        self.post = Customer.objects.create(tenant=self.postpaid, external_id="post")

    def _old_row(self, tenant, owner, family, *, state="stopped", reason,
                 episode_seq=3):
        return StopSignalState.objects.create(
            tenant=tenant, owner=owner, control_family=family, reason=reason,
            state=state, episode_seq=episode_seq, transitioned_at=timezone.now())

    def _forward(self):
        MIGRATION._key_the_lines(global_apps, None)

    def _backward(self):
        MIGRATION._collapse_the_lines(global_apps, None)

    def _fresh(self, row):
        row.refresh_from_db()
        return row


class TheRowsTakeTheirLinesTest(MigrationTestBase):
    def test_the_customer_wide_row_splits_by_the_owners_tenant_mode(self):
        pre = self._old_row(self.prepaid, self.pre, MIGRATION.OLD_FLOOR_STOP,
                            reason=reasons.HARD_FLOOR)
        post = self._old_row(self.postpaid, self.post, MIGRATION.OLD_FLOOR_STOP,
                             reason=reasons.CUSTOMER_SPEND_POOL)

        self._forward()

        pre, post = self._fresh(pre), self._fresh(post)
        self.assertEqual((pre.control_family, pre.reason, pre.clear_reason),
                         (service.family_of_line(reasons.HARD_FLOOR),
                          reasons.HARD_FLOOR, ""))
        self.assertEqual((post.control_family, post.reason, post.clear_reason),
                         (service.family_of_line(reasons.CUSTOMER_SPEND_POOL),
                          reasons.CUSTOMER_SPEND_POOL, ""))
        self.assertEqual((pre.episode_seq, post.episode_seq), (3, 3))
        self.assertIsNone(pre.control_id)

    def test_a_cleared_rows_clearing_cause_moves_to_its_own_column(self):
        row = self._old_row(self.prepaid, self.pre, MIGRATION.OLD_FLOOR_STOP,
                            state="cleared", reason=service.CLEAR_BALANCE_RECOVERED)

        self._forward()

        row = self._fresh(row)
        self.assertEqual(row.reason, reasons.HARD_FLOOR)
        self.assertEqual(row.clear_reason, service.CLEAR_BALANCE_RECOVERED)

    def test_the_wind_down_row_is_the_wallet_policys_line(self):
        stopped = self._old_row(self.prepaid, self.pre, MIGRATION.OLD_SOFT_FLOOR,
                                reason=service.SOFT_FLOOR_REACHED)
        cleared = self._old_row(self.postpaid, self.post, MIGRATION.OLD_SOFT_FLOOR,
                                state="cleared", reason=service.CLEAR_RECONCILED)

        self._forward()

        stopped, cleared = self._fresh(stopped), self._fresh(cleared)
        for row in (stopped, cleared):
            self.assertEqual(row.control_family,
                             service.family_of_line(service.LINE_SOFT_FLOOR))
            self.assertEqual(row.reason, service.LINE_SOFT_FLOOR)
        self.assertEqual(stopped.clear_reason, "")
        self.assertEqual(cleared.clear_reason, service.CLEAR_RECONCILED)

    def test_the_reverse_round_trips_what_it_can(self):
        stopped = self._old_row(self.prepaid, self.pre, MIGRATION.OLD_FLOOR_STOP,
                                reason=reasons.HARD_FLOOR)
        cleared = self._old_row(self.postpaid, self.post, MIGRATION.OLD_FLOOR_STOP,
                                state="cleared", reason=service.CLEAR_RECONCILED)
        soft = self._old_row(self.postpaid, self.post, MIGRATION.OLD_SOFT_FLOOR,
                             reason=service.SOFT_FLOOR_REACHED)

        self._forward()
        self._backward()

        for row, family, reason in ((stopped, MIGRATION.OLD_FLOOR_STOP, reasons.HARD_FLOOR),
                                    (cleared, MIGRATION.OLD_FLOOR_STOP, service.CLEAR_RECONCILED),
                                    (soft, MIGRATION.OLD_SOFT_FLOOR, service.SOFT_FLOOR_REACHED)):
            row = self._fresh(row)
            self.assertEqual((row.control_family, row.reason, row.clear_reason),
                             (family, reason, ""))


class ThePairsPayloadsTakeTheNewShapeTest(MigrationTestBase):
    def _row(self, tenant, event_type, **payload):
        # Literal payloads on purpose (`docs/conventions/testing.md`'s
        # exception): the POINT is the shape a row queued before #458 holds
        # — the bare `reason` the current dataclasses no longer declare.
        return OutboxEvent.objects.create(
            event_type=event_type, tenant_id=tenant.id,
            payload={"tenant_id": str(tenant.id), **payload})

    def _payload(self, row):
        row.refresh_from_db()
        return row.payload

    def test_the_bare_reason_becomes_the_lines_word_with_its_family(self):
        fired = self._row(self.postpaid, StopFired.EVENT_TYPE,
                          reason=reasons.CUSTOMER_SPEND_POOL, episode_seq=1)
        cleared = self._row(self.prepaid, StopCleared.EVENT_TYPE,
                            reason=service.CLEAR_BALANCE_RECOVERED, episode_seq=1)

        self._forward()

        self.assertEqual(self._payload(fired), {
            "tenant_id": str(self.postpaid.id), "episode_seq": 1,
            "reason_code": reasons.CUSTOMER_SPEND_POOL,
            "control_family": service.family_of_line(reasons.CUSTOMER_SPEND_POOL),
            "control_id": ""})
        # The clearing cause leaves the wire: the line's word takes its place.
        self.assertEqual(self._payload(cleared)["reason_code"], reasons.HARD_FLOOR)
        self.assertNotIn("reason", self._payload(cleared))

    def test_a_free_text_reason_on_another_event_is_left_as_written(self):
        """#457's lesson: the pass is scoped by event type."""
        refund = self._row(self.prepaid, RefundRequested.EVENT_TYPE,
                           reason=reasons.HARD_FLOOR, refund_id="r1")

        self._forward()

        self.assertEqual(self._payload(refund)["reason"], reasons.HARD_FLOOR)
        self.assertNotIn("reason_code", self._payload(refund))

    def test_the_reverse_puts_the_bare_key_back_and_drops_the_control(self):
        fired = self._row(self.prepaid, StopFired.EVENT_TYPE,
                          reason=reasons.HARD_FLOOR, episode_seq=2)

        self._forward()
        self._backward()

        self.assertEqual(self._payload(fired), {
            "tenant_id": str(self.prepaid.id), "episode_seq": 2,
            "reason": reasons.HARD_FLOOR})
