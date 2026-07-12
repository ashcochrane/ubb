"""F5.5 opt-in consolidated postpaid billing.

Usage rides the billing owner's subscription-renewal DRAFT invoice (one Stripe
invoice per period) instead of a standalone usage invoice. The renewal draft is
FOREIGN — Stripe mints it at the cycle anchor and auto-finalizes it ~1h later,
on ITS clock — so the safety addendum replaces F0.1's blind-adopt with a
diff-by-line_index resume:

- target still draft  -> ensure OUR items only, NO finalize call (ever);
- target finalized    -> all lines present: adopt; some/none: bill ONLY the
  missing lines on a fresh standalone remainder we control and record THAT id.

Every line lands on exactly one finalized invoice — no double-bill, no silent
loss. Standalone is the automatic fallback whenever the draft window is missed.
"""
import contextlib
import datetime
import logging
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from celery.schedules import crontab
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.invoicing.models import (
    CustomerUsageInvoice, PostpaidResidualLedger, PostpaidUsageConfig)
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService
from core.exceptions import StripeFatalError

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
SVC = "apps.billing.invoicing.services.postpaid_service.stripe"

# Frozen two-line aggregation used throughout: 60 + 40 cents, 5_000µ residual.
LINES = [("a", 600_000), ("b", 405_000)]
TOTAL = 1_005_000


def _tenant(consolidate=True):
    t = Tenant.objects.create(
        name="T", products=["metering", "billing"], billing_mode="postpaid",
        stripe_connected_account_id="acct_x", charges_enabled=True)
    PostpaidUsageConfig.objects.create(tenant=t, consolidate_with_subscription=consolidate)
    return t


def _customer(t, external_id="c1", stripe_customer_id="cus_1"):
    return Customer.objects.create(
        tenant=t, external_id=external_id, stripe_customer_id=stripe_customer_id)


def _sub(t, c, status="active", with_plan=True, sub_id="sub_1", paused=False):
    from apps.subscriptions.models import (
        CustomerSubscriptionItem, StripeSubscription, TenantBillingPlan)
    now = timezone.now()
    sub = StripeSubscription.objects.create(
        tenant=t, customer=c, stripe_subscription_id=sub_id,
        stripe_product_name="P", status=status, amount_micros=49_000_000,
        interval="month", quantity=1, current_period_start=now,
        current_period_end=now, last_synced_at=now, paused=paused)
    plan = None
    if with_plan:
        plan = TenantBillingPlan.objects.create(
            tenant=t, key=f"pro-{sub_id}", name="Pro", access_fee_micros=49_000_000)
    CustomerSubscriptionItem.objects.create(
        tenant=t, customer=c, stripe_subscription=sub,
        stripe_subscription_item_id=f"si_{sub_id}", axis="access",
        stripe_price_id="price_1", unit_amount_micros=49_000_000, plan=plan)
    return sub


def _renewal(id="in_renewal", status="draft", age_seconds=120, auto_advance=True):
    """The subscription renewal invoice: FOREIGN (no usage metadata)."""
    inv = MagicMock()
    inv.id = id
    inv.status = status
    inv.deleted = False
    inv.auto_advance = auto_advance
    inv.created = int(timezone.now().timestamp()) - age_seconds
    inv.metadata = {}
    return inv


def _item(rec, line_index, id=None, amount=None):
    """An InvoiceItem of OURS (carries the rec's metadata)."""
    item = MagicMock()
    item.id = id or f"ii_renewal_{line_index}"
    item.amount = amount if amount is not None else (60 if line_index == 0 else 40)
    item.metadata = {"usage_invoice_id": str(rec.id), "line_index": str(line_index)}
    return item


def _paged(objs):
    page = MagicMock()
    page.auto_paging_iter.side_effect = lambda: iter(list(objs))
    return page


@contextlib.contextmanager
def _stripe(retrieve=None, sub_drafts=(), meta_listed=(), items=(), created_id="in_new",
            item_create=None):
    """Patch the SDK surface; Invoice.list routes on kwargs: subscription= is
    the F5.5 target resolution, customer= is the I4 metadata lookup."""
    counter = {"n": 0}

    def default_item_create(*a, **k):
        counter["n"] += 1
        return MagicMock(id=f"ii_new_{counter['n']}")

    def invoice_list(*a, **k):
        return _paged(sub_drafts if "subscription" in k else meta_listed)

    with patch(f"{SVC}.Invoice.retrieve", return_value=retrieve) as m_retrieve, \
         patch(f"{SVC}.Invoice.list", side_effect=invoice_list) as m_list, \
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


def _agg(total=TOTAL, lines=None):
    return patch.object(PostpaidUsageService, "aggregate_lines",
                        return_value=(total, list(lines) if lines is not None else list(LINES)))


def _consolidated_rec(t, c, **kwargs):
    """A mid-push rec resuming against a consolidated target."""
    defaults = dict(
        period_start=PS, period_end=PE, total_billed_micros=TOTAL,
        status="pending", stripe_invoice_id="in_renewal",
        invoice_kind="consolidated", push_phase="invoice_created",
        line_snapshot=[[label, amount] for label, amount in LINES],
        carry_in_micros=0)
    defaults.update(kwargs)
    rec = CustomerUsageInvoice.objects.create(tenant=t, customer=c, **defaults)
    if rec.carry_in_micros is not None:
        # A pinned carry implies the Phase-1 reservation already created the
        # ledger (take-and-zero) — model that state exactly.
        PostpaidResidualLedger.objects.get_or_create(customer=c, defaults={"tenant": t})
    return rec


def _subscription_targets(mock_list):
    """Every Invoice.list call that did F5.5 target resolution."""
    return [call for call in mock_list.call_args_list if "subscription" in call.kwargs]


@pytest.mark.django_db
class TestHappyPath:
    def test_usage_rides_the_renewal_draft(self):
        t, c = _tenant(), None
        c = _customer(t)
        _sub(t, c)
        with _stripe(sub_drafts=[_renewal()]) as m, _agg():
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed"
        assert rec.invoice_kind == "consolidated"
        assert rec.stripe_invoice_id == "in_renewal"
        assert rec.push_phase == "items_pinned"  # consolidated never reaches a finalize
        # The target resolution listed the sub's drafts; NO standalone invoice
        # was minted and NO finalize was ever called (Stripe finalizes the renewal).
        assert len(_subscription_targets(m.list)) == 1
        assert _subscription_targets(m.list)[0].kwargs["subscription"] == "sub_1"
        assert m.create.call_count == 0
        assert m.finalize.call_count == 0
        # Items pinned BY ID to the renewal draft, in the -c{target} namespace.
        assert m.item_create.call_count == 2
        for n, call in enumerate(m.item_create.call_args_list):
            assert call.kwargs["invoice"] == "in_renewal"
            assert call.kwargs["idempotency_key"] == f"usage-item-{rec.id}-cin_renewal-{n}"
            assert call.kwargs["metadata"] == {
                "usage_invoice_id": str(rec.id), "line_index": str(n),
                "consolidated": "true"}
        assert m.item_create.call_args_list[0].kwargs["amount"] == 60
        assert m.item_create.call_args_list[1].kwargs["amount"] == 40
        # Residual carry recorded exactly as in standalone mode.
        assert rec.residual_micros == 5_000
        assert PostpaidResidualLedger.objects.get(customer=c).balance_micros == 5_000
        assert rec.line_items.count() == 2


@pytest.mark.django_db
class TestStandaloneFallback:
    def test_window_missed_old_draft_falls_back_with_log(self, caplog):
        t = _tenant()
        c = _customer(t)
        _sub(t, c)
        old = _renewal(age_seconds=46 * 60)
        with _stripe(sub_drafts=[old]) as m, _agg(), \
             caplog.at_level(logging.WARNING, logger="ubb.billing"):
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.invoice_kind == "standalone"
        assert rec.stripe_invoice_id == "in_new"
        assert m.create.call_count == 1 and m.finalize.call_count == 1
        missed = [r for r in caplog.records
                  if r.getMessage() == "postpaid.consolidation_window_missed"]
        assert len(missed) == 1
        assert missed[0].data["draft_invoice_id"] == "in_renewal"
        assert missed[0].data["draft_age_seconds"] >= 45 * 60

    def test_no_draft_falls_back_with_log(self, caplog):
        t = _tenant()
        c = _customer(t)
        _sub(t, c)
        with _stripe(sub_drafts=[]) as m, _agg(), \
             caplog.at_level(logging.WARNING, logger="ubb.billing"):
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.invoice_kind == "standalone"
        assert m.create.call_count == 1 and m.finalize.call_count == 1
        missed = [r for r in caplog.records
                  if r.getMessage() == "postpaid.consolidation_window_missed"]
        assert len(missed) == 1
        assert missed[0].data["draft_invoice_id"] is None

    def test_never_auto_advancing_draft_falls_back(self, caplog):
        """A draft that will never auto-finalize must not swallow usage items."""
        t = _tenant()
        c = _customer(t)
        _sub(t, c)
        with _stripe(sub_drafts=[_renewal(auto_advance=False)]) as m, _agg(), \
             caplog.at_level(logging.WARNING, logger="ubb.billing"):
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.invoice_kind == "standalone"
        assert any(r.getMessage() == "postpaid.consolidation_window_missed"
                   for r in caplog.records)

    def test_flag_off_never_resolves_a_target(self):
        t = _tenant(consolidate=False)
        c = _customer(t)
        _sub(t, c)
        with _stripe(sub_drafts=[_renewal()]) as m, _agg():
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.invoice_kind == "standalone"
        assert _subscription_targets(m.list) == []
        assert m.create.call_count == 1 and m.finalize.call_count == 1

    def test_no_active_subscription_falls_back(self):
        t = _tenant()
        c = _customer(t)  # flag on, but no subscription at all
        with _stripe(sub_drafts=[_renewal()]) as m, _agg():
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.invoice_kind == "standalone"
        assert _subscription_targets(m.list) == []  # the port said no — no Stripe lookup

    def test_past_due_subscription_is_eligible(self):
        t = _tenant()
        c = _customer(t)
        _sub(t, c, status="past_due")
        with _stripe(sub_drafts=[_renewal()]) as m, _agg():
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.invoice_kind == "consolidated"
        assert rec.stripe_invoice_id == "in_renewal"
        assert m.create.call_count == 0


@pytest.mark.django_db
class TestEligibilityPort:
    def test_no_subscription_returns_none(self):
        from apps.subscriptions.ports import get_active_subscription_for_consolidation
        t = _tenant()
        c = _customer(t)
        assert get_active_subscription_for_consolidation(t, c) is None

    def test_active_planned_subscription_returns_plain_data(self):
        from apps.subscriptions.ports import get_active_subscription_for_consolidation
        t = _tenant()
        c = _customer(t)
        _sub(t, c)
        assert get_active_subscription_for_consolidation(t, c) == {
            "stripe_subscription_id": "sub_1"}

    def test_past_due_is_eligible_canceled_is_not(self):
        from apps.subscriptions.ports import get_active_subscription_for_consolidation
        t = _tenant()
        c = _customer(t)
        _sub(t, c, status="past_due", sub_id="sub_pd")
        assert get_active_subscription_for_consolidation(t, c) == {
            "stripe_subscription_id": "sub_pd"}
        c2 = _customer(t, external_id="c2", stripe_customer_id="cus_2")
        _sub(t, c2, status="canceled", sub_id="sub_cx")
        assert get_active_subscription_for_consolidation(t, c2) is None

    def test_paused_or_unplanned_subscription_is_ineligible(self):
        from apps.subscriptions.ports import get_active_subscription_for_consolidation
        t = _tenant()
        c = _customer(t)
        _sub(t, c, paused=True, sub_id="sub_paused")
        assert get_active_subscription_for_consolidation(t, c) is None
        c2 = _customer(t, external_id="c2", stripe_customer_id="cus_2")
        _sub(t, c2, with_plan=False, sub_id="sub_foreign")  # not UBB-managed
        assert get_active_subscription_for_consolidation(t, c2) is None


@pytest.mark.django_db
class TestSafetyAddendumResume:
    def test_resume_draft_still_open_creates_only_missing_items_no_finalize(self):
        t = _tenant()
        c = _customer(t)
        rec = _consolidated_rec(t, c)
        with _stripe(retrieve=_renewal(), items=[_item(rec, 0)]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_renewal"
        assert rec.invoice_kind == "consolidated"
        assert m.create.call_count == 0
        assert m.finalize.call_count == 0  # NEVER finalize a foreign renewal
        assert m.item_create.call_count == 1  # only the missing line
        kw = m.item_create.call_args.kwargs
        assert kw["invoice"] == "in_renewal"
        assert kw["idempotency_key"] == f"usage-item-{rec.id}-cin_renewal-1"
        assert sorted(rec.line_items.values_list("dimension", "stripe_invoice_item_id")) \
            == [("a", "ii_renewal_0"), ("b", "ii_new_1")]

    def test_foreign_items_on_the_renewal_never_shadow_ours(self):
        """The renewal sweeps foreign pending items too; an alien item with a
        colliding line_index but a different usage_invoice_id must be ignored."""
        t = _tenant()
        c = _customer(t)
        rec = _consolidated_rec(t, c)
        alien = MagicMock()
        alien.id = "ii_alien"
        alien.metadata = {"usage_invoice_id": "someone-else", "line_index": "0"}
        with _stripe(retrieve=_renewal(), items=[alien]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed"
        assert m.item_create.call_count == 2  # both OUR lines were still missing
        assert "ii_alien" not in set(
            rec.line_items.values_list("stripe_invoice_item_id", flat=True))

    def test_partial_adopt_splits_remainder_onto_standalone(self, caplog):
        """THE addendum case: the renewal auto-finalized with only line 0 —
        line 1 must bill on a fresh standalone remainder, exactly once."""
        t = _tenant()
        c = _customer(t)
        rec = _consolidated_rec(t, c)
        with _stripe(retrieve=_renewal(status="open"), items=[_item(rec, 0)]) as m, \
             _agg(), caplog.at_level(logging.ERROR, logger="ubb.billing"):
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        # The remainder invoice: -r{target} namespace, OUR metadata, finalized.
        assert m.create.call_count == 1
        ckw = m.create.call_args.kwargs
        assert ckw["idempotency_key"] == f"usage-invoice-{rec.id}-rin_renewal"
        assert ckw["metadata"]["usage_invoice_id"] == str(rec.id)
        assert ckw["metadata"]["consolidated_remainder_of"] == "in_renewal"
        assert m.item_create.call_count == 1  # ONLY the missing line
        ikw = m.item_create.call_args.kwargs
        assert ikw["invoice"] == "in_new"
        assert ikw["amount"] == 40
        assert ikw["idempotency_key"] == f"usage-item-{rec.id}-rin_renewal-1"
        assert m.finalize.call_count == 1  # the remainder only — we control it
        fkw = m.finalize.call_args.kwargs
        assert fkw["invoice"] == "in_new"
        assert fkw["idempotency_key"] == f"usage-finalize-{rec.id}-rin_renewal"
        # Phase 3 records the invoice WE control; the kind stays for audit.
        assert rec.status == "pushed"
        assert rec.stripe_invoice_id == "in_new"
        assert rec.invoice_kind == "consolidated"
        split = [r for r in caplog.records
                 if r.getMessage() == "postpaid.consolidation_partial_split"]
        assert len(split) == 1
        assert split[0].data["consolidated_invoice_id"] == "in_renewal"
        assert split[0].data["remainder_invoice_id"] == "in_new"
        assert split[0].data["remainder_line_indexes"] == ["1"]
        # Per-line item ids recorded from BOTH invoices.
        pairs = dict(rec.line_items.values_list("dimension", "stripe_invoice_item_id"))
        assert pairs == {"a": "ii_renewal_0", "b": "ii_new_1"}

    def test_full_adopt_records_with_zero_stripe_writes(self):
        t = _tenant()
        c = _customer(t)
        rec = _consolidated_rec(t, c)
        with _stripe(retrieve=_renewal(status="paid"),
                     items=[_item(rec, 0), _item(rec, 1)]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_renewal"
        assert rec.push_phase == "finalized"
        assert m.create.call_count == 0
        assert m.item_create.call_count == 0
        assert m.finalize.call_count == 0
        pairs = dict(rec.line_items.values_list("dimension", "stripe_invoice_item_id"))
        assert pairs == {"a": "ii_renewal_0", "b": "ii_renewal_1"}

    def test_finalize_race_during_item_create_falls_through_to_split(self, caplog):
        """The 45-min pre-check narrows but cannot close the race: the draft
        finalizes between our item creates. The fatal from Stripe must re-read
        the target and fork into the split, never park failed_permanent."""
        t = _tenant()
        c = _customer(t)
        rec = _consolidated_rec(t, c)
        boom = StripeFatalError("invoice is no longer a draft")
        with _stripe(retrieve=_renewal(status="open"), items=[_item(rec, 0)],
                     item_create=[boom, MagicMock(id="ii_rem_1")]) as m, _agg(), \
             caplog.at_level(logging.ERROR, logger="ubb.billing"):
            # Pointer-less fresh push would retrieve nothing; use the resume rec
            # whose first retrieve must return the still-draft renewal.
            with patch(f"{SVC}.Invoice.retrieve",
                       side_effect=[_renewal(), _renewal(status="open")]) as m_retrieve:
                PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed"
        assert rec.stripe_invoice_id == "in_new"  # the remainder we control
        assert m_retrieve.call_count == 2  # pointer resume + post-race re-read
        # First create attempt was the consolidated namespace, the retry the
        # remainder namespace — composed without collision.
        keys = [call.kwargs["idempotency_key"] for call in m.item_create.call_args_list]
        assert keys == [f"usage-item-{rec.id}-cin_renewal-1",
                        f"usage-item-{rec.id}-rin_renewal-1"]
        assert m.finalize.call_count == 1
        assert any(r.getMessage() == "postpaid.consolidation_partial_split"
                   for r in caplog.records)

    def test_crashed_split_resumes_the_remainder_via_metadata_lookup(self):
        """Crash after the remainder invoice was created but before its item:
        the retry must FIND it (I4 metadata match), not mint a sibling."""
        t = _tenant()
        c = _customer(t)
        rec = _consolidated_rec(t, c)
        remainder = MagicMock()
        remainder.id = "in_rem"
        remainder.status = "draft"
        remainder.deleted = False
        remainder.metadata = {"usage_invoice_id": str(rec.id)}
        with _stripe(retrieve=_renewal(status="open"), items=[_item(rec, 0)],
                     meta_listed=[remainder]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "pushed" and rec.stripe_invoice_id == "in_rem"
        assert m.create.call_count == 0  # resumed, never recreated
        assert m.item_create.call_count == 1
        assert m.item_create.call_args.kwargs["invoice"] == "in_rem"
        assert m.finalize.call_args.kwargs["invoice"] == "in_rem"


@pytest.mark.django_db
class TestRebillVoidInterplay:
    def test_rebill_void_refused_for_consolidated_rec(self):
        """F5.5 Fix 3: --rebill-void must be refused for a consolidated rec.
        A consolidated target is the customer's subscription renewal — voiding
        it via this flag is not applicable; the operator must use a plain repush
        to resume or interact with the renewal directly in Stripe."""
        from django.core.management.base import CommandError
        t = _tenant()
        c = _customer(t)
        _sub(t, c)
        rec = _consolidated_rec(
            t, c, status="failed_permanent", stripe_invoice_id="in_renewal_old",
            push_phase="items_pinned", push_attempts=3)
        with pytest.raises(CommandError) as exc_info:
            call_command("repush_usage_invoice", str(rec.id), "--rebill-void")
        assert "consolidated" in str(exc_info.value).lower()
        # Row must be completely untouched — no generation bump, pointer intact.
        rec.refresh_from_db()
        assert rec.status == "failed_permanent"
        assert rec.stripe_invoice_id == "in_renewal_old"
        assert rec.rebill_generation == 0  # never bumped

    def test_plain_repush_consolidated_resumes_from_pointer(self):
        """Plain repush (no --rebill-void) is still allowed and resumes from the
        existing pointer, re-resolving nothing (retrieve-first path)."""
        t = _tenant()
        c = _customer(t)
        _sub(t, c)
        rec = _consolidated_rec(
            t, c, status="failed_permanent", stripe_invoice_id="in_renewal_old",
            push_phase="items_pinned", push_attempts=3)
        call_command("repush_usage_invoice", str(rec.id))
        rec.refresh_from_db()
        assert rec.status == "pending"
        assert rec.stripe_invoice_id == "in_renewal_old"  # pointer preserved
        assert rec.push_attempts == 0
        assert rec.rebill_generation == 0  # unchanged


@pytest.mark.django_db
class TestConsolidatedAr:
    """invoice.paid for the SUBSCRIPTION invoice must mark BOTH the
    SubscriptionInvoice row AND the consolidated usage rec paid."""

    def _pushed_consolidated(self, t, c):
        return CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=PS, period_end=PE,
            total_billed_micros=TOTAL, status="pushed",
            stripe_invoice_id="in_renewal", invoice_kind="consolidated")

    def _sub_invoice_obj(self, status="paid"):
        return SimpleNamespace(
            id="in_renewal", subscription="sub_1", parent=None,
            amount_paid=4900, currency="usd",
            hosted_invoice_url="https://pay/r", invoice_pdf="https://pdf/r",
            period_start=1750000000, period_end=1752000000,
            status_transitions=SimpleNamespace(paid_at=1750100000),
            status=status)

    def test_webhook_invoice_paid_marks_both_rows(self):
        from api.v1.webhooks import handle_invoice_paid
        from apps.subscriptions.models import SubscriptionInvoice
        t = _tenant()
        c = _customer(t)
        _sub(t, c)
        rec = self._pushed_consolidated(t, c)
        event = SimpleNamespace(account="acct_x",
                                data=SimpleNamespace(object=self._sub_invoice_obj()))
        handle_invoice_paid(event)
        row = SubscriptionInvoice.objects.get(stripe_invoice_id="in_renewal")
        assert row.status == "paid"
        rec.refresh_from_db()
        assert rec.payment_status == "paid"
        assert rec.paid_at is not None
        assert rec.hosted_invoice_url == "https://pay/r"

    def test_webhook_standalone_rec_is_untouched_by_subscription_events(self):
        """A standalone rec that (impossibly) shares the id must not be hit by
        the consolidated extension — the kind filter is the guard."""
        from api.v1.webhooks import handle_invoice_paid
        t = _tenant()
        c = _customer(t)
        _sub(t, c)
        rec = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=PS, period_end=PE,
            status="pushed", stripe_invoice_id="in_renewal",
            invoice_kind="standalone")
        event = SimpleNamespace(account="acct_x",
                                data=SimpleNamespace(object=self._sub_invoice_obj()))
        handle_invoice_paid(event)
        rec.refresh_from_db()
        assert rec.payment_status is None

    def test_poller_repairs_both_rows(self):
        from apps.billing.invoicing.tasks import reconcile_invoice_payment_status
        from apps.subscriptions.models import SubscriptionInvoice
        t = _tenant()
        c = _customer(t)
        sub = _sub(t, c)
        si = SubscriptionInvoice.objects.create(
            tenant=t, customer=c, stripe_subscription=sub,
            stripe_invoice_id="in_renewal", status="open")
        rec = self._pushed_consolidated(t, c)
        inv = MagicMock()
        inv.id = "in_renewal"
        inv.status = "paid"
        inv.subscription = "sub_1"
        inv.parent = None
        inv.hosted_invoice_url = "https://pay/r"
        inv.invoice_pdf = None
        inv.amount_paid = 4900
        listing = MagicMock()
        listing.auto_paging_iter.return_value = iter([inv])
        with patch("apps.billing.invoicing.tasks.stripe.Invoice.list",
                   return_value=listing), \
             patch("apps.billing.invoicing.tasks.time.sleep"):
            reconcile_invoice_payment_status()
        si.refresh_from_db()
        rec.refresh_from_db()
        assert si.status == "paid"
        assert rec.payment_status == "paid"
        assert rec.paid_at is not None
        assert rec.hosted_invoice_url == "https://pay/r"


@pytest.mark.django_db
class TestGen1ConsolidatedComposedKey:
    def test_gen1_consolidated_push_key_namespace(self):
        """A standalone rec that was --rebill-void'd (rebill_generation=1, pointer
        cleared, invoice_kind still 'standalone') whose tenant THEN enables
        consolidation: the next push resolves a consolidated target and each item's
        idempotency key must compose BOTH the generation namespace AND the
        consolidated namespace — usage-item-{rec.id}-g1-c{target_id}-{i}.

        Asserts:
        - Invoice.create is NOT called (target resolved, no standalone create).
        - Each item's idempotency_key exactly matches the composed form.
        - Invoice.finalize_invoice is NOT called (consolidated, Stripe auto-finalizes).
        - rec.invoice_kind flips to 'consolidated'.
        """
        t = _tenant()
        c = _customer(t)
        _sub(t, c)
        # Simulate the post-rebill-void state: generation bumped, pointer cleared,
        # snapshot cleared, invoice_kind still "standalone" (as repush_usage_invoice
        # leaves it — the flip to "consolidated" happens in Phase 2a on the NEXT push).
        rec = CustomerUsageInvoice.objects.create(
            tenant=t, customer=c,
            period_start=PS, period_end=PE,
            status="pending",
            stripe_invoice_id="",        # pointer cleared by --rebill-void
            invoice_kind="standalone",   # not yet flipped — that happens in Phase 2a
            rebill_generation=1,         # bumped by repush_usage_invoice --rebill-void
            line_snapshot=[],            # cleared; will be re-frozen on this push
            carry_in_micros=None,
            total_billed_micros=0,
        )
        PostpaidResidualLedger.objects.get_or_create(customer=c, defaults={"tenant": t})

        target_id = "in_renewal"
        with _stripe(sub_drafts=[_renewal(id=target_id)]) as m, _agg():
            PostpaidUsageService.push_customer_period(t, c, PS, PE)

        rec.refresh_from_db()

        # No standalone invoice was created; target was resolved from the sub draft.
        assert m.create.call_count == 0, "Invoice.create must not be called when a target is resolved"
        # Consolidated: Stripe auto-finalizes — we must NEVER call finalize.
        assert m.finalize.call_count == 0, "finalize_invoice must not be called for a consolidated rec"
        # The rec must have flipped kind and be pushed.
        assert rec.invoice_kind == "consolidated"
        assert rec.status == "pushed"
        assert rec.stripe_invoice_id == target_id

        # Core assertion: both namespaces composed in every item idempotency key.
        assert m.item_create.call_count == 2
        for i, call in enumerate(m.item_create.call_args_list):
            expected_key = f"usage-item-{rec.id}-g1-c{target_id}-{i}"
            actual_key = call.kwargs["idempotency_key"]
            assert actual_key == expected_key, (
                f"line {i}: expected idempotency_key={expected_key!r}, got {actual_key!r}")
            assert call.kwargs["invoice"] == target_id


def test_close_beat_lands_inside_the_renewal_draft_window():
    """Stripe drafts the renewal at the 1st 00:00 anchor and auto-finalizes it
    ~1h later — the postpaid close must run between the two."""
    sched = settings.CELERY_BEAT_SCHEDULE["close-postpaid-usage-periods"]["schedule"]
    assert sched == crontab(minute=5, hour=0, day_of_month=1)
