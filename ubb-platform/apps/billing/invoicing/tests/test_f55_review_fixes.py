"""F5.5 review fixes (Fix 1, Fix 2, Fix 3).

Fix 1: Phase-2a guarded update ignores its row count — a stale/reclaimed
       worker must abort before any InvoiceItem.create.

Fix 2: PUT postpaid-config partial-update asymmetry — usage_line_item_group_by
       must use a None sentinel so an omit preserves the current value.

Fix 3: repush_usage_invoice --rebill-void must refuse consolidated recs with
       a clear message; plain repush must still be allowed.
"""
import contextlib
import datetime
import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, call

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.invoicing.models import (
    CustomerUsageInvoice, PostpaidResidualLedger, PostpaidUsageConfig)
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)
SVC = "apps.billing.invoicing.services.postpaid_service.stripe"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _tenant(consolidate=False):
    t = Tenant.objects.create(
        name="T", products=["metering", "billing"], billing_mode="postpaid",
        stripe_connected_account_id="acct_x", charges_enabled=True)
    PostpaidUsageConfig.objects.create(
        tenant=t, consolidate_with_subscription=consolidate)
    return t


def _customer(t, external_id="c1", stripe_customer_id="cus_1"):
    return Customer.objects.create(
        tenant=t, external_id=external_id, stripe_customer_id=stripe_customer_id)


def _consolidated_rec(t, c, status="pushing", **kwargs):
    defaults = dict(
        period_start=PS, period_end=PE, total_billed_micros=1_005_000,
        status=status, stripe_invoice_id="in_renewal",
        invoice_kind="consolidated", push_phase="invoice_created",
        line_snapshot=[["a", 600_000], ["b", 405_000]],
        carry_in_micros=0,
        push_attempts=1,
    )
    defaults.update(kwargs)
    rec = CustomerUsageInvoice.objects.create(tenant=t, customer=c, **defaults)
    PostpaidResidualLedger.objects.get_or_create(customer=c, defaults={"tenant": t})
    return rec


def _paged(objs):
    page = MagicMock()
    page.auto_paging_iter.side_effect = lambda: iter(list(objs))
    return page


@contextlib.contextmanager
def _stripe_surface(retrieve=None, sub_drafts=(), meta_listed=(), items=(),
                    created_id="in_new"):
    """Patch the full SDK surface used by _push_to_stripe."""
    counter = {"n": 0}

    def default_item_create(*a, **k):
        counter["n"] += 1
        return MagicMock(id=f"ii_new_{counter['n']}")

    def invoice_list(*a, **k):
        return _paged(sub_drafts if "subscription" in k else meta_listed)

    with patch(f"{SVC}.Invoice.retrieve", return_value=retrieve), \
         patch(f"{SVC}.Invoice.list", side_effect=invoice_list), \
         patch(f"{SVC}.Invoice.create",
               return_value=MagicMock(id=created_id)) as m_create, \
         patch(f"{SVC}.InvoiceItem.list",
               return_value=_paged(items)) as m_item_list, \
         patch(f"{SVC}.InvoiceItem.create",
               side_effect=default_item_create) as m_item_create, \
         patch(f"{SVC}.Invoice.finalize_invoice",
               return_value=MagicMock(id=created_id)), \
         patch("apps.platform.events.tasks.process_single_event"):
        yield SimpleNamespace(create=m_create,
                              item_list=m_item_list,
                              item_create=m_item_create)


def _agg(total=1_005_000, lines=None):
    if lines is None:
        lines = [("a", 600_000), ("b", 405_000)]
    return patch.object(PostpaidUsageService, "aggregate_lines",
                        return_value=(total, list(lines)))


# ===========================================================================
# Fix 1 — Phase-2a claim-loss abort
# ===========================================================================

@pytest.mark.django_db(transaction=True)
class TestPhase2aClaimLossAbort:
    """A stale worker whose Phase-2a guarded update matches 0 rows (another
    worker or a race flipped status away from 'pushing') MUST raise before
    creating any InvoiceItem.

    The test simulates this race by patching Invoice.create (which runs BEFORE
    the Phase-2a update and already has the row in 'pushing') to flip the row
    status away from 'pushing', so the Phase-2a filter matches 0 rows.
    """

    def _setup_consolidated(self):
        t = _tenant(consolidate=True)
        c = _customer(t)
        rec = _consolidated_rec(t, c, status="pending",
                                stripe_invoice_id="",
                                invoice_kind="standalone",
                                push_phase="")

        renewal = MagicMock()
        renewal.id = "in_renewal_fresh"
        renewal.status = "draft"
        renewal.deleted = False
        renewal.auto_advance = True
        # Very recent so consolidation window is NOT missed
        import time
        renewal.created = int(time.time()) - 10
        renewal.metadata = {}
        return t, c, rec, renewal

    def test_consolidated_stale_worker_raises_before_item_create(self):
        """Consolidated path: Invoice.create is used as the injection point to
        flip the row away from 'pushing', then the Phase-2a update returns 0."""
        t, c, rec, renewal = self._setup_consolidated()

        def _invoice_create_and_steal(*a, **k):
            # Return the draft renewal (so consolidated=True path is taken),
            # but simultaneously flip the row away from 'pushing' to simulate
            # the claim being stolen by another worker.
            CustomerUsageInvoice.objects.filter(id=rec.id).update(status="pending")
            inv = MagicMock()
            inv.id = "in_renewal_fresh"
            inv.status = "draft"
            inv.deleted = False
            inv.metadata = {}
            return inv

        def _invoice_list(*a, **k):
            if "subscription" in k:
                return _paged([renewal])
            return _paged([])

        with patch(f"{SVC}.Invoice.list", side_effect=_invoice_list), \
             patch(f"{SVC}.Invoice.retrieve", return_value=renewal), \
             patch(f"{SVC}.Invoice.create", side_effect=_invoice_create_and_steal) as m_create, \
             patch(f"{SVC}.InvoiceItem.list", return_value=_paged([])), \
             patch(f"{SVC}.InvoiceItem.create") as m_item_create, \
             patch(f"{SVC}.Invoice.finalize_invoice"), \
             patch("apps.platform.events.tasks.process_single_event"), \
             _agg():
            with pytest.raises(RuntimeError, match="postpaid.claim_lost"):
                PostpaidUsageService.push_customer_period(t, c, PS, PE)

        # The critical assertion: no item was ever created.
        assert m_item_create.call_count == 0

    def test_standalone_stale_worker_raises_before_item_create(self):
        """Standalone path: same injection — Invoice.create steals the row,
        Phase-2a returns 0 rows updated, RuntimeError raised before items."""
        t = _tenant(consolidate=False)
        c = _customer(t)
        rec = _consolidated_rec(t, c, status="pending",
                                stripe_invoice_id="",
                                invoice_kind="standalone",
                                push_phase="")

        def _invoice_create_and_steal(*a, **k):
            # Flip the row away from 'pushing' before Phase-2a can run.
            CustomerUsageInvoice.objects.filter(id=rec.id).update(status="pending")
            return MagicMock(id="in_new_standalone")

        with patch(f"{SVC}.Invoice.list", return_value=_paged([])), \
             patch(f"{SVC}.Invoice.create",
                   side_effect=_invoice_create_and_steal) as m_create, \
             patch(f"{SVC}.InvoiceItem.list", return_value=_paged([])), \
             patch(f"{SVC}.InvoiceItem.create") as m_item_create, \
             patch(f"{SVC}.Invoice.finalize_invoice"), \
             patch("apps.platform.events.tasks.process_single_event"), \
             _agg():
            with pytest.raises(RuntimeError, match="postpaid.claim_lost"):
                PostpaidUsageService.push_customer_period(t, c, PS, PE)

        assert m_item_create.call_count == 0


# ===========================================================================
# Fix 2 — config partial-update sentinel
# ===========================================================================

class PostpaidConfigPartialUpdateTest(TestCase):
    """PUT /postpaid-config with usage_line_item_group_by omitted must preserve
    the existing value, not overwrite it with the schema default."""

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="T2", products=["metering", "billing"])
        _, self.key = TenantApiKey.create_key(self.tenant, label="k")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def test_omitting_group_by_preserves_existing_value(self):
        # First: set a non-default group_by
        r = self.http.put(
            "/api/v1/billing/postpaid-config",
            data=json.dumps({"usage_line_item_group_by": "product_id"}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["usage_line_item_group_by"], "product_id")

        # Second PUT omits group_by entirely — must NOT overwrite with "".
        r = self.http.put(
            "/api/v1/billing/postpaid-config",
            data=json.dumps({"consolidate_with_subscription": True}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        # group_by must be preserved
        self.assertEqual(body["usage_line_item_group_by"], "product_id",
                         "Omitting group_by must preserve its current value, not reset to ''")
        self.assertTrue(body["consolidate_with_subscription"])

    def test_explicit_empty_string_clears_group_by(self):
        # Set group_by to something
        self.http.put(
            "/api/v1/billing/postpaid-config",
            data=json.dumps({"usage_line_item_group_by": "product_id"}),
            content_type="application/json", **self._auth())

        # Explicitly pass "" — must clear it.
        r = self.http.put(
            "/api/v1/billing/postpaid-config",
            data=json.dumps({"usage_line_item_group_by": ""}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["usage_line_item_group_by"], "")

    def test_both_fields_omitted_preserves_both(self):
        # Establish a non-default state
        self.http.put(
            "/api/v1/billing/postpaid-config",
            data=json.dumps({"usage_line_item_group_by": "model",
                             "consolidate_with_subscription": True}),
            content_type="application/json", **self._auth())

        # Empty body PUT — both fields omitted, both must survive.
        r = self.http.put(
            "/api/v1/billing/postpaid-config",
            data=json.dumps({}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["usage_line_item_group_by"], "model")
        self.assertTrue(body["consolidate_with_subscription"])


# ===========================================================================
# Fix 3 — --rebill-void refused for consolidated recs
# ===========================================================================

@pytest.mark.django_db
class TestRebillVoidRefusedForConsolidated:
    """--rebill-void on a consolidated rec must raise CommandError with a clear
    message. Plain repush (no --rebill-void) must still be allowed."""

    def _consolidated_db_rec(self, t, c, status="failed_permanent"):
        return CustomerUsageInvoice.objects.create(
            tenant=t, customer=c,
            period_start=PS, period_end=PE,
            total_billed_micros=1_000_000,
            status=status,
            stripe_invoice_id="in_renewal",
            invoice_kind="consolidated",
            push_phase="items_pinned",
            push_attempts=3,
        )

    def test_rebill_void_on_consolidated_raises_command_error(self):
        t = Tenant.objects.create(
            name="T3", products=["metering", "billing"], billing_mode="postpaid",
            stripe_connected_account_id="acct_x", charges_enabled=True)
        c = Customer.objects.create(
            tenant=t, external_id="c3", stripe_customer_id="cus_3")
        rec = self._consolidated_db_rec(t, c)

        with pytest.raises(CommandError) as exc_info:
            call_command("repush_usage_invoice", str(rec.id), "--rebill-void")

        msg = str(exc_info.value)
        assert "consolidated" in msg.lower()
        # Row must be untouched — status and stripe_invoice_id unchanged.
        rec.refresh_from_db()
        assert rec.status == "failed_permanent"
        assert rec.stripe_invoice_id == "in_renewal"

    def test_plain_repush_still_allowed_for_consolidated(self):
        """A plain repush (no --rebill-void) is resume-safe and must not be blocked."""
        t = Tenant.objects.create(
            name="T4", products=["metering", "billing"], billing_mode="postpaid",
            stripe_connected_account_id="acct_x", charges_enabled=True)
        c = Customer.objects.create(
            tenant=t, external_id="c4", stripe_customer_id="cus_4")
        rec = self._consolidated_db_rec(t, c)

        # Must not raise.
        call_command("repush_usage_invoice", str(rec.id))
        rec.refresh_from_db()
        assert rec.status == "pending"
        assert rec.stripe_invoice_id == "in_renewal"  # pointer preserved for resume
        assert rec.push_attempts == 0
