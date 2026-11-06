"""The manual hold: one operator workflow to place and release a deliberate
hold on a customer (R10 Stage C4; owner/consultant ruling 2026-11-05, PLAN §7
item 41, FINAL).

The hold is the existing representation — ``suspended`` with an EMPTY reason —
placed through ``apps/billing/gating/services/manual_hold.py`` (announcing
``customer.suspended`` and notifying a seat's roster once) and released through
the one reactivation site. It never overwrites, and its release never clears, a
cause its own recovery owns (``hard_floor``, ``customer_spend_pool``,
``payment_failed``, ``dispute_lost``). A release removes the MANUAL cause and
never forces the customer active (Ruling B): with nothing else standing the
customer is active again, ``customer.reactivated`` is announced and a seat's
roster notified, once; a system condition still standing takes over instead,
with nothing announced. The operator surface is ``manage.py
set_customer_manual_hold``; the Django admin no longer edits ``status`` or
``suspension_reason``.
"""
import datetime
from unittest.mock import MagicMock, patch

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

    def saved_states(self, customer):
        """Every ``(status, suspension_reason)`` the customer's row is SAVED with
        from here on — so a release that wrote ``active`` and then changed its
        mind would show it, even inside one transaction. It sees ``save()``
        only (``post_save``), which is how the one reactivation site writes; a
        ``QuerySet.update()`` would pass it unseen."""
        from django.db.models.signals import post_save

        states = []

        def record(sender, instance, **kwargs):
            if instance.pk == customer.pk:
                states.append((instance.status, instance.suspension_reason))

        post_save.connect(record, sender=Customer, weak=False)
        self.addCleanup(post_save.disconnect, record, sender=Customer)
        return states

    def stand_a_payment_failure(self, customer):
        """A qualifying failed invoice against ``customer`` (RULED Q4)."""
        from apps.billing.invoicing.models import CustomerUsageInvoice
        CustomerUsageInvoice.objects.create(
            tenant=customer.tenant, customer=customer,
            period_start=datetime.date(2026, 1, 1), period_end=datetime.date(2026, 2, 1),
            total_billed_micros=1_000_000, status="pushed", stripe_invoice_id="in_failed",
            payment_failed_at=timezone.now())


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
        """RULED Q4 and Ruling B: a qualifying failed invoice holds the owner at
        any other recovery, and the cause hands over to ``payment_failed``. The
        hold IS released — answered as handed over, not failed — and the
        customer never passes through ``active``: no ``customer.reactivated``,
        no second ``customer.suspended``, no roster change."""
        manual_hold.place_manual_hold(self.seat.id, operator="op-1")
        self.notified.clear()
        self.stand_a_payment_failure(self.seat)
        saved = self.saved_states(self.seat)
        self.assertEqual(manual_hold.release_manual_hold(self.seat.id, operator="op-1"),
                         manual_hold.HANDED_OVER)
        self.assertEqual(self.standing(self.seat), ("suspended", reasons.PAYMENT_FAILED))
        self.assertEqual(saved, [("suspended", reasons.PAYMENT_FAILED)])
        self.assertEqual(self.events(self.seat, "customer.reactivated"), [])
        self.assertEqual(len(self.events(self.seat, "customer.suspended")), 1)  # the hold's
        self.assertEqual(self.notified, [])

    def test_a_second_release_after_a_hand_over_writes_nothing(self):
        """Idempotent as the command's convention reads it: nothing is written
        twice. The hold is already gone, and what stands now is a system cause,
        which a release refuses as it refuses any other."""
        manual_hold.place_manual_hold(self.solo.id, operator="op-1")
        self.stand_a_payment_failure(self.solo)
        manual_hold.release_manual_hold(self.solo.id, operator="op-1")
        saved = self.saved_states(self.solo)
        with self.assertRaisesMessage(manual_hold.ManualHoldRefused, "not a manual hold"):
            manual_hold.release_manual_hold(self.solo.id, operator="op-1")
        self.assertEqual(saved, [])
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


class AReleaseNeverForcesActiveTest(_ManualHoldCase):
    """RELEASING A MANUAL HOLD REMOVES THE MANUAL CAUSE; IT NEVER FORCES THE
    CUSTOMER ACTIVE (owner/consultant Ruling B, 2026-11-05, PLAN §7 item 41).

    No suspend path records a cause on a customer that is already suspended:
    the drawdown's level test, a stop line's fold and a lost dispute's
    claw-back each suspend only an ACTIVE owner. So a system condition can
    arise under a hold with nothing written — and before Ruling B the release
    made such a customer active. The release now asks, under the row lock, the
    gate every money lift passes (a stop line still open under ``enforcing``;
    a wallet past its floor); a cause that stands takes over, the customer
    stays suspended with nothing announced, and that cause's own recovery
    brings it back later — the ``customer.reactivated`` then is the real
    transition's, once."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        from apps.platform.tenants.tests._rails import activate_the_rail
        activate_the_rail()          # a money mode needs its payment rail (G27)
        cache.clear()

    def _prepaid(self, enforcement_mode, **fields):
        return Tenant.objects.create(
            name=f"Prepaid {enforcement_mode}", products=["metering", "billing"],
            billing_mode="prepaid", enforcement_mode=enforcement_mode, **fields)

    def _funded(self, tenant, external_id, balance_micros):
        from apps.billing.wallets.models import Wallet
        customer = Customer.objects.create(tenant=tenant, external_id=external_id)
        Wallet.objects.create(customer=customer, balance_micros=balance_micros)
        return customer

    def _billed_under_the_hold(self, tenant, customer, usage_micros):
        """A usage the customer recorded while still active, billed after the
        hold: the outbox handler draws the wallet down asynchronously."""
        import uuid
        from dataclasses import asdict
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.metering.usage.tests._helpers import a_posting
        from apps.platform.events.schemas import UsageRecorded
        posting = a_posting(tenant=tenant, customer=customer, idempotency_key="u1",
                            provider_cost_micros=usage_micros,
                            billed_cost_micros=usage_micros)
        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            pricing_status_reason=None, tenant_id=tenant.id, customer_id=customer.id,
            event_id=str(posting.id), cost_micros=usage_micros)))

    def test_with_nothing_standing_a_prepaid_release_makes_it_active_once(self):
        """The control: a healthy wallet, no line, no failure — active again."""
        tenant = self._prepaid("off")
        customer = self._funded(tenant, "healthy", 5_000_000)
        manual_hold.place_manual_hold(customer.id, operator="op-1")
        self.assertEqual(manual_hold.release_manual_hold(customer.id, operator="op-1"),
                         manual_hold.RELEASED)
        self.assertEqual(self.standing(customer), ("active", ""))
        [reactivated] = self.events(customer, "customer.reactivated")
        self.assertEqual(reactivated["reason_code"], "")

    def test_a_wallet_past_its_floor_under_the_hold_keeps_it_suspended_for_the_floor(self):
        from apps.billing.wallets import operations as wallet_ops
        tenant = self._prepaid("off")
        customer = self._funded(tenant, "drawn", 5_000_000)
        manual_hold.place_manual_hold(customer.id, operator="op-1")
        self._billed_under_the_hold(tenant, customer, 8_000_000)     # 5M - 8M = -3M
        # The level test suspends only an active owner: the floor was crossed
        # under the hold and nothing recorded it.
        self.assertEqual(self.standing(customer), ("suspended", ""))
        saved = self.saved_states(customer)

        outcome = manual_hold.release_manual_hold(customer.id, operator="op-1")
        self.assertEqual(self.standing(customer), ("suspended", reasons.HARD_FLOOR))
        self.assertEqual(saved, [("suspended", reasons.HARD_FLOOR)])   # never active
        self.assertEqual(self.events(customer, "customer.reactivated"), [])
        self.assertEqual(len(self.events(customer, "customer.suspended")), 1)  # the hold's
        self.assertEqual((outcome, outcome.cause),
                         (manual_hold.HANDED_OVER, reasons.HARD_FLOOR))

        # The floor's own recovery brings it back: a credit over the floor.
        with patch("apps.platform.events.tasks.process_single_event"), \
                self.captureOnCommitCallbacks(execute=True):
            wallet_ops.credit(customer_id=customer.id, tenant=tenant,
                              amount_micros=10_000_000, idempotency_key="cr1")
        self.assertEqual(self.standing(customer), ("active", ""))
        [reactivated] = self.events(customer, "customer.reactivated")
        self.assertEqual(reactivated["reason_code"], reasons.HARD_FLOOR)

    def test_an_open_stop_line_keeps_it_suspended_on_that_lines_word(self):
        from apps.billing.gating.services.live_counter import LiveCounter
        from apps.billing.gating.services.stop_signal_service import (
            CLEAR_RECONCILED, STOP_LINES, StopSignalService, control_id_of)
        from core.vocabulary import TRIGGER_SOURCE_ENFORCEMENT_PATROL
        tenant = self._prepaid("enforcing")
        for line in STOP_LINES:
            with self.subTest(line):
                customer = self._funded(tenant, f"held-{line}", 5_000_000)
                manual_hold.place_manual_hold(customer.id, operator="op-1")
                StopSignalService.drive_stop(
                    customer.id, tenant, line=line,
                    control_id=control_id_of(line, customer.id, tenant),
                    trigger_source=TRIGGER_SOURCE_ENFORCEMENT_PATROL,
                    stop_bound_micros=0, stop_measured_micros=0)
                # The stop's fold suspends only an active owner: the held one
                # keeps the empty reason while the line holds it.
                self.assertEqual(self.standing(customer), ("suspended", ""))
                saved = self.saved_states(customer)

                outcome = manual_hold.release_manual_hold(customer.id, operator="op-1")
                self.assertEqual(self.standing(customer), ("suspended", line))
                self.assertEqual(saved, [("suspended", line)])
                self.assertEqual(self.events(customer, "customer.reactivated"), [])
                self.assertEqual((outcome, outcome.cause), (manual_hold.HANDED_OVER, line))

                # The line lifting brings it back, through `resume`, once.
                LiveCounter.resume(customer.id, tenant, line=line,
                                   clear_reason=CLEAR_RECONCILED, balance_micros=5_000_000)
                self.assertEqual(self.standing(customer), ("active", ""))
                [reactivated] = self.events(customer, "customer.reactivated")
                self.assertEqual(reactivated["reason_code"], line)

    def test_a_dispute_lost_under_the_hold_keeps_it_suspended_for_the_floor(self):
        """The lost dispute's claw-back suspends only an ACTIVE owner, so a
        dispute lost under the hold drives the wallet past its floor with
        nothing recorded; the release finds the floor, not ``active``. Under
        both modes — under ``enforcing`` too a claw-back opens no stop line
        (it is not mirrored to the live counter), so it is the floor read, not
        a line, that holds it — and the floor's own recovery lifts it."""
        from apps.billing.connectors.stripe.webhooks import handle_charge_dispute_closed
        from apps.billing.gating.services.stop_signal_service import StopSignalService
        from apps.billing.topups.models import TopUpAttempt
        from apps.billing.wallets import operations as wallet_ops
        from apps.billing.wallets.models import Wallet
        from core.vocabulary import GRANT_SOURCE_CHECKOUT
        for mode in ("off", "enforcing"):
            with self.subTest(mode):
                tenant = self._prepaid(mode, stripe_connected_account_id=f"acct_{mode}")
                customer = self._funded(tenant, f"disputed-{mode}", 0)
                attempt = TopUpAttempt.objects.create(
                    customer=customer, billing_owner_id=customer.id,
                    amount_micros=5_000_000, trigger="manual", status="succeeded",
                    stripe_charge_id=f"ch_{mode}")
                wallet_ops.credit_top_up(
                    customer_id=customer.id, tenant=tenant, amount_micros=5_000_000,
                    idempotency_key=f"topup:cs_{mode}", source=GRANT_SOURCE_CHECKOUT,
                    source_reference=str(attempt.id), description="Stripe top-up")
                manual_hold.place_manual_hold(customer.id, operator="op-1")
                lost = MagicMock()
                lost.data.object.id = f"dp_{mode}"
                lost.data.object.charge = f"ch_{mode}"
                lost.data.object.status = "lost"
                lost.data.object.amount = 800                 # cents: 8M micros
                lost.data.object.currency = "usd"
                lost.account = f"acct_{mode}"
                handle_charge_dispute_closed(lost)             # 5M - 8M = -3M, under the hold
                self.assertEqual(Wallet.objects.get(customer=customer).balance_micros,
                                 -3_000_000)
                self.assertEqual(self.standing(customer), ("suspended", ""))  # unrecorded
                self.assertEqual(StopSignalService.open_stop_lines(customer.id), [])
                saved = self.saved_states(customer)

                outcome = manual_hold.release_manual_hold(customer.id, operator="op-1")
                self.assertEqual(self.standing(customer), ("suspended", reasons.HARD_FLOOR))
                self.assertEqual(saved, [("suspended", reasons.HARD_FLOOR)])
                self.assertEqual(self.events(customer, "customer.reactivated"), [])
                self.assertEqual((outcome, outcome.cause),
                                 (manual_hold.HANDED_OVER, reasons.HARD_FLOOR))

                # A credit back over the floor lifts it, once, in either mode.
                with patch("apps.platform.events.tasks.process_single_event"), \
                        self.captureOnCommitCallbacks(execute=True):
                    wallet_ops.credit(customer_id=customer.id, tenant=tenant,
                                      amount_micros=10_000_000, idempotency_key=f"cr_{mode}")
                self.assertEqual(self.standing(customer), ("active", ""))
                [reactivated] = self.events(customer, "customer.reactivated")
                self.assertEqual(reactivated["reason_code"], reasons.HARD_FLOOR)

    def test_a_payment_failure_and_a_wallet_past_its_floor_leave_payment_failed(self):
        """Both stand. The payment failure is asked first (RULED Q4, and Ruling
        B's "the resulting suspension_reason is payment_failed"), so that is
        the reason, and the customer stays suspended either way. When that
        failure later resolves, the floor takes over (PLAN §7 item 43) — the
        whole sequence is pinned in ``api/v1/tests/test_wave5a_ar_capstone.py``
        (``TestAPaymentRecoveryHandsOverToAStandingMoneyCause``)."""
        tenant = self._prepaid("off")
        customer = self._funded(tenant, "both", 5_000_000)
        manual_hold.place_manual_hold(customer.id, operator="op-1")
        self._billed_under_the_hold(tenant, customer, 8_000_000)     # past the floor
        self.stand_a_payment_failure(customer)
        saved = self.saved_states(customer)

        outcome = manual_hold.release_manual_hold(customer.id, operator="op-1")
        self.assertEqual(self.standing(customer), ("suspended", reasons.PAYMENT_FAILED))
        self.assertEqual(saved, [("suspended", reasons.PAYMENT_FAILED)])
        self.assertEqual(self.events(customer, "customer.reactivated"), [])
        self.assertEqual(outcome, manual_hold.HANDED_OVER)

    def test_under_off_a_stop_line_left_by_a_mode_flip_holds_nothing(self):
        """The ledger's lines are ``enforcing``'s controls; a mode flip closes
        them silently, best-effort. One left open by a failed close is no
        cause under ``off``, where nothing would ever lift it: a release with
        a healthy wallet and no failure is active again, not handed to it."""
        from apps.billing.gating.services.stop_signal_service import (
            LINE_CUSTOMER_SPEND_POOL, StopSignalService, control_id_of)
        from core.vocabulary import TRIGGER_SOURCE_ENFORCEMENT_PATROL
        tenant = self._prepaid("off")
        customer = self._funded(tenant, "stale-line", 5_000_000)
        manual_hold.place_manual_hold(customer.id, operator="op-1")
        StopSignalService.drive_stop(
            customer.id, tenant, line=LINE_CUSTOMER_SPEND_POOL,
            control_id=control_id_of(LINE_CUSTOMER_SPEND_POOL, customer.id, tenant),
            trigger_source=TRIGGER_SOURCE_ENFORCEMENT_PATROL,
            stop_bound_micros=0, stop_measured_micros=0)
        self.assertEqual([row["reason"] for row in
                          StopSignalService.open_stop_lines(customer.id)],
                         [LINE_CUSTOMER_SPEND_POOL])                    # left open
        self.assertEqual(manual_hold.release_manual_hold(customer.id, operator="op-1"),
                         manual_hold.RELEASED)
        self.assertEqual(self.standing(customer), ("active", ""))

    def test_a_pooled_seat_is_measured_by_no_floor_of_its_own(self):
        """A pooled seat is not its floor's subject: every floor path suspends
        its BUSINESS (which gates the seat), never the seat. So a held seat
        whose business is past its floor is released active, and the business
        stays suspended for its floor — nothing is stranded on a seat that no
        floor recovery would ever visit."""
        from apps.billing.wallets.models import Wallet
        tenant = self._prepaid("off")
        business = Customer.objects.create(
            tenant=tenant, external_id="pooled", account_type="business",
            billing_topology="pooled")
        Wallet.objects.create(customer=business, balance_micros=-3_000_000)
        self.suspend_for(business, reasons.HARD_FLOOR)
        seat = Customer.objects.create(tenant=tenant, external_id="pooled-seat",
                                       account_type="seat", parent=business)
        manual_hold.place_manual_hold(seat.id, operator="op-1")
        self.assertEqual(manual_hold.release_manual_hold(seat.id, operator="op-1"),
                         manual_hold.RELEASED)
        self.assertEqual(self.standing(seat), ("active", ""))
        self.assertEqual(self.standing(business), ("suspended", reasons.HARD_FLOOR))


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

    def test_a_release_handed_over_says_so_and_is_not_a_failure(self):
        self._run("--customer", str(self.solo.id), "--state", "held", "--operator", "op-1")
        self.stand_a_payment_failure(self.solo)
        out = self._run("--customer", str(self.solo.id), "--state", "released",
                        "--operator", "op-1")
        self.assertIn("manual hold is released, but it remains suspended for "
                      "'payment_failed', a system cause its own recovery lifts", out)
        self.assertEqual(self.standing(self.solo), ("suspended", reasons.PAYMENT_FAILED))

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
