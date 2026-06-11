"""F1.1 per-owner residual ledger — order-free carry, exactly-once reservation.

The old carry was a lock-free 'latest prior pushed row' chain read in Phase 2:
out-of-order retries double-counted the same prior residual and stranded the
late period's own residual forever (Race A); two workers pushing adjacent
periods both read the same prior (Race B). The ledger is a commutative
per-owner accumulator: Phase 1 RESERVES (take-and-zero, pinned on the row,
exactly once), Phase 3 DEPOSITS — so the conservation invariant
    cents_billed * 10_000 + ledger_balance == usage_in + carry_in
holds under any push order or interleaving.

Thread tests use TransactionTestCase (real Postgres row locking, committed
setup data) with threading.Barrier(2) and per-thread connection.close(), the
same harness pattern as apps/billing/tests/test_concurrency_races.py.
"""
import contextlib
import datetime
import importlib
import threading
from unittest.mock import patch, MagicMock

import pytest
from django.db import connection
from django.test import TransactionTestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.invoicing.models import CustomerUsageInvoice, PostpaidResidualLedger
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

SVC = "apps.billing.invoicing.services.postpaid_service.stripe"

P_JUN, P_JUL = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
P_AUG, P_SEP = datetime.date(2026, 8, 1), datetime.date(2026, 9, 1)
P_OCT = datetime.date(2026, 10, 1)


def _charge_ready_tenant(name="T"):
    return Tenant.objects.create(
        name=name, products=["metering", "billing"], billing_mode="postpaid",
        stripe_connected_account_id="acct_x", charges_enabled=True)


def _postpaid_customer(t, external_id="c1", stripe_customer_id="cus_1"):
    return Customer.objects.create(
        tenant=t, external_id=external_id, stripe_customer_id=stripe_customer_id)


def _stripe_invoice(id="in_1", status="draft", rec=None):
    inv = MagicMock()
    inv.id = id
    inv.status = status
    inv.deleted = False
    inv.metadata = {"usage_invoice_id": str(rec.id)} if rec is not None else {}
    return inv


def _stripe_item(id="ii_old", line_index="0"):
    item = MagicMock()
    item.id = id
    item.metadata = {"line_index": line_index}
    return item


@contextlib.contextmanager
def _stripe(retrieve=None, items=(), finalize_error=None):
    """Thread-safe mocks for the SDK surface _push_to_stripe touches.

    All counters (and the recorded InvoiceItem cent amounts) live behind ONE
    lock in a closure, so multi-thread tests can assert exact totals. Each
    list call builds a fresh pager. Yields the state dict:
    {"invoices", "items", "finalizes", "amounts"}.
    """
    lock = threading.Lock()
    state = {"invoices": 0, "items": 0, "finalizes": 0, "amounts": []}

    def invoice_create(*a, **k):
        with lock:
            state["invoices"] += 1
            return MagicMock(id=f"in_{state['invoices']}")

    def item_create(*a, **k):
        with lock:
            state["items"] += 1
            state["amounts"].append(k["amount"])
            return MagicMock(id=f"ii_{state['items']}")

    def finalize(*a, **k):
        with lock:
            state["finalizes"] += 1
        if finalize_error is not None:
            raise finalize_error
        return MagicMock(id=k.get("invoice"))

    def paged(objs):
        page = MagicMock()
        page.auto_paging_iter.side_effect = lambda: iter(list(objs))
        return page

    with patch(f"{SVC}.Invoice.create", side_effect=invoice_create), \
         patch(f"{SVC}.Invoice.retrieve", return_value=retrieve), \
         patch(f"{SVC}.Invoice.list", side_effect=lambda *a, **k: paged([])), \
         patch(f"{SVC}.InvoiceItem.list", side_effect=lambda *a, **k: paged(items)), \
         patch(f"{SVC}.InvoiceItem.create", side_effect=item_create), \
         patch(f"{SVC}.Invoice.finalize_invoice", side_effect=finalize), \
         patch("apps.platform.events.tasks.process_single_event"):
        yield state


def _agg(total, lines=None):
    return patch.object(PostpaidUsageService, "aggregate_lines",
                        return_value=(total, lines if lines is not None else [("", total)]))


def _run_workers(targets):
    """Barrier-start one thread per target callable; collect exceptions."""
    barrier = threading.Barrier(len(targets))
    errors = []

    def wrap(fn):
        def worker():
            try:
                barrier.wait()
                fn()
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()
        return worker

    threads = [threading.Thread(target=wrap(fn)) for fn in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


class ConcurrentSamePeriodPush(TransactionTestCase):
    """Two workers push the SAME (owner, period): the F0.1 'pushing' claim makes
    the loser early-return — one row, one Stripe invoice, one set of line items,
    and a consistent ledger (one reservation, one deposit)."""

    def test_two_workers_same_period_one_invoice_one_ledger_cycle(self):
        tenant = _charge_ready_tenant(name="RACE_PP_SAME")
        customer = _postpaid_customer(tenant, external_id="race_pp1")

        with _stripe() as state, _agg(1_234_567):
            errors = _run_workers([
                lambda: PostpaidUsageService.push_customer_period(tenant, customer, P_JUN, P_JUL),
                lambda: PostpaidUsageService.push_customer_period(tenant, customer, P_JUN, P_JUL),
            ])
        self.assertEqual(errors, [], f"workers raised unexpected exceptions: {errors}")

        rows = CustomerUsageInvoice.objects.filter(tenant=tenant, customer=customer)
        self.assertEqual(rows.count(), 1)
        rec = rows.first()
        self.assertEqual(rec.status, "pushed")
        # Exactly ONE Stripe invoice + ONE set of line items across both workers.
        self.assertEqual(state["invoices"], 1)
        self.assertEqual(state["amounts"], [123])  # floor(1_234_567 / 10_000)
        self.assertEqual(rec.line_items.count(), 1)
        # One reservation (empty ledger -> pin 0), one deposit of the residual.
        self.assertEqual(rec.carry_in_micros, 0)
        self.assertEqual(rec.residual_micros, 4_567)
        ledger = PostpaidResidualLedger.objects.get(customer=customer)
        self.assertEqual(ledger.balance_micros, 4_567)


class ConcurrentAdjacentPeriodCarry(TransactionTestCase):
    """Race B: two workers push ADJACENT periods of the same owner. The old
    chain read let both consume the same prior residual (9_000 twice -> 2 cents
    billed from 13_000 of value). The ledger's take-and-zero reservation makes
    the carry conservation exact under any interleaving."""

    def test_adjacent_periods_conserve_residual_exactly(self):
        tenant = _charge_ready_tenant(name="RACE_PP_ADJ")
        customer = _postpaid_customer(tenant, external_id="race_pp2")
        PostpaidResidualLedger.objects.create(
            tenant=tenant, customer=customer, balance_micros=9_000)

        with _stripe() as state, _agg(2_000):
            errors = _run_workers([
                lambda: PostpaidUsageService.push_customer_period(tenant, customer, P_JUN, P_JUL),
                lambda: PostpaidUsageService.push_customer_period(tenant, customer, P_JUL, P_AUG),
            ])
        self.assertEqual(errors, [], f"workers raised unexpected exceptions: {errors}")

        recs = list(CustomerUsageInvoice.objects.filter(tenant=tenant, customer=customer))
        self.assertEqual(len(recs), 2)
        for rec in recs:
            self.assertEqual(rec.status, "pushed")
        ledger = PostpaidResidualLedger.objects.get(customer=customer)

        # Conservation: cents*10_000 + final ledger == 9_000 seed + 2 * 2_000 usage.
        billed_micros = sum(state["amounts"]) * 10_000
        self.assertEqual(billed_micros + ledger.balance_micros, 13_000)
        # The double-count would bill 2 cents; correct is exactly 1 cent + 3_000 left.
        self.assertEqual(sum(state["amounts"]), 1)
        self.assertEqual(ledger.balance_micros, 3_000)
        self.assertEqual(state["invoices"], 1)  # the 0-cent push mints no invoice
        # Exactly one worker won the 9_000 reservation; the other got the
        # zeroed ledger (0) or the winner's deposit (1_000) — never 9_000 again.
        carries = sorted(rec.carry_in_micros for rec in recs)
        self.assertEqual(carries[1], 9_000)
        self.assertIn(carries[0], (0, 1_000))


@pytest.mark.django_db
class TestOutOfOrderCarry:
    """Race A (sequential): P2 pushes BEFORE P1. The chain read would feed
    P0's residual to both P1 and P2 and strand P1's own residual; the ledger
    conserves every micro across all four periods."""

    def test_out_of_order_pushes_conserve_and_never_strand(self):
        t = _charge_ready_tenant()
        c = _postpaid_customer(t)

        def push(ps, pe, total):
            with _stripe() as state, _agg(total):
                PostpaidUsageService.push_customer_period(t, c, ps, pe)
            return state

        ledger = lambda: PostpaidResidualLedger.objects.get(customer=c)  # noqa: E731

        # P0 pushes normally and leaves residual 4_567 in the ledger.
        s0 = push(P_JUN, P_JUL, 1_234_567)
        assert s0["amounts"] == [123]
        assert ledger().balance_micros == 4_567

        # P2 pushes BEFORE P1: reserves 4_567 -> 12_567 -> 1 cent, 2_567 left.
        s2 = push(P_AUG, P_SEP, 8_000)
        assert s2["amounts"] == [1]
        assert ledger().balance_micros == 2_567

        # P1 arrives late: reserves 2_567 -> 9_567 -> 0 cents, all banked.
        s1 = push(P_JUL, P_AUG, 7_000)
        assert s1["amounts"] == []
        rec1 = CustomerUsageInvoice.objects.get(customer=c, period_start=P_JUL)
        assert rec1.status == "pushed" and rec1.residual_micros == 9_567
        assert ledger().balance_micros == 9_567

        # P3 consumes P1's banked residual: 9_567 + 6_000 -> 1 cent, 5_567 left.
        s3 = push(P_SEP, P_OCT, 6_000)
        assert s3["amounts"] == [1]
        rec3 = CustomerUsageInvoice.objects.get(customer=c, period_start=P_SEP)
        assert rec3.carry_in_micros == 9_567  # P1's residual NOT stranded
        assert ledger().balance_micros == 5_567

        # Conservation across all four periods, to the micro.
        usage_in = 1_234_567 + 8_000 + 7_000 + 6_000
        cents = sum(s0["amounts"] + s1["amounts"] + s2["amounts"] + s3["amounts"])
        assert cents * 10_000 + ledger().balance_micros == usage_in


@pytest.mark.django_db
class TestCarrySurvivesRetryAcrossFetch:
    """The pin must survive a DB round-trip: a Phase-2 failure leaves the row
    'failed', and a NEW worker (fresh fetch) retries it. If carry_in_micros
    were missing from the claim save's update_fields, the in-process object
    would still pass the in-order tests — only this re-fetch + ledger-sentinel
    test catches the silently-dropped field (the ledger is already zeroed, so
    a re-reservation would destroy the residual)."""

    def test_pin_survives_db_roundtrip_and_ledger_is_not_reread(self):
        t = _charge_ready_tenant()
        c = _postpaid_customer(t)
        PostpaidResidualLedger.objects.create(tenant=t, customer=c, balance_micros=4_567)

        # Attempt 1: reservation pins 4_567, items pin, finalize blows up -> sticky failed.
        with _stripe(finalize_error=RuntimeError("boom")) as s1, _agg(8_000):
            with pytest.raises(RuntimeError):
                PostpaidUsageService.push_customer_period(t, c, P_JUN, P_JUL)
        assert s1["amounts"] == [1]  # 8_000 + 4_567 = 12_567 -> 1 cent
        rec = CustomerUsageInvoice.objects.get(tenant=t, customer=c, period_start=P_JUN)
        assert rec.status == "failed"
        assert rec.carry_in_micros == 4_567  # the pin made it to the DB
        ledger = PostpaidResidualLedger.objects.get(customer=c)
        assert ledger.balance_micros == 0  # taken-and-zeroed exactly once

        # Sentinel: if the retry (wrongly) re-reserved, it would take 7_777
        # and zero the ledger — both asserts below would see it.
        ledger.balance_micros = 7_777
        ledger.save(update_fields=["balance_micros"])

        # Retry as a NEW worker: freshly-loaded customer, retrieve-first resume.
        fresh_customer = Customer.objects.get(id=c.id)
        with _stripe(retrieve=_stripe_invoice(id="in_1", status="draft", rec=rec),
                     items=[_stripe_item(id="ii_old", line_index="0")]) as s2, _agg(8_000):
            PostpaidUsageService.push_customer_period(t, fresh_customer, P_JUN, P_JUL)
        rec.refresh_from_db()
        assert rec.status == "pushed"
        assert rec.carry_in_micros == 4_567   # pinned value survived, replayed
        assert rec.residual_micros == 2_567   # 12_567 - 1 cent
        assert s2["invoices"] == 0 and s2["items"] == 0  # resumed, not recreated
        ledger.refresh_from_db()
        # Sentinel untouched by any re-read; only the Phase-3 deposit landed.
        assert ledger.balance_micros == 7_777 + 2_567


@pytest.mark.django_db
class TestSkipPathsReserveNoCarry:
    """The reservation sits AFTER every skip check: a row that never pushes
    must never take (and strand) the ledger balance."""

    def test_zero_usage_with_banked_carry_skips_and_keeps_ledger(self):
        # Sub-cent residue alone must not mint an invoice: the carry stays
        # banked for a future month with real usage.
        t = _charge_ready_tenant()
        c = _postpaid_customer(t)
        PostpaidResidualLedger.objects.create(tenant=t, customer=c, balance_micros=9_000)
        with _stripe() as state, _agg(0, lines=[]):
            rec = PostpaidUsageService.push_customer_period(t, c, P_JUN, P_JUL)
        rec.refresh_from_db()
        assert rec.status == "skipped" and rec.skip_reason == "no_usage"
        assert rec.carry_in_micros is None  # no reservation
        assert PostpaidResidualLedger.objects.get(customer=c).balance_micros == 9_000
        assert state["invoices"] == 0

    def test_no_stripe_customer_skip_reserves_nothing(self):
        t = _charge_ready_tenant()
        c = _postpaid_customer(t, stripe_customer_id="")
        with _stripe(), _agg(500_000):
            rec = PostpaidUsageService.push_customer_period(t, c, P_JUN, P_JUL)
        rec.refresh_from_db()
        assert rec.status == "skipped" and rec.skip_reason == "no_stripe_customer"
        assert rec.carry_in_micros is None
        assert not PostpaidResidualLedger.objects.filter(customer=c).exists()

    def test_not_charge_ready_skip_reserves_nothing(self):
        t = Tenant.objects.create(
            name="T_NCR", products=["metering", "billing"], billing_mode="postpaid")
        c = _postpaid_customer(t)
        with _stripe(), _agg(500_000):
            rec = PostpaidUsageService.push_customer_period(t, c, P_JUN, P_JUL)
        rec.refresh_from_db()
        assert rec.status == "skipped" and rec.skip_reason == "not_charge_ready"
        assert rec.carry_in_micros is None
        assert not PostpaidResidualLedger.objects.filter(customer=c).exists()

    def test_seat_superseded_row_reserves_nothing(self):
        t = _charge_ready_tenant()
        biz = Customer.objects.create(
            tenant=t, external_id="biz", account_type="business",
            billing_topology="pooled", stripe_customer_id="cus_biz")
        seat = Customer.objects.create(
            tenant=t, external_id="seat1", account_type="seat", parent=biz,
            stripe_customer_id="")
        stray = CustomerUsageInvoice.objects.create(
            tenant=t, customer=seat, period_start=P_JUN, period_end=P_JUL,
            status="pending")
        with _stripe(), _agg(500_000):
            rec = PostpaidUsageService.push_customer_period(t, seat, P_JUN, P_JUL)
        stray.refresh_from_db()
        assert stray.status == "skipped" and stray.skip_reason == "seat_superseded"
        assert stray.carry_in_micros is None  # superseded rows never reserve
        assert not PostpaidResidualLedger.objects.filter(customer=seat).exists()
        # The OWNER row pushed normally with its own (owner-keyed) ledger cycle.
        rec.refresh_from_db()
        assert rec.customer_id == biz.id and rec.status == "pushed"
        assert rec.carry_in_micros == 0
        assert PostpaidResidualLedger.objects.filter(customer=biz).exists()


@pytest.mark.django_db
class TestMigrationBackfill:
    """0006 seeds each customer's ledger with the residual of their LATEST
    pushed row — exactly what the old chain read would have returned next."""

    def _seed(self):
        from django.apps import apps as django_apps
        mig = importlib.import_module(
            "apps.billing.invoicing.migrations.0006_residual_ledger")
        mig.seed_residual_ledgers(django_apps, None)

    def test_pushed_rows_seed_latest_residual_others_get_no_ledger(self):
        t = _charge_ready_tenant()
        pushed = _postpaid_customer(t, external_id="c_pushed")
        unpushed = _postpaid_customer(t, external_id="c_unpushed", stripe_customer_id="cus_2")
        CustomerUsageInvoice.objects.create(
            tenant=t, customer=pushed, period_start=P_JUN, period_end=P_JUL,
            status="pushed", residual_micros=1_111)
        CustomerUsageInvoice.objects.create(
            tenant=t, customer=pushed, period_start=P_JUL, period_end=P_AUG,
            status="pushed", residual_micros=2_222)  # the LATEST pushed row
        CustomerUsageInvoice.objects.create(
            tenant=t, customer=unpushed, period_start=P_JUN, period_end=P_JUL,
            status="pending")
        CustomerUsageInvoice.objects.create(
            tenant=t, customer=unpushed, period_start=P_JUL, period_end=P_AUG,
            status="skipped", skip_reason="no_usage")

        self._seed()
        ledger = PostpaidResidualLedger.objects.get(customer=pushed)
        assert ledger.balance_micros == 2_222  # latest, not first/sum
        assert ledger.tenant_id == t.id
        assert not PostpaidResidualLedger.objects.filter(customer=unpushed).exists()

        # Idempotent re-run: an existing ledger is never clobbered or duplicated.
        PostpaidResidualLedger.objects.filter(customer=pushed).update(balance_micros=5_555)
        self._seed()
        assert PostpaidResidualLedger.objects.filter(customer=pushed).count() == 1
        assert PostpaidResidualLedger.objects.get(customer=pushed).balance_micros == 5_555
