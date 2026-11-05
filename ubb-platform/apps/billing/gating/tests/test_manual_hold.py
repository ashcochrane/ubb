"""The manual hold: one operator workflow to place and release a deliberate
hold on a customer (R10 Stage C4; owner/consultant ruling 2026-11-05, PLAN §7
item 41, FINAL).

The hold is the existing representation — ``suspended`` with an EMPTY reason —
placed through ``apps/billing/gating/services/manual_hold.py`` and released
through the one reactivation site, each announcing the canonical lifecycle
event and notifying a seat's roster once. It never overwrites, and its release
never clears, a cause its own recovery owns (``hard_floor``,
``customer_spend_pool``, ``payment_failed``, ``dispute_lost``). The operator
surface is ``manage.py set_customer_manual_hold``; the Django admin no longer
edits ``status`` or ``suspension_reason``.
"""
import datetime
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.billing.gating.services import manual_hold
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons

#: Every cause a system path suspends for, each owned by its own recovery.
SYSTEM_CAUSES = (reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL,
                 reasons.PAYMENT_FAILED, reasons.DISPUTE_LOST)


class _ManualHoldCase(TestCase):
    def setUp(self):
        from apps.platform.customers import hooks
        self.tenant = Tenant.objects.create(name="Hold", products=["metering", "billing"])
        self.business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled")
        self.seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat",
            parent=self.business)
        self.solo = Customer.objects.create(tenant=self.tenant, external_id="solo")
        # The roster's listeners, recorded for this test only.
        self.notified = []
        saved = list(hooks._listeners)
        hooks._listeners[:] = [self.notified.append]
        self.addCleanup(lambda: hooks._listeners.__setitem__(slice(None), saved))

    def standing(self, customer):
        customer.refresh_from_db()
        return customer.status, customer.suspension_reason

    def events(self, customer, kind):
        return list(OutboxEvent.objects.filter(
            event_type=kind, payload__customer_id=str(customer.id)).values_list(
                "payload", flat=True))

    def suspend_for(self, customer, reason):
        Customer.objects.filter(id=customer.id).update(
            status="suspended", suspension_reason=reason)


class PlacingAHoldTest(_ManualHoldCase):
    def test_a_hold_suspends_with_the_empty_reason_announces_and_notifies_once(self):
        self.assertEqual(manual_hold.place_manual_hold(self.seat.id, operator="op-1"),
                         manual_hold.HELD)
        self.assertEqual(self.standing(self.seat), ("suspended", ""))
        [announced] = self.events(self.seat, "customer.suspended")
        self.assertEqual((announced["reason"], announced["customer_id"]),
                         ("", str(self.seat.id)))
        self.assertEqual([b.id for b in self.notified], [self.business.id])

    def test_holding_a_held_customer_changes_nothing(self):
        manual_hold.place_manual_hold(self.solo.id, operator="op-1")
        self.assertEqual(manual_hold.place_manual_hold(self.solo.id, operator="op-2"),
                         manual_hold.ALREADY_HELD)
        self.assertEqual(self.standing(self.solo), ("suspended", ""))
        self.assertEqual(len(self.events(self.solo, "customer.suspended")), 1)

    def test_a_hold_never_overwrites_a_system_cause(self):
        for cause in SYSTEM_CAUSES:
            with self.subTest(cause):
                self.suspend_for(self.seat, cause)
                with self.assertRaisesMessage(manual_hold.ManualHoldRefused, "never overwrites"):
                    manual_hold.place_manual_hold(self.seat.id, operator="op-1")
                self.assertEqual(self.standing(self.seat), ("suspended", cause))
        self.assertEqual(self.events(self.seat, "customer.suspended"), [])
        self.assertEqual(self.notified, [])

    def test_a_closed_or_deleted_customer_cannot_be_held(self):
        Customer.objects.filter(id=self.solo.id).update(status="closed")
        with self.assertRaisesMessage(manual_hold.ManualHoldRefused, "'closed'"):
            manual_hold.place_manual_hold(self.solo.id, operator="op-1")
        self.assertEqual(self.standing(self.solo), ("closed", ""))
        self.seat.soft_delete()
        self.notified.clear()
        with self.assertRaisesMessage(manual_hold.ManualHoldRefused, "no live customer"):
            manual_hold.place_manual_hold(self.seat.id, operator="op-1")
        self.assertEqual(self.notified, [])


class ReleasingAHoldTest(_ManualHoldCase):
    def test_a_release_reactivates_through_the_one_site_and_notifies_once(self):
        manual_hold.place_manual_hold(self.seat.id, operator="op-1")
        self.notified.clear()
        self.assertEqual(manual_hold.release_manual_hold(self.seat.id, operator="op-2"),
                         manual_hold.RELEASED)
        self.assertEqual(self.standing(self.seat), ("active", ""))
        [reactivated] = self.events(self.seat, "customer.reactivated")
        self.assertEqual(reactivated["reason_code"], "")
        self.assertEqual([b.id for b in self.notified], [self.business.id])

    def test_releasing_an_active_customer_changes_nothing(self):
        manual_hold.place_manual_hold(self.solo.id, operator="op-1")
        manual_hold.release_manual_hold(self.solo.id, operator="op-1")
        self.assertEqual(manual_hold.release_manual_hold(self.solo.id, operator="op-1"),
                         manual_hold.ALREADY_ACTIVE)
        self.assertEqual(self.standing(self.solo), ("active", ""))
        self.assertEqual(len(self.events(self.solo, "customer.reactivated")), 1)

    def test_a_release_never_clears_a_system_cause(self):
        for cause in SYSTEM_CAUSES:
            with self.subTest(cause):
                self.suspend_for(self.seat, cause)
                with self.assertRaisesMessage(manual_hold.ManualHoldRefused,
                                              "not a manual hold"):
                    manual_hold.release_manual_hold(self.seat.id, operator="op-1")
                self.assertEqual(self.standing(self.seat), ("suspended", cause))
        self.assertEqual(self.events(self.seat, "customer.reactivated"), [])
        self.assertEqual(self.notified, [])

    def test_a_customer_deleted_during_its_release_is_refused_not_failed(self):
        manual_hold.place_manual_hold(self.solo.id, operator="op-1")

        def deleted_meanwhile(owner_id):
            Customer.objects.get(id=owner_id).soft_delete()
            return False          # the reactivation site no longer finds it

        with patch("apps.billing.gating.services.live_counter.LiveCounter.clear_manual_hold",
                   side_effect=deleted_meanwhile), \
                self.assertRaisesMessage(manual_hold.ManualHoldRefused, "no live customer"):
            manual_hold.release_manual_hold(self.solo.id, operator="op-1")

    def test_a_standing_payment_failure_keeps_the_customer_suspended_for_it(self):
        """RULED Q4: a qualifying failed invoice holds the owner at any other
        recovery, and the cause hands over to ``payment_failed``."""
        from apps.billing.invoicing.models import CustomerUsageInvoice
        manual_hold.place_manual_hold(self.solo.id, operator="op-1")
        CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self.solo, period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1), total_billed_micros=1_000_000,
            status="pushed", stripe_invoice_id="in_failed", payment_failed_at=timezone.now())
        self.assertEqual(manual_hold.release_manual_hold(self.solo.id, operator="op-1"),
                         manual_hold.HANDED_OVER)
        self.assertEqual(self.standing(self.solo), ("suspended", reasons.PAYMENT_FAILED))
        self.assertEqual(self.events(self.solo, "customer.reactivated"), [])

    def test_the_operator_is_kept_on_every_outcome_refusals_included(self):
        self.suspend_for(self.seat, reasons.HARD_FLOOR)
        with self.assertLogs("apps.billing.gating.services.manual_hold", "INFO") as logs:
            manual_hold.place_manual_hold(self.solo.id, operator="op-7")
            manual_hold.release_manual_hold(self.solo.id, operator="op-8")
            with self.assertRaises(manual_hold.ManualHoldRefused):
                manual_hold.release_manual_hold(self.seat.id, operator="op-9")
        self.assertEqual(
            [(r.getMessage(), r.data["outcome"], r.data["operator"]) for r in logs.records],
            [("customer.manual_hold", manual_hold.HELD, "op-7"),
             ("customer.manual_hold", manual_hold.RELEASED, "op-8"),
             ("customer.manual_hold", manual_hold.REFUSED, "op-9")])

    def test_a_release_the_reactivation_site_did_not_carry_out_is_a_failure(self):
        """An internal failure at the reactivation site (which it swallows and
        logs) is reported as a failure that can be retried, never as a
        refusal; the hold stands."""
        manual_hold.place_manual_hold(self.solo.id, operator="op-1")
        with patch("apps.billing.gating.services.live_counter.LiveCounter.clear_manual_hold",
                   return_value=False), \
                self.assertRaisesMessage(manual_hold.ManualHoldFailed, "can be retried"):
            manual_hold.release_manual_hold(self.solo.id, operator="op-1")
        self.assertEqual(self.standing(self.solo), ("suspended", ""))
        self.assertEqual(self.events(self.solo, "customer.reactivated"), [])


class TheOperatorCommandTest(_ManualHoldCase):
    def _run(self, *args):
        from io import StringIO
        out = StringIO()
        call_command("set_customer_manual_hold", *args, stdout=out)
        return out.getvalue()

    def test_held_then_released(self):
        out = self._run("--customer", str(self.seat.id), "--state", "held", "--operator", "op-1")
        self.assertIn("now under a manual hold", out)
        self.assertEqual(self.standing(self.seat), ("suspended", ""))
        out = self._run("--customer", str(self.seat.id), "--state", "released",
                        "--operator", "op-1")
        self.assertIn("manual hold is released", out)
        self.assertEqual(self.standing(self.seat), ("active", ""))

    def test_holding_a_held_customer_reports_it_and_changes_nothing(self):
        self._run("--customer", str(self.solo.id), "--state", "held", "--operator", "op-1")
        out = self._run("--customer", str(self.solo.id), "--state", "held", "--operator", "op-1")
        self.assertIn("already under a manual hold", out)
        self.assertEqual(len(self.events(self.solo, "customer.suspended")), 1)

    def test_a_failed_release_is_reported_as_a_failure(self):
        self._run("--customer", str(self.solo.id), "--state", "held", "--operator", "op-1")
        with patch("apps.billing.gating.services.live_counter.LiveCounter.clear_manual_hold",
                   return_value=False), self.assertRaisesMessage(CommandError, "failed:"):
            self._run("--customer", str(self.solo.id), "--state", "released",
                      "--operator", "op-1")
        self.assertEqual(self.standing(self.solo), ("suspended", ""))

    def test_a_system_cause_is_refused_and_nothing_changes(self):
        self.suspend_for(self.solo, reasons.HARD_FLOOR)
        for state in ("held", "released"):
            with self.subTest(state), self.assertRaisesMessage(CommandError, "refused"):
                self._run("--customer", str(self.solo.id), "--state", state,
                          "--operator", "op-1")
        self.assertEqual(self.standing(self.solo), ("suspended", reasons.HARD_FLOOR))

    def test_the_operator_customer_and_state_are_required_and_checked(self):
        cases = {
            "blank operator": (("--customer", str(self.solo.id), "--state", "held",
                                "--operator", " "), "--operator must name"),
            "no operator": (("--customer", str(self.solo.id), "--state", "held"),
                            "--operator"),
            "not a uuid": (("--customer", "solo", "--state", "held", "--operator", "op-1"),
                           "is not a customer id"),
            "unknown customer": (("--customer", "00000000-0000-0000-0000-000000000000",
                                  "--state", "held", "--operator", "op-1"),
                                 "no live customer"),
            "no such state": (("--customer", str(self.solo.id), "--state", "closed",
                               "--operator", "op-1"), "invalid choice"),
        }
        for name, (args, message) in cases.items():
            with self.subTest(name), self.assertRaisesMessage(CommandError, message):
                self._run(*args)
        self.assertEqual(self.standing(self.solo), ("active", ""))
