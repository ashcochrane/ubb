"""F0.1 bounded + resumable postpaid push.

I1: at most one finalized Stripe invoice per (billing owner, period).
I2: resume-not-recreate — the pointer persists the moment the invoice exists;
    every retry is retrieve-first.
I3: retries bounded by push_attempts AND wall-clock, then terminal
    failed_permanent + outbox alert.
I4: belt-and-braces pre-create Invoice.list metadata match.
I5: owner-first keying (pooled seat -> business).
"""
import contextlib
import datetime
import importlib
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.billing.invoicing.models import CustomerUsageInvoice
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
SVC = "apps.billing.invoicing.services.postpaid_service.stripe"
FAILED_EVENT = "usage.invoice_push_failed_permanent"


def _charge_ready_tenant():
    return Tenant.objects.create(
        name="T", products=["metering", "billing"], billing_mode="postpaid",
        stripe_connected_account_id="acct_x", charges_enabled=True)


def _customer(t, external_id="c1", stripe_customer_id="cus_1"):
    return Customer.objects.create(
        tenant=t, external_id=external_id, stripe_customer_id=stripe_customer_id)


def _pooled_business(t):
    biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                  billing_topology="pooled", stripe_customer_id="cus_biz")
    seat = Customer.objects.create(tenant=t, external_id="seat1", account_type="seat",
                                   parent=biz, stripe_customer_id="")
    return biz, seat


def _row(t, c, **kwargs):
    defaults = dict(period_start=PS, period_end=PE, total_billed_micros=1_000_000)
    defaults.update(kwargs)
    return CustomerUsageInvoice.objects.create(tenant=t, customer=c, **defaults)


def _stripe_invoice(id="in_1", status="draft", rec=None, deleted=False):
    inv = MagicMock()
    inv.id = id
    inv.status = status
    inv.deleted = deleted
    inv.metadata = {"usage_invoice_id": str(rec.id)} if rec is not None else {}
    return inv


def _stripe_item(id="ii_old", line_index="0"):
    item = MagicMock()
    item.id = id
    item.metadata = {"line_index": line_index}
    return item


def _paged(objs):
    page = MagicMock()
    page.auto_paging_iter.side_effect = lambda: iter(list(objs))
    return page


@contextlib.contextmanager
def _stripe(retrieve=None, listed=(), items=(), created_id="in_new", item_create=None):
    """Patch the full SDK surface _push_to_stripe touches; yields the mocks."""
    counter = {"n": 0}

    def default_item_create(*a, **k):
        counter["n"] += 1
        return MagicMock(id=f"ii_new_{counter['n']}")

    with patch(f"{SVC}.Invoice.retrieve", return_value=retrieve) as m_retrieve, \
         patch(f"{SVC}.Invoice.list", return_value=_paged(listed)) as m_list, \
         patch(f"{SVC}.Invoice.create", return_value=MagicMock(id=created_id)) as m_create, \
         patch(f"{SVC}.InvoiceItem.list", return_value=_paged(items)) as m_item_list, \
         patch(f"{SVC}.InvoiceItem.create",
               side_effect=item_create or default_item_create) as m_item_create, \
         patch(f"{SVC}.Invoice.finalize_invoice",
               return_value=MagicMock(id=created_id)) as m_finalize, \
         patch("apps.platform.events.tasks.process_single_event"):
        yield SimpleNamespace(retrieve=m_retrieve, list=m_list, create=m_create,
                              item_list=m_item_list, item_create=m_item_create,
                              finalize=m_finalize)


def _agg(total=500_000, lines=None):
    return patch.object(PostpaidUsageService, "aggregate_lines",
                        return_value=(total, lines if lines is not None else [("", total)]))


@pytest.mark.django_db
class TestCrashPairMatrix:
    """A crash between any two push steps must RESUME, never recreate (I1/I2/I4)."""

    def test_claim_to_create_crash_creates_with_metadata(self):
        t, c = _charge_ready_tenant(), None
        c = _customer(t)
        with _stripe() as m, _agg():
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_new"
        assert rec.push_phase == "finalized"
        assert rec.push_attempts == 1 and rec.first_attempted_at is not None
        # I4 lookup ran before the create; the create carries the recovery metadata.
        assert m.list.call_count == 1
        assert m.create.call_count == 1
        assert m.create.call_args.kwargs["metadata"]["usage_invoice_id"] == str(rec.id)
        item_meta = m.item_create.call_args.kwargs["metadata"]
        assert item_meta == {"usage_invoice_id": str(rec.id), "line_index": "0"}

    def test_create_to_persist_crash_resumes_via_metadata_match(self):
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="pending")  # crash left no pointer...
        draft = _stripe_invoice(id="in_1", status="draft", rec=rec)  # ...but Stripe has it
        with _stripe(listed=[draft]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert m.create.call_count == 0  # the metadata list-match resumed it
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_1"
        assert m.finalize.call_count == 1

    def test_persist_to_items_crash_resumes_via_retrieve(self):
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="pending", stripe_invoice_id="in_1",
                   push_phase="invoice_created")
        with _stripe(retrieve=_stripe_invoice(id="in_1", status="draft", rec=rec)) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert m.retrieve.call_count == 1 and m.list.call_count == 0
        assert m.create.call_count == 0
        assert m.item_create.call_count == 1 and m.finalize.call_count == 1
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_1"

    def test_items_to_finalize_crash_skips_existing_items(self):
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="pending", stripe_invoice_id="in_1",
                   push_phase="items_pinned")
        with _stripe(retrieve=_stripe_invoice(id="in_1", status="draft", rec=rec),
                     items=[_stripe_item(id="ii_old", line_index="0")]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert m.create.call_count == 0
        assert m.item_create.call_count == 0  # the pinned item was recovered, not recreated
        assert m.finalize.call_count == 1
        assert rec.status == "pushed"
        assert list(rec.line_items.values_list("stripe_invoice_item_id", flat=True)) == ["ii_old"]

    def test_finalize_to_record_crash_adopts_open_invoice(self):
        """THE core case: the invoice finalized but the DB never heard — the retry
        must do ZERO Stripe writes and just record."""
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="pending", stripe_invoice_id="in_1", push_phase="finalized")
        with _stripe(retrieve=_stripe_invoice(id="in_1", status="open", rec=rec),
                     items=[_stripe_item(id="ii_old", line_index="0")]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert m.create.call_count == 0
        assert m.item_create.call_count == 0
        assert m.finalize.call_count == 0
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_1"
        assert list(rec.line_items.values_list("stripe_invoice_item_id", flat=True)) == ["ii_old"]
        assert OutboxEvent.objects.filter(event_type="usage.invoice_pushed").count() == 1


@pytest.mark.django_db
class TestRetryAfterKeyExpiry:
    def test_repush_after_key_expiry_resumes_not_recreates(self):
        """I1 across key expiry: a failed_permanent row reactivated by the repush
        command resumes from its persisted pointer — never a second create."""
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="failed_permanent", stripe_invoice_id="in_1",
                   push_phase="invoice_created", push_attempts=8,
                   first_attempted_at=timezone.now() - datetime.timedelta(days=3))
        call_command("repush_usage_invoice", str(rec.id))
        rec.refresh_from_db()
        assert rec.status == "pending" and rec.push_attempts == 0
        assert rec.first_attempted_at is None and rec.last_attempt_error == ""
        assert rec.stripe_invoice_id == "in_1"  # the pointer survives the reset
        with _stripe(retrieve=_stripe_invoice(id="in_1", status="draft", rec=rec)) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert m.create.call_count == 0
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_1"


@pytest.mark.django_db
class TestRetryBounds:
    def test_attempts_cap_flips_terminal_with_exactly_one_alert(self):
        t = _charge_ready_tenant()
        c = _customer(t)
        cap = settings.UBB_POSTPAID_PUSH_MAX_ATTEMPTS
        rec = _row(t, c, status="pending", push_attempts=cap,
                   first_attempted_at=timezone.now(), last_attempt_error="boom")
        with _stripe() as m:
            PostpaidUsageService.push_customer_period(t, c, PS, PE)  # pass 1: caps
            PostpaidUsageService.push_customer_period(t, c, PS, PE)  # pass 2: idempotent
        rec.refresh_from_db()
        assert rec.status == "failed_permanent"
        for mock in (m.retrieve, m.list, m.create, m.item_create, m.finalize):
            mock.assert_not_called()
        events = OutboxEvent.objects.filter(event_type=FAILED_EVENT)
        assert events.count() == 1  # no re-alert on the second pass
        assert events.first().payload["push_attempts"] == cap
        assert events.first().payload["last_error"] == "boom"

    def test_wall_clock_cap_flips_terminal_before_any_stripe_call(self):
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="pending", push_attempts=1,
                   first_attempted_at=timezone.now() - datetime.timedelta(
                       hours=settings.UBB_POSTPAID_PUSH_MAX_AGE_HOURS + 1))
        with _stripe() as m:
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "failed_permanent"
        for mock in (m.retrieve, m.list, m.create, m.item_create, m.finalize):
            mock.assert_not_called()
        assert OutboxEvent.objects.filter(event_type=FAILED_EVENT).count() == 1

    def test_transient_failure_sticks_failed_not_pending(self):
        t = _charge_ready_tenant()
        c = _customer(t)
        with _stripe(item_create=RuntimeError("boom")) as m, _agg():
            with pytest.raises(RuntimeError):
                PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec = CustomerUsageInvoice.objects.get(tenant=t, customer=c, period_start=PS)
        assert rec.status == "failed"  # sticky: never silently back to 'pending'
        assert "boom" in rec.last_attempt_error
        assert rec.push_attempts == 1
        # Persist-at-create: the pointer survived the mid-push crash (I2).
        assert rec.stripe_invoice_id == "in_new"
        assert rec.push_phase == "invoice_created"
        assert m.create.call_count == 1

    def test_fatal_void_invoice_parks_failed_permanent_after_one_attempt(self):
        """A void/deleted invoice raises StripeFatalError — non-retryable by
        definition, so the row parks failed_permanent on the FIRST attempt with
        exactly one alert, not after ~8 hourly sticky-failed retries."""
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="pending", stripe_invoice_id="in_void",
                   push_phase="invoice_created")
        with _stripe(retrieve=_stripe_invoice(id="in_void", status="void", rec=rec)) as m, _agg():
            out = PostpaidUsageService.push_customer_period(t, c, PS, PE)  # parks, no raise
            PostpaidUsageService.push_customer_period(t, c, PS, PE)  # pass 2: idempotent
        rec.refresh_from_db()
        assert out.status == "failed_permanent"
        assert rec.status == "failed_permanent"
        assert rec.push_attempts == 1  # ONE attempt, not the full cap
        assert "void" in rec.last_attempt_error
        assert m.retrieve.call_count == 1  # pass 2 returned before any Stripe call
        for mock in (m.create, m.item_create, m.finalize):
            mock.assert_not_called()
        events = OutboxEvent.objects.filter(event_type=FAILED_EVENT)
        assert events.count() == 1  # exactly one alert, none on the idempotent pass
        assert events.first().payload["stripe_invoice_id"] == "in_void"
        assert events.first().payload["push_attempts"] == 1


@pytest.mark.django_db
class TestFrozenLineSnapshot:
    """Important-3: line_index identity is positional over the aggregation sort,
    so the lines are FROZEN at first claim — a mid-retry group_by flip must not
    re-aggregate and diff the wrong indices on resume."""

    def _events(self, t, c):
        from apps.metering.usage.models import UsageEvent
        for i, (pid, micros) in enumerate([("prod_a", 600_000), ("prod_b", 400_000)]):
            ev = UsageEvent.objects.create(
                tenant=t, customer=c, request_id=f"r{i}", idempotency_key=f"i{i}",
                provider_cost_micros=1, billed_cost_micros=micros, product_id=pid)
            UsageEvent.objects.filter(id=ev.id).update(
                effective_at=timezone.make_aware(timezone.datetime(2026, 6, 15)))

    def test_resume_after_group_by_flip_creates_zero_new_items(self):
        from apps.billing.invoicing.models import PostpaidUsageConfig
        t = _charge_ready_tenant()
        c = _customer(t)
        cfg = PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="")
        self._events(t, c)
        # Attempt 1: the single ungrouped line is pinned, then the finalize crashes.
        with _stripe() as m:
            m.finalize.side_effect = RuntimeError("boom")
            with pytest.raises(RuntimeError):
                PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec = CustomerUsageInvoice.objects.get(tenant=t, customer=c, period_start=PS)
        assert rec.status == "failed"
        assert rec.line_snapshot == [["", 1_000_000]]  # frozen at first claim
        assert m.item_create.call_count == 1
        # Tenant flips grouping mid-retry: re-aggregating would now yield TWO
        # lines and shift every line_index.
        cfg.usage_line_item_group_by = "product_id"
        cfg.save()
        # Resume: frozen lines, the pinned item recovered — ZERO new items.
        with _stripe(retrieve=_stripe_invoice(id="in_new", status="draft", rec=rec),
                     items=[_stripe_item(id="ii_pinned", line_index="0")]) as m2:
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed"
        assert m2.create.call_count == 0
        assert m2.item_create.call_count == 0  # the frozen line matched the pinned item
        assert m2.finalize.call_count == 1
        assert rec.total_billed_micros == 1_000_000
        assert list(rec.line_items.values_list("dimension", "amount_micros",
                                               "stripe_invoice_item_id")) \
            == [("", 1_000_000, "ii_pinned")]

    def test_fresh_row_honors_current_group_by(self):
        from apps.billing.invoicing.models import PostpaidUsageConfig
        t = _charge_ready_tenant()
        c = _customer(t)
        PostpaidUsageConfig.objects.create(tenant=t, usage_line_item_group_by="product_id")
        self._events(t, c)
        with _stripe() as m:
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec = CustomerUsageInvoice.objects.get(tenant=t, customer=c, period_start=PS)
        assert rec.status == "pushed"
        assert m.item_create.call_count == 2  # grouped: one item per product
        assert rec.line_snapshot == [["prod_a", 600_000], ["prod_b", 400_000]]
        assert list(rec.line_items.order_by("-amount_micros")
                    .values_list("dimension", "amount_micros")) \
            == [("prod_a", 600_000), ("prod_b", 400_000)]


@pytest.mark.django_db
class TestReconcileSelection:
    def test_terminal_rows_untouched(self):
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        t = _charge_ready_tenant()
        c = _customer(t)
        c2 = _customer(t, external_id="c2", stripe_customer_id="cus_2")
        dead = _row(t, c, status="failed_permanent", last_attempt_error="x")
        superseded = _row(t, c2, status="skipped", skip_reason="seat_superseded")
        with _stripe() as m:
            reconcile_postpaid_usage()
        dead.refresh_from_db(); superseded.refresh_from_db()
        assert dead.status == "failed_permanent"
        assert superseded.status == "skipped" and superseded.skip_reason == "seat_superseded"
        for mock in (m.retrieve, m.list, m.create, m.item_create, m.finalize):
            mock.assert_not_called()

    def test_stale_pushing_reclaim_preserves_pointer_and_resumes(self):
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="pushing", stripe_invoice_id="in_1",
                   push_phase="invoice_created", push_attempts=1,
                   first_attempted_at=timezone.now())
        CustomerUsageInvoice.objects.filter(id=rec.id).update(
            updated_at=timezone.now() - datetime.timedelta(minutes=45))
        with _stripe(retrieve=_stripe_invoice(id="in_1", status="draft", rec=rec)) as m, _agg():
            reconcile_postpaid_usage()
        rec.refresh_from_db()
        assert rec.status == "pushed"
        assert rec.stripe_invoice_id == "in_1"  # reclaim kept the pointer; resume used it
        assert m.create.call_count == 0
        assert m.retrieve.call_count == 1


@pytest.mark.django_db
class TestOwnerFirstKeying:
    def test_pooled_seat_push_keys_row_on_business(self):
        t = _charge_ready_tenant()
        biz, seat = _pooled_business(t)
        with _stripe() as m, _agg():
            rec = PostpaidUsageService.push_customer_period(t, seat, PS, PE)
        assert rec.customer_id == biz.id
        rows = CustomerUsageInvoice.objects.filter(tenant=t, period_start=PS)
        assert rows.count() == 1 and rows.first().customer_id == biz.id
        # The seat has NO stripe_customer_id, but its pooled owner does: not skipped.
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.skip_reason == ""
        assert m.create.call_args.kwargs["customer"] == "cus_biz"

    def test_seat_keyed_row_is_superseded_by_the_service_belt(self):
        t = _charge_ready_tenant()
        biz, seat = _pooled_business(t)
        stray = _row(t, seat, status="pending")
        with _stripe() as m, _agg():
            rec = PostpaidUsageService.push_customer_period(t, seat, PS, PE)
        stray.refresh_from_db()
        assert stray.status == "skipped" and stray.skip_reason == "seat_superseded"
        assert rec.customer_id == biz.id and rec.status == "pushed"

    def test_close_task_then_direct_seat_push_one_row_per_owner_period(self):
        from apps.metering.usage.models import UsageEvent
        from apps.billing.invoicing.tasks import close_postpaid_usage_periods, _prior_month
        t = _charge_ready_tenant()
        biz, seat = _pooled_business(t)
        start, end = _prior_month()
        ev = UsageEvent.objects.create(tenant=t, customer=seat, request_id="r1",
            idempotency_key="i1", provider_cost_micros=1, billed_cost_micros=1_000_000)
        UsageEvent.objects.filter(id=ev.id).update(
            effective_at=timezone.make_aware(timezone.datetime(start.year, start.month, 15)))
        with _stripe() as m:
            close_postpaid_usage_periods()
            PostpaidUsageService.push_customer_period(t, seat, start, end)
        rows = CustomerUsageInvoice.objects.filter(tenant=t, period_start=start)
        assert rows.count() == 1
        row = rows.first()
        assert row.customer_id == biz.id and row.status == "pushed"
        assert m.create.call_count == 1  # I1: one invoice, despite two callers


@pytest.mark.django_db
class TestMigrationRules:
    def _migration(self):
        return importlib.import_module(
            "apps.billing.invoicing.migrations.0005_bounded_resumable_push")

    def _run(self):
        from django.apps import apps as django_apps
        mig = self._migration()
        mig.supersede_pooled_seat_rows(django_apps, None)  # (c) first
        mig.fail_legacy_rows(django_apps, None)            # (a) then

    def test_legacy_pending_row_becomes_failed_permanent(self):
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="pending")
        self._run()
        rec.refresh_from_db()
        assert rec.status == "failed_permanent"
        assert rec.last_attempt_error.startswith("migrated: pre-metadata era")

    def test_seat_rule_wins_over_legacy_rule_for_seat_keyed_failed_rows(self):
        t = _charge_ready_tenant()
        biz, seat = _pooled_business(t)
        seat_rec = _row(t, seat, status="failed")
        biz_rec = _row(t, biz, status="failed")
        self._run()
        seat_rec.refresh_from_db(); biz_rec.refresh_from_db()
        assert seat_rec.status == "skipped" and seat_rec.skip_reason == "seat_superseded"
        assert seat_rec.last_attempt_error == ""  # rule (a) did not also hit it
        assert biz_rec.status == "failed_permanent"


@pytest.mark.django_db
class TestSkippedRowRecovery:
    def test_charge_ready_flip_recovers_not_charge_ready_row(self):
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        t = _charge_ready_tenant()  # NOW charge-ready; the row predates that
        c = _customer(t)
        rec = _row(t, c, status="skipped", skip_reason="not_charge_ready")
        with _stripe(), _agg():
            reconcile_postpaid_usage()
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.skip_reason == ""

    def test_no_stripe_customer_recovers_when_owner_gains_one(self):
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        t = _charge_ready_tenant()
        c = _customer(t)  # has cus_1 now; the skip predates that
        rec = _row(t, c, status="skipped", skip_reason="no_stripe_customer")
        with _stripe(), _agg():
            reconcile_postpaid_usage()
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.skip_reason == ""

    def test_seat_keyed_skipped_rows_flip_to_seat_superseded_not_pending(self):
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        t = _charge_ready_tenant()
        biz, seat = _pooled_business(t)
        rec = _row(t, seat, status="skipped", skip_reason="not_charge_ready")
        with _stripe() as m:
            reconcile_postpaid_usage()
        rec.refresh_from_db()
        assert rec.status == "skipped" and rec.skip_reason == "seat_superseded"
        m.create.assert_not_called()  # never re-pushed, and no owner row minted
        assert not CustomerUsageInvoice.objects.filter(customer=biz).exists()

    def test_no_usage_skip_stays_terminal(self):
        from apps.billing.invoicing.tasks import reconcile_postpaid_usage
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="skipped", skip_reason="no_usage", total_billed_micros=0)
        with _stripe() as m:
            reconcile_postpaid_usage()
        rec.refresh_from_db()
        assert rec.status == "skipped" and rec.skip_reason == "no_usage"
        m.create.assert_not_called()


@pytest.mark.django_db
class TestRepushCommand:
    def test_refuses_seat_keyed_rows(self):
        t = _charge_ready_tenant()
        biz, seat = _pooled_business(t)
        rec = _row(t, seat, status="failed_permanent")
        with pytest.raises(CommandError, match="seat"):
            call_command("repush_usage_invoice", str(rec.id))
        rec.refresh_from_db()
        assert rec.status == "failed_permanent"  # untouched

    def test_refuses_rows_not_in_a_repushable_status(self):
        """Only failed/failed_permanent/skipped rows may be reset: pending/pushing
        are owned by the hourly reconcile; pushed is already billed."""
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="pushed", stripe_invoice_id="in_1",
                   push_phase="finalized", push_attempts=1)
        for status in ("pushed", "pushing", "pending"):
            CustomerUsageInvoice.objects.filter(id=rec.id).update(status=status)
            with pytest.raises(CommandError, match=f"status '{status}'"):
                call_command("repush_usage_invoice", str(rec.id))
            rec.refresh_from_db()
            assert rec.status == status  # untouched
            assert rec.push_attempts == 1  # counters not reset

    def test_rebill_void_clears_pointer_and_list_match_skips_the_void_invoice(self):
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="failed_permanent", stripe_invoice_id="in_void",
                   push_phase="finalized",
                   push_attempts=settings.UBB_POSTPAID_PUSH_MAX_ATTEMPTS)
        call_command("repush_usage_invoice", str(rec.id), "--rebill-void")
        rec.refresh_from_db()
        assert rec.status == "pending" and rec.push_attempts == 0
        assert rec.stripe_invoice_id == "" and rec.push_phase == ""
        # The old VOID invoice still matches by metadata but must be skipped (5b),
        # so the push mints a replacement instead of resuming the corpse.
        void_inv = _stripe_invoice(id="in_void", status="void", rec=rec)
        with _stripe(listed=[void_inv]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert m.create.call_count == 1
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_new"

    def test_rebill_void_rotates_every_idempotency_key_family(self):
        """Critical-1: within Stripe's 24h key window the legacy keys would
        replay the recorded (now-void) invoice/items/finalize and Phase 3 would
        record 'pushed' against the corpse — the bumped generation must rotate
        ALL THREE key families so the replay is impossible."""
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="failed_permanent", stripe_invoice_id="in_void",
                   push_phase="finalized", push_attempts=3,
                   line_snapshot=[["", 1_000_000]])
        original_create_key = f"usage-invoice-{rec.id}"  # the gen-0 legacy key
        call_command("repush_usage_invoice", str(rec.id), "--rebill-void")
        rec.refresh_from_db()
        assert rec.rebill_generation == 1
        assert rec.line_snapshot == []  # a rebill is a FRESH billing decision
        void_inv = _stripe_invoice(id="in_void", status="void", rec=rec)
        with _stripe(listed=[void_inv]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        create_key = m.create.call_args.kwargs["idempotency_key"]
        assert create_key != original_create_key  # the replay key is retired
        assert create_key == f"usage-invoice-{rec.id}-g1"
        assert m.item_create.call_args.kwargs["idempotency_key"] == f"usage-item-{rec.id}-g1-0"
        assert m.finalize.call_args.kwargs["idempotency_key"] == f"usage-finalize-{rec.id}-g1"
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_new"

    def test_repush_preserves_pinned_carry_in_every_mode(self):
        """F1.1: carry_in_micros is untouched by BOTH repush modes — a resumed
        push replays the pinned reservation; a --rebill-void re-bills the same
        carry (the voided invoice never collected it). It must never be
        auto-returned to the residual ledger."""
        from apps.billing.invoicing.models import PostpaidResidualLedger
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="failed_permanent", stripe_invoice_id="in_1",
                   push_phase="invoice_created", carry_in_micros=4_567)
        call_command("repush_usage_invoice", str(rec.id))
        rec.refresh_from_db()
        assert rec.status == "pending" and rec.carry_in_micros == 4_567
        CustomerUsageInvoice.objects.filter(id=rec.id).update(status="failed_permanent")
        call_command("repush_usage_invoice", str(rec.id), "--rebill-void")
        rec.refresh_from_db()
        assert rec.status == "pending" and rec.carry_in_micros == 4_567
        assert rec.stripe_invoice_id == "" and rec.line_snapshot == []
        # Neither mode deposited the parked pin back into the ledger.
        assert not PostpaidResidualLedger.objects.filter(customer=c).exists()

    def test_forced_re_record_replaces_line_items_never_duplicates(self):
        """Important-2 belt-and-braces: Phase 3 deletes the recorded line items
        inside the atomic re-record so a repush of a row that already recorded
        once can never leave duplicate UsageInvoiceLineItem rows."""
        from apps.billing.invoicing.models import UsageInvoiceLineItem
        t = _charge_ready_tenant()
        c = _customer(t)
        rec = _row(t, c, status="failed", stripe_invoice_id="in_1", push_phase="finalized")
        UsageInvoiceLineItem.objects.create(
            usage_invoice=rec, dimension="stale", amount_micros=999,
            stripe_invoice_item_id="ii_stale")
        with _stripe(retrieve=_stripe_invoice(id="in_1", status="open", rec=rec),
                     items=[_stripe_item(id="ii_new", line_index="0")]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed"
        assert m.item_create.call_count == 0  # adopt path: zero Stripe writes
        assert rec.line_items.count() == 1  # replaced, never appended
        assert list(rec.line_items.values_list("stripe_invoice_item_id", flat=True)) == ["ii_new"]


@pytest.mark.django_db
def test_failed_permanent_event_type_is_registered():
    """An unregistered event type dispatches to zero handlers — assert the
    registry actually knows usage.invoice_push_failed_permanent."""
    from apps.platform.events.registry import handler_registry
    handlers = handler_registry.get_handlers(FAILED_EVENT)
    assert handlers, "usage.invoice_push_failed_permanent must be registered in events/apps.py"
