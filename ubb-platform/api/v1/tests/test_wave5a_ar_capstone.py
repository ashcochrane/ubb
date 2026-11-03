"""Wave-5a AR-visibility CAPSTONE (Stripe MOCKED).

Proves the FULL accounts-receivable reconcile loop end-to-end against the real
handlers, driving SYNTHETIC Stripe events (same construction style as
api/v1/tests/test_ar_reconcile.py) — no network, no real Stripe.

Covered end-to-end:
  * usage standalone invoice: finalized -> payment_failed -> paid
      (open + url/pdf stored; payment_failed_at stamped + hosted url ROTATED;
       then paid + paid_at; monotonic open->...->paid never regresses)
  * subscription invoice: finalized -> payment_failed -> voided
      (open SubscriptionInvoice row created w/ url/pdf; payment_failed_at
       stamped + hosted url ROTATED; then void — full parity with usage path)
  * idempotency / duplicate delivery (no error, no double-apply)
  * out-of-order finalized AFTER paid does NOT regress paid -> open (monotonic)
  * event.account mismatch -> no write
  * /me visibility: billing owner sees the reconciled rows (w/ refreshed url);
    a pooled seat sees nothing (consolidated bill belongs to the business)
"""
from types import SimpleNamespace
from datetime import date

from django.test import TestCase, Client
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.models import SubscriptionInvoice
from apps.billing.invoicing.models import CustomerUsageInvoice
from core.widget_auth import create_widget_token

from api.v1.webhooks import (
    handle_invoice_finalized,
    handle_invoice_paid,
    handle_invoice_voided,
)
from apps.billing.connectors.stripe.webhooks import handle_invoice_payment_failed
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import CustomerReactivated
from apps.platform.work import reasons
from apps.subscriptions.tests._helpers import a_mirrored_subscription


# --- synthetic event helpers (mirror test_ar_reconcile.py) ------------------

def _event(account, *, obj):
    return SimpleNamespace(account=account, data=SimpleNamespace(object=obj))


def _usage_obj(invoice_id, *, hosted_url="", pdf=""):
    """A standalone usage invoice object — no subscription linkage."""
    return SimpleNamespace(
        id=invoice_id,
        customer="cus_capstone",
        subscription=None,
        parent=None,
        hosted_invoice_url=hosted_url,
        invoice_pdf=pdf,
        amount_paid=0,
        currency="usd",
    )


def _sub_obj(invoice_id, subscription_id, *, amount_paid=4900, hosted_url="",
             pdf="", period_start=1738368000, period_end=1740960000,
             paid_at_ts=1738400000):
    """A subscription invoice object — Basil legacy `.subscription` linkage."""
    return SimpleNamespace(
        id=invoice_id,
        customer="cus_capstone",
        subscription=subscription_id,
        parent=None,
        amount_paid=amount_paid,
        currency="usd",
        hosted_invoice_url=hosted_url,
        invoice_pdf=pdf,
        period_start=period_start,
        period_end=period_end,
        status_transitions=SimpleNamespace(paid_at=paid_at_ts),
    )


class TestWave5aARCapstone(TestCase):
    """The full AR loop, mocked, driven through the real handlers."""

    ACCT = "acct_capstone"

    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(
            name="Capstone",
            products=["metering", "billing"],
            stripe_connected_account_id=self.ACCT,
        )
        # Billing owner = an individual customer (owns its own bill).
        self.owner = Customer.objects.create(
            tenant=self.tenant, external_id="owner",
            account_type="individual",
        )
        now = timezone.now()
        self.sub = a_mirrored_subscription(
            tenant=self.tenant, customer=self.owner,
            stripe_subscription_id="sub_capstone",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        # A pre-pushed standalone usage invoice (no subscription).
        self.usage_inv = CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self.owner,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            total_billed_micros=12_340_000,
            status="pushed", stripe_invoice_id="in_usage_cap",
        )

    def _token(self, customer):
        return create_widget_token(
            self.tenant.widget_secret, str(customer.id), str(self.tenant.id)
        )

    def _me(self, path, customer):
        return self.client.get(
            path, HTTP_AUTHORIZATION=f"Bearer {self._token(customer)}"
        )

    # -- 1a. usage: finalized -> payment_failed (url rotates) -> paid ---------

    def test_usage_invoice_full_loop_with_url_rotation_on_payment_failed(self):
        acct = self.ACCT

        # finalized -> open + url/pdf stored
        handle_invoice_finalized(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://pay/v1", pdf="https://pdf/v1")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "open")
        self.assertEqual(self.usage_inv.hosted_invoice_url, "https://pay/v1")
        self.assertEqual(self.usage_inv.invoice_pdf, "https://pdf/v1")
        self.assertIsNone(self.usage_inv.payment_failed_at)
        first_url = self.usage_inv.hosted_invoice_url

        # payment_failed -> payment_failed_at stamped + hosted url ROTATED to a
        # NEW value (Stripe rotates the token); payment_status stays open (the
        # failed attempt is not a terminal status, so it does NOT regress).
        handle_invoice_payment_failed(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://pay/v2-ROTATED",
            pdf="https://pdf/v2-ROTATED")))
        self.usage_inv.refresh_from_db()
        self.assertIsNotNone(self.usage_inv.payment_failed_at)
        # THE load-bearing assertion: the stored url actually changed.
        self.assertNotEqual(self.usage_inv.hosted_invoice_url, first_url)
        self.assertEqual(self.usage_inv.hosted_invoice_url, "https://pay/v2-ROTATED")
        self.assertEqual(self.usage_inv.invoice_pdf, "https://pdf/v2-ROTATED")
        self.assertEqual(self.usage_inv.payment_status, "open")  # not regressed

        # paid -> paid + paid_at
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "paid")
        self.assertIsNotNone(self.usage_inv.paid_at)
        # url was not cleared by the (blank-url) paid event
        self.assertEqual(self.usage_inv.hosted_invoice_url, "https://pay/v2-ROTATED")

    # -- 1b. subscription: finalized -> voided -------------------------------

    def test_subscription_invoice_finalized_creates_open_row_then_voided(self):
        acct = self.ACCT

        # finalized -> creates an OPEN SubscriptionInvoice row w/ url/pdf
        handle_invoice_finalized(_event(acct, obj=_sub_obj(
            "in_sub_cap", "sub_capstone",
            hosted_url="https://pay/s1", pdf="https://pdf/s1")))
        rows = SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_cap")
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.status, "open")
        self.assertEqual(row.hosted_invoice_url, "https://pay/s1")
        self.assertEqual(row.invoice_pdf, "https://pdf/s1")
        self.assertIsNone(row.paid_at)

        # voided -> status void (same row, no second row)
        handle_invoice_voided(_event(acct, obj=_sub_obj("in_sub_cap", "sub_capstone")))
        self.assertEqual(
            SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_cap").count(), 1)
        row.refresh_from_db()
        self.assertEqual(row.status, "void")

    # -- 2. idempotency / ordering -------------------------------------------

    def test_duplicate_paid_delivery_is_idempotent(self):
        acct = self.ACCT
        handle_invoice_finalized(_event(acct, obj=_usage_obj("in_usage_cap")))
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        self.usage_inv.refresh_from_db()
        first_paid_at = self.usage_inv.paid_at
        self.assertEqual(self.usage_inv.payment_status, "paid")

        # re-deliver the SAME paid event: no error, no double, paid_at frozen
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "paid")
        self.assertEqual(self.usage_inv.paid_at, first_paid_at)

    def test_out_of_order_finalized_after_paid_does_not_regress(self):
        acct = self.ACCT
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "paid")
        paid_at = self.usage_inv.paid_at

        # a LATE finalized arrives out of order -> must NOT regress paid -> open
        handle_invoice_finalized(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://late")))
        self.usage_inv.refresh_from_db()
        self.assertEqual(self.usage_inv.payment_status, "paid")  # monotonic
        self.assertEqual(self.usage_inv.paid_at, paid_at)
        # url still refreshes (non-status field) even when status is terminal
        self.assertEqual(self.usage_inv.hosted_invoice_url, "https://late")

    def test_subscription_duplicate_finalized_does_not_create_second_row(self):
        acct = self.ACCT
        handle_invoice_finalized(_event(acct, obj=_sub_obj("in_sub_dup", "sub_capstone")))
        handle_invoice_finalized(_event(acct, obj=_sub_obj("in_sub_dup", "sub_capstone")))
        self.assertEqual(
            SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_dup").count(), 1)

    # -- 3. account mismatch -> no write -------------------------------------

    def test_account_mismatch_no_write_usage(self):
        handle_invoice_finalized(_event(
            "acct_WRONG", obj=_usage_obj("in_usage_cap", hosted_url="https://x")))
        self.usage_inv.refresh_from_db()
        self.assertIsNone(self.usage_inv.payment_status)  # untouched
        self.assertEqual(self.usage_inv.hosted_invoice_url, "")

    def test_account_mismatch_no_row_subscription(self):
        handle_invoice_finalized(_event(
            "acct_WRONG", obj=_sub_obj("in_sub_mismatch", "sub_capstone")))
        self.assertFalse(
            SubscriptionInvoice.objects.filter(stripe_invoice_id="in_sub_mismatch").exists())

    # -- 4. /me visibility ----------------------------------------------------

    def test_me_endpoints_surface_reconciled_rows_for_billing_owner(self):
        acct = self.ACCT
        # drive both invoices to their reconciled states
        handle_invoice_finalized(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://pay/u1", pdf="https://pdf/u1")))
        handle_invoice_payment_failed(_event(acct, obj=_usage_obj(
            "in_usage_cap", hosted_url="https://pay/u2-ROT", pdf="https://pdf/u2-ROT")))
        handle_invoice_paid(_event(acct, obj=_usage_obj("in_usage_cap")))
        handle_invoice_finalized(_event(acct, obj=_sub_obj(
            "in_sub_cap", "sub_capstone", hosted_url="https://pay/s1", pdf="https://pdf/s1")))

        # billing owner sees the reconciled usage invoice
        usage_resp = self._me("/api/v1/me/usage-invoices", self.owner)
        self.assertEqual(usage_resp.status_code, 200)
        u = usage_resp.json()["data"]
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0]["payment_status"], "paid")
        self.assertEqual(u[0]["hosted_invoice_url"], "https://pay/u2-ROT")  # rotated
        self.assertEqual(u[0]["stripe_invoice_id"], "in_usage_cap")

        # billing owner sees the reconciled subscription invoice
        sub_resp = self._me("/api/v1/me/subscription-invoices", self.owner)
        self.assertEqual(sub_resp.status_code, 200)
        s = sub_resp.json()["data"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["status"], "open")
        self.assertEqual(s[0]["hosted_invoice_url"], "https://pay/s1")

    def test_me_endpoints_empty_for_pooled_seat(self):
        # a pooled seat under a business does NOT own the consolidated bill
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled",
        )
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat",
            parent=business,
        )
        # both invoices belong to the BUSINESS
        CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=business,
            period_start=date(2026, 2, 1), period_end=date(2026, 3, 1),
            status="pushed", stripe_invoice_id="in_biz_usage",
            payment_status="paid", hosted_invoice_url="https://biz/u",
        )
        now = timezone.now()
        biz_sub = a_mirrored_subscription(
            tenant=self.tenant, customer=business,
            stripe_subscription_id="sub_biz",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        SubscriptionInvoice.objects.create(
            tenant=self.tenant, customer=business, stripe_subscription=biz_sub,
            stripe_invoice_id="in_biz_sub", amount_paid_micros=49_000_000,
            status="paid", hosted_invoice_url="https://biz/s",
        )

        # the pooled seat sees NOTHING (sibling-spend isolation)
        seat_usage = self._me("/api/v1/me/usage-invoices", seat)
        self.assertEqual(seat_usage.status_code, 200)
        self.assertEqual(seat_usage.json()["data"], [])
        seat_sub = self._me("/api/v1/me/subscription-invoices", seat)
        self.assertEqual(seat_sub.status_code, 200)
        self.assertEqual(seat_sub.json()["data"], [])

        # while the business DOES see both
        biz_usage = self._me("/api/v1/me/usage-invoices", business)
        self.assertEqual(len(biz_usage.json()["data"]), 1)
        biz_sub_resp = self._me("/api/v1/me/subscription-invoices", business)
        self.assertEqual(len(biz_sub_resp.json()["data"]), 1)


class TestSubscriptionPaymentFailed(TestCase):
    """A SUBSCRIPTION invoice.payment_failed now stamps payment_failed_at AND
    refreshes hosted_invoice_url + invoice_pdf on the SubscriptionInvoice row,
    with full parity to the usage-invoice path.

    SubscriptionInvoice.payment_failed_at was added (by `subscriptions/0008`,
    before the cutover squash, #190) to close the gap that caused the
    connector to raise ValueError on every subscription payment-failed event
    (retrying forever in production).
    """

    ACCT = "acct_pf_sub"

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="PFSub", products=["metering", "billing"],
            stripe_connected_account_id=self.ACCT,
        )
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        now = timezone.now()
        self.sub = a_mirrored_subscription(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription_id="sub_pf_sub",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        self.row = SubscriptionInvoice.objects.create(
            tenant=self.tenant, customer=self.customer, stripe_subscription=self.sub,
            stripe_invoice_id="in_pf_sub", amount_paid_micros=0,
            status="open", hosted_invoice_url="https://orig",
        )

    def test_subscription_payment_failed_stamps_field_and_rotates_url(self):
        """invoice.payment_failed on a subscription invoice:
        - stamps payment_failed_at
        - rotates hosted_invoice_url to the new Stripe token
        - does NOT raise
        - does NOT change the status (open is non-terminal)
        """
        ev = _event(self.ACCT, obj=_sub_obj("in_pf_sub", "sub_pf_sub",
                                             hosted_url="https://rotated",
                                             pdf="https://pdf-rotated"))
        # must not raise
        handle_invoice_payment_failed(ev)

        self.row.refresh_from_db()
        # payment_failed_at is now stamped
        self.assertIsNotNone(self.row.payment_failed_at)
        # hosted url was rotated to the new Stripe token
        self.assertEqual(self.row.hosted_invoice_url, "https://rotated")
        self.assertEqual(self.row.invoice_pdf, "https://pdf-rotated")
        # status is unchanged (payment failure is not terminal)
        self.assertEqual(self.row.status, "open")

    def test_subscription_payment_failed_no_regress_on_terminal_status(self):
        """payment_failed after a terminal status does not overwrite the status,
        but still stamps payment_failed_at and refreshes the url (non-status
        fields are always updated).
        """
        self.row.status = "void"
        self.row.save(update_fields=["status", "updated_at"])

        ev = _event(self.ACCT, obj=_sub_obj("in_pf_sub", "sub_pf_sub",
                                             hosted_url="https://rotated2"))
        handle_invoice_payment_failed(ev)

        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.payment_failed_at)
        self.assertEqual(self.row.hosted_invoice_url, "https://rotated2")
        # status stays void — the save only touches payment_failed_at/url/pdf/updated_at
        self.assertEqual(self.row.status, "void")


class TestPaymentFailedSuspensionClearsFromDurableTruth(TestCase):
    """R10 Stage C2, F-6 (BILLING BLOCKER), RULED Q4.

    A payment-failure suspension targets the canonical billing OWNER of the
    MATCHED LOCAL usage/subscription invoice, writes
    `suspension_reason = payment_failed` and emits `customer.suspended`; a
    Stripe invoice with no local row suspends nobody. `invoice.paid` clears
    THAT invoice's `payment_failed_at` and reactivates only a customer
    suspended for `payment_failed`, and only when no other qualifying
    failed/unpaid local invoice (usage or subscription) of that owner
    remains; payment resolution never clears any other reason; the real
    transition emits `customer.reactivated` exactly once.

    Before C2 the suspend wrote no reason, targeted whichever local customer
    carried the Stripe customer id, and nothing ever reinstated the customer
    (`R10-BILLING-READINESS/evidence/05-postpaid.txt` step 9).
    """

    ACCT = "acct_c2_ar"

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="C2AR", products=["metering", "billing"],
            stripe_connected_account_id=self.ACCT)
        self.owner = Customer.objects.create(
            tenant=self.tenant, external_id="owner", stripe_customer_id="cus_owner")
        self.periods = iter(range(1, 12))

    # -- fixtures ------------------------------------------------------------

    def _usage_row(self, customer, stripe_invoice_id, **fields):
        month = next(self.periods)
        return CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=customer,
            period_start=date(2026, month, 1), period_end=date(2026, month + 1, 1),
            total_billed_micros=1_000_000, status="pushed",
            stripe_invoice_id=stripe_invoice_id, **fields)

    def _subscription_row(self, customer, stripe_invoice_id, sub_id, **fields):
        now = timezone.now()
        sub = a_mirrored_subscription(
            tenant=self.tenant, customer=customer, stripe_subscription_id=sub_id,
            stripe_product_name="Pro", status="active", amount_micros=49_000_000,
            currency="usd", interval="month", current_period_start=now,
            current_period_end=now, last_synced_at=now)
        return SubscriptionInvoice.objects.create(
            tenant=self.tenant, customer=customer, stripe_subscription=sub,
            stripe_invoice_id=stripe_invoice_id, amount_paid_micros=0,
            currency="usd", status="open", **fields)

    def _fail(self, obj):
        handle_invoice_payment_failed(_event(self.ACCT, obj=obj))

    def _pay(self, obj):
        handle_invoice_paid(_event(self.ACCT, obj=obj))

    def _suspended_events(self, customer):
        return OutboxEvent.objects.filter(
            event_type="customer.suspended", payload__customer_id=str(customer.id))

    def _reactivated(self, customer):
        return OutboxEvent.objects.filter(
            event_type=CustomerReactivated.EVENT_TYPE, payload__customer_id=str(customer.id))

    def _standing(self, customer):
        customer.refresh_from_db()
        return customer.status, customer.suspension_reason

    # -- the suspend --------------------------------------------------------

    def test_a_failed_local_usage_invoice_suspends_its_owner_with_the_reason_and_the_event(self):
        row = self._usage_row(self.owner, "in_c2_1")
        self._fail(_usage_obj("in_c2_1"))
        row.refresh_from_db()
        self.assertIsNotNone(row.payment_failed_at)
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self.assertEqual(self._suspended_events(self.owner).count(), 1)
        payload = self._suspended_events(self.owner).get().payload
        self.assertEqual(payload["reason"], reasons.PAYMENT_FAILED)
        self.assertIsNone(payload["balance_micros"])  # no wallet on this tenant
        # Idempotent: the redelivery suspends nothing twice and announces once.
        self._fail(_usage_obj("in_c2_1"))
        self.assertEqual(self._suspended_events(self.owner).count(), 1)

    def test_a_stripe_invoice_with_no_local_row_suspends_nobody(self):
        self._fail(_usage_obj("in_nobody_holds_this"))  # customer = cus_capstone
        other = Customer.objects.create(
            tenant=self.tenant, external_id="holder", stripe_customer_id="cus_capstone")
        self._fail(_usage_obj("in_nobody_holds_this"))  # the holder is not the owner of any invoice
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._standing(other), ("active", ""))
        self.assertFalse(OutboxEvent.objects.filter(event_type="customer.suspended").exists())

    def test_the_suspension_targets_the_invoices_billing_owner_not_the_stripe_customer_holder(self):
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat", parent=biz)
        holder = Customer.objects.create(
            tenant=self.tenant, external_id="holder", stripe_customer_id="cus_capstone")
        self._usage_row(seat, "in_seat_usage")      # a pooled seat's row: the business pays
        self._fail(_usage_obj("in_seat_usage"))     # the Stripe customer id names `holder`
        self.assertEqual(self._standing(biz), ("suspended", reasons.PAYMENT_FAILED))
        self.assertEqual(self._standing(seat), ("active", ""))
        self.assertEqual(self._standing(holder), ("active", ""))

    def test_a_late_failure_on_an_invoice_already_paid_suspends_nobody(self):
        """Stripe can deliver an earlier `invoice.payment_failed` after the
        `invoice.paid` that settled it: the stamp lands as it always has, but
        a settled invoice is not a standing failure, so nobody is suspended."""
        row = self._usage_row(self.owner, "in_c2_late", payment_status="paid",
                              paid_at=timezone.now())
        late = _usage_obj("in_c2_late")
        late.customer = "cus_owner"   # the owner's own Stripe customer
        self._fail(late)
        row.refresh_from_db()
        self.assertIsNotNone(row.payment_failed_at)
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertFalse(self._suspended_events(self.owner).exists())
        sub_row = self._subscription_row(self.owner, "in_c2_late_sub", "sub_c2_late")
        SubscriptionInvoice.objects.filter(id=sub_row.id).update(status="paid")
        late_sub = _sub_obj("in_c2_late_sub", "sub_c2_late")
        late_sub.customer = "cus_owner"
        self._fail(late_sub)
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertFalse(self._suspended_events(self.owner).exists())

    def test_a_failure_after_reactivation_suspends_the_owner_again(self):
        # The owner's standing is read under its row lock only, so a failure
        # that meets an owner a clear just made active suspends it again.
        self._usage_row(self.owner, "in_c2_a")
        self._usage_row(self.owner, "in_c2_b")
        self._fail(_usage_obj("in_c2_a"))
        self._pay(_usage_obj("in_c2_a"))
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self._fail(_usage_obj("in_c2_b"))
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self.assertEqual(self._suspended_events(self.owner).count(), 2)
        self.assertEqual(self._reactivated(self.owner).count(), 1)

    def test_a_standing_suspension_keeps_its_own_reason_when_a_payment_fails(self):
        Customer.objects.filter(id=self.owner.id).update(
            status="suspended", suspension_reason=reasons.HARD_FLOOR)
        self._usage_row(self.owner, "in_c2_1")
        self._fail(_usage_obj("in_c2_1"))
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.HARD_FLOOR))
        self.assertFalse(self._suspended_events(self.owner).exists())

    # -- the clear ----------------------------------------------------------

    def test_invoice_paid_clears_the_stamp_and_reactivates_with_the_reason_left(self):
        row = self._usage_row(self.owner, "in_c2_1")
        self._fail(_usage_obj("in_c2_1"))
        self._pay(_usage_obj("in_c2_1"))
        row.refresh_from_db()
        self.assertEqual(row.payment_status, "paid")
        self.assertIsNone(row.payment_failed_at)
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)
        payload = self._reactivated(self.owner).get().payload
        self.assertEqual(payload["tenant_id"], str(self.tenant.id))
        self.assertEqual(payload["reason_code"], reasons.PAYMENT_FAILED)
        self.assertIsNone(payload["balance_micros"])
        # The duplicate delivery reactivates nothing twice.
        self._pay(_usage_obj("in_c2_1"))
        self.assertEqual(self._reactivated(self.owner).count(), 1)

    def test_paying_one_invoice_never_clears_while_another_failure_remains(self):
        first = self._usage_row(self.owner, "in_c2_1")
        second = self._usage_row(self.owner, "in_c2_2")
        self._fail(_usage_obj("in_c2_1"))
        self._fail(_usage_obj("in_c2_2"))
        self._pay(_usage_obj("in_c2_1"))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.payment_failed_at)
        self.assertIsNotNone(second.payment_failed_at)
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self.assertFalse(self._reactivated(self.owner).exists())
        self._pay(_usage_obj("in_c2_2"))
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)

    def test_a_failed_subscription_invoice_of_the_owner_counts_as_a_remaining_failure(self):
        self._usage_row(self.owner, "in_c2_usage")
        self._subscription_row(self.owner, "in_c2_sub", "sub_c2")
        self._fail(_usage_obj("in_c2_usage"))
        self._fail(_sub_obj("in_c2_sub", "sub_c2"))
        self._pay(_usage_obj("in_c2_usage"))
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self._pay(_sub_obj("in_c2_sub", "sub_c2"))
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)
        self.assertEqual(self._reactivated(self.owner).get().payload["reason_code"],
                         reasons.PAYMENT_FAILED)

    def test_a_pooled_seats_failed_invoice_holds_the_business(self):
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat", parent=biz)
        self._usage_row(biz, "in_biz")
        self._usage_row(seat, "in_seat")
        self._fail(_usage_obj("in_biz"))
        self._fail(_usage_obj("in_seat"))
        self._pay(_usage_obj("in_biz"))
        self.assertEqual(self._standing(biz), ("suspended", reasons.PAYMENT_FAILED))
        self._pay(_usage_obj("in_seat"))
        self.assertEqual(self._standing(biz), ("active", ""))

    def test_the_subscription_path_suspends_and_clears_the_owner(self):
        row = self._subscription_row(self.owner, "in_c2_sub", "sub_c2")
        self._fail(_sub_obj("in_c2_sub", "sub_c2"))
        row.refresh_from_db()
        self.assertIsNotNone(row.payment_failed_at)
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self._pay(_sub_obj("in_c2_sub", "sub_c2"))
        row.refresh_from_db()
        self.assertEqual(row.status, "paid")
        self.assertIsNone(row.payment_failed_at)
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)

    def test_payment_resolution_never_clears_another_reason(self):
        for reason in (reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL,
                       reasons.DISPUTE_LOST, "", "fraud_review"):
            with self.subTest(reason=reason):
                owner = Customer.objects.create(
                    tenant=self.tenant, external_id=f"owner-{reason or 'manual'}",
                    status="suspended", suspension_reason=reason)
                row = self._usage_row(owner, f"in_{reason or 'manual'}",
                                      payment_failed_at=timezone.now())
                self._pay(_usage_obj(row.stripe_invoice_id))
                row.refresh_from_db()
                self.assertIsNone(row.payment_failed_at)   # the invoice is settled
                self.assertEqual(self._standing(owner), ("suspended", reason))  # the owner is not
                self.assertFalse(self._reactivated(owner).exists())

    #: The billing receiver's throwaway signing secret for the wire tests below.
    WIRE_SECRET = "whsec_c2_receiver_test_only"

    def _deliver_signed(self, event_id, event_type, invoice_id):
        """One signed delivery through the billing receiver (C1b's shared
        core), verified by Stripe's own verifier — nothing mocked."""
        import hashlib
        import hmac
        import json
        import time
        from django.test import RequestFactory
        from api.v1.webhooks import stripe_webhook

        payload = json.dumps({
            "id": event_id, "object": "event", "type": event_type,
            "livemode": True, "created": int(time.time()), "account": self.ACCT,
            "data": {"object": {
                "id": invoice_id, "object": "invoice", "customer": "cus_owner",
                "subscription": None, "parent": None, "amount_paid": 0,
                "currency": "usd", "hosted_invoice_url": "", "invoice_pdf": "",
                "status_transitions": {"paid_at": None}}}}).encode()
        ts = int(time.time())
        digest = hmac.new(self.WIRE_SECRET.encode(), f"{ts}.".encode() + payload,
                          hashlib.sha256).hexdigest()
        request = RequestFactory().post(
            "/api/v1/webhooks/stripe", data=payload, content_type="application/json",
            HTTP_STRIPE_SIGNATURE=f"t={ts},v1={digest}")
        with self.settings(STRIPE_WEBHOOK_SECRET=self.WIRE_SECRET, STRIPE_TEST_WEBHOOK_SECRET=""):
            return stripe_webhook(request)

    def test_through_the_real_receiver_core(self):
        """F-6 over real events: signed deliveries through the billing
        receiver (C1b's shared core), verified by Stripe's own verifier."""
        from apps.billing.stripe.models import StripeWebhookEvent

        row = self._usage_row(self.owner, "in_c2_wire")
        self.assertEqual(self._deliver_signed(
            "evt_c2_pf", "invoice.payment_failed", "in_c2_wire").status_code, 200)
        row.refresh_from_db()
        self.assertIsNotNone(row.payment_failed_at)
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self.assertEqual(self._deliver_signed(
            "evt_c2_paid", "invoice.paid", "in_c2_wire").status_code, 200)
        row.refresh_from_db()
        self.assertEqual((row.payment_status, row.payment_failed_at), ("paid", None))
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)
        self.assertEqual(
            sorted(StripeWebhookEvent.objects.values_list("stripe_event_id", "status")),
            [("evt_c2_paid", "succeeded"), ("evt_c2_pf", "succeeded")])

    # -- a voided failed invoice (PLAN §7 item 26) ----------------------------
    #
    # RULED 2026-11-03: a failed local invoice that becomes `void` is a
    # RESOLVED AR condition for a `payment_failed` suspension — not
    # economically paid, but no longer an outstanding failure that can keep
    # the billing owner suspended. The void settles that invoice's stamp and
    # the same billing-owned decision as on paid runs, under the owner's lock.

    def _void(self, obj):
        handle_invoice_voided(_event(self.ACCT, obj=obj))

    def test_a_voided_failed_usage_invoice_settles_and_reactivates_exactly_once(self):
        row = self._usage_row(self.owner, "in_c2_void")
        self._fail(_usage_obj("in_c2_void"))
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self._void(_usage_obj("in_c2_void"))
        row.refresh_from_db()
        self.assertEqual((row.payment_status, row.payment_failed_at), ("void", None))
        self.assertIsNone(row.paid_at)                      # void is not a payment
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)
        payload = self._reactivated(self.owner).get().payload
        self.assertEqual(payload["reason_code"], reasons.PAYMENT_FAILED)
        self.assertIsNone(payload["balance_micros"])
        # A replayed/duplicate void moves nothing twice.
        self._void(_usage_obj("in_c2_void"))
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)

    def test_a_voided_failed_subscription_invoice_settles_and_reactivates(self):
        row = self._subscription_row(self.owner, "in_c2_void_sub", "sub_c2_void")
        self._fail(_sub_obj("in_c2_void_sub", "sub_c2_void"))
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self._void(_sub_obj("in_c2_void_sub", "sub_c2_void"))
        row.refresh_from_db()
        self.assertEqual((row.status, row.payment_failed_at), ("void", None))
        self.assertIsNone(row.paid_at)
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)
        self._void(_sub_obj("in_c2_void_sub", "sub_c2_void"))   # replay
        self.assertEqual(self._reactivated(self.owner).count(), 1)

    def test_voiding_one_invoice_never_clears_while_another_failure_remains(self):
        voided = self._usage_row(self.owner, "in_c2_void_a")
        self._subscription_row(self.owner, "in_c2_still_sub", "sub_c2_still")
        self._fail(_usage_obj("in_c2_void_a"))
        self._fail(_sub_obj("in_c2_still_sub", "sub_c2_still"))
        self._void(_usage_obj("in_c2_void_a"))
        voided.refresh_from_db()
        self.assertIsNone(voided.payment_failed_at)          # its own failure settled
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self.assertFalse(self._reactivated(self.owner).exists())
        self._void(_sub_obj("in_c2_still_sub", "sub_c2_still"))
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)

    def test_voiding_never_clears_an_unrelated_suspension(self):
        for reason in (reasons.HARD_FLOOR, reasons.CUSTOMER_SPEND_POOL,
                       reasons.DISPUTE_LOST, "", "fraud_review"):
            with self.subTest(reason=reason):
                owner = Customer.objects.create(
                    tenant=self.tenant, external_id=f"void-{reason or 'manual'}",
                    status="suspended", suspension_reason=reason)
                row = self._usage_row(owner, f"in_void_{reason or 'manual'}",
                                      payment_failed_at=timezone.now())
                self._void(_usage_obj(row.stripe_invoice_id))
                row.refresh_from_db()
                self.assertIsNone(row.payment_failed_at)     # the invoice is settled
                self.assertEqual(self._standing(owner), ("suspended", reason))
                self.assertFalse(self._reactivated(owner).exists())

    def test_an_unmatched_voided_invoice_affects_nobody(self):
        Customer.objects.filter(id=self.owner.id).update(
            status="suspended", suspension_reason=reasons.PAYMENT_FAILED)
        row = self._usage_row(self.owner, "in_c2_ours", payment_failed_at=timezone.now())
        self._void(_usage_obj("in_nobody_holds_this"))
        self._void(_sub_obj("in_nobody_holds_this_sub", "sub_nobody_holds"))
        row.refresh_from_db()
        self.assertIsNotNone(row.payment_failed_at)
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self.assertFalse(OutboxEvent.objects.filter(
            event_type=CustomerReactivated.EVENT_TYPE).exists())

    def test_a_late_failure_after_void_suspends_nobody(self):
        row = self._usage_row(self.owner, "in_c2_void_late", payment_status="void")
        late = _usage_obj("in_c2_void_late")
        late.customer = "cus_owner"   # the owner's own Stripe customer
        self._fail(late)
        row.refresh_from_db()
        self.assertIsNotNone(row.payment_failed_at)          # the historical stamp, kept
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertFalse(self._suspended_events(self.owner).exists())
        sub_row = self._subscription_row(self.owner, "in_c2_void_late_sub", "sub_c2_void_late")
        SubscriptionInvoice.objects.filter(id=sub_row.id).update(status="void")
        late_sub = _sub_obj("in_c2_void_late_sub", "sub_c2_void_late")
        late_sub.customer = "cus_owner"
        self._fail(late_sub)
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertFalse(self._suspended_events(self.owner).exists())

    def test_a_void_through_the_real_receiver_core(self):
        """`invoice.voided` is the billing receiver's own type: a signed
        delivery settles the failure and reactivates, end to end."""
        row = self._usage_row(self.owner, "in_c2_wire_void")
        self._deliver_signed("evt_c2_void_pf", "invoice.payment_failed", "in_c2_wire_void")
        self.assertEqual(self._standing(self.owner), ("suspended", reasons.PAYMENT_FAILED))
        self.assertEqual(self._deliver_signed(
            "evt_c2_void", "invoice.voided", "in_c2_wire_void").status_code, 200)
        row.refresh_from_db()
        self.assertEqual((row.payment_status, row.payment_failed_at), ("void", None))
        self.assertEqual(self._standing(self.owner), ("active", ""))
        self.assertEqual(self._reactivated(self.owner).count(), 1)
        self._deliver_signed("evt_c2_void", "invoice.voided", "in_c2_wire_void")  # redelivery
        self.assertEqual(self._reactivated(self.owner).count(), 1)
