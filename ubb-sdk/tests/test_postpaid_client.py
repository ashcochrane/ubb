import unittest
from unittest.mock import patch, MagicMock
from ubb.billing import BillingClient
from ubb._core.models.usage_invoice_out import UsageInvoiceOut


def _usage_invoice(period_start, period_end, total, *, status, stripe_invoice_id,
                   skip_reason=None, payment_status=None):
    """One row of the ONE usage-invoice shape (R10 Stage C5, F-15): the shared
    base every usage-invoice route answers, plus the tenant read's two
    operator fields."""
    return {
        "id": "7a1d1b9e-5e6e-4c9a-9a6d-1b2c3d4e5f60", "customer_id": "c1",
        "external_id": "ext-c1", "period_start": period_start,
        "period_end": period_end, "currency": "usd", "total_billed_micros": total,
        "status": status, "skip_reason": skip_reason,
        "stripe_invoice_id": stripe_invoice_id, "pushed_at": None,
        "payment_status": payment_status, "paid_at": None, "payment_failed_at": None,
        "hosted_invoice_url": "", "invoice_pdf": "",
        "created_at": "2026-07-01T00:00:00Z",
        "push_attempts": 1, "last_attempt_error": "",
    }


class PostpaidClientTest(unittest.TestCase):
    def setUp(self):
        self.client = BillingClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.billing.httpx.Client.get")
    def test_get_usage_invoices(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": [
            _usage_invoice("2026-06-01", "2026-07-01", 1000, status="pushed",
                           stripe_invoice_id="in_1", payment_status="open")],
            "next_cursor": None, "has_more": False})
        page = self.client.get_usage_invoices("c1")
        rows = page.data
        self.assertIsInstance(rows[0], UsageInvoiceOut)
        self.assertEqual(rows[0].total_billed_micros, 1000)
        self.assertEqual(rows[0].payment_status, "open")
        self.assertEqual(rows[0].push_attempts, 1)
        self.assertFalse(page.has_more)
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/billing/customers/c1/usage-invoices")
        self.assertEqual(mock_get.call_args.kwargs["params"], {"limit": 50})

    @patch("ubb.billing.httpx.Client.get")
    def test_get_usage_invoices_answers_the_page_envelope(self, mock_get):
        """SDK 5.0.0: the one cursor envelope, not a bare list that dropped
        the cursor (R10 Stage C5, F-15). `payment_status` is null while the
        invoice is not yet collectible — null, never a fifth word."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": [
            _usage_invoice("2026-05-01", "2026-06-01", 500, status="skipped",
                           stripe_invoice_id="", skip_reason="no_usage"),
            _usage_invoice("2026-06-01", "2026-07-01", 2000, status="pushed",
                           stripe_invoice_id="in_2", payment_status="paid"),
        ], "next_cursor": "c_next", "has_more": True})
        page = self.client.get_usage_invoices("c2", cursor="c_prev", limit=2)
        self.assertEqual(len(page.data), 2)
        self.assertEqual(page.data[0].status, "skipped")
        self.assertEqual(page.data[0].skip_reason, "no_usage")
        self.assertIsNone(page.data[0].payment_status)
        self.assertEqual(page.data[1].stripe_invoice_id, "in_2")
        self.assertEqual(page.data[1].payment_status, "paid")
        self.assertEqual((page.next_cursor, page.has_more), ("c_next", True))
        self.assertEqual(mock_get.call_args.kwargs["params"],
                         {"limit": 2, "cursor": "c_prev"})

    @patch("ubb.billing.httpx.Client.get")
    def test_get_postpaid_config(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "group_by": "field:product_id",
            "consolidate_with_subscription": False})
        out = self.client.get_postpaid_config()
        self.assertEqual(out["group_by"], "field:product_id")
        self.assertEqual(out["consolidate_with_subscription"], False)
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/billing/postpaid-config")

    @patch("ubb.billing.httpx.Client.put")
    def test_set_postpaid_config(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "group_by": "field:product_id",
            "consolidate_with_subscription": False})
        out = self.client.set_postpaid_config("field:product_id")
        self.assertEqual(out["group_by"], "field:product_id")
        self.assertEqual(mock_put.call_args.args[0], "/api/v1/billing/postpaid-config")
        self.assertEqual(mock_put.call_args.kwargs["json"],
                         {"group_by": "field:product_id"})
        # None = leave the consolidation opt-in unchanged: the flag must be
        # OMITTED from the body, never sent as false.
        self.assertNotIn("consolidate_with_subscription", mock_put.call_args.kwargs["json"])

    @patch("ubb.billing.httpx.Client.put")
    def test_an_explicit_empty_string_clears_the_grouping(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "group_by": "",
            "consolidate_with_subscription": False})
        out = self.client.set_postpaid_config(group_by="")
        self.assertEqual(out["group_by"], "")
        body = mock_put.call_args.kwargs["json"]
        self.assertEqual(body, {"group_by": ""})

    @patch("ubb.billing.httpx.Client.put")
    def test_set_postpaid_config_consolidation_flag(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "group_by": "field:product_id",
            "consolidate_with_subscription": True})
        out = self.client.set_postpaid_config(consolidate_with_subscription=True)
        self.assertEqual(out["consolidate_with_subscription"], True)
        body = mock_put.call_args.kwargs["json"]
        self.assertEqual(body["consolidate_with_subscription"], True)

    @patch("ubb.billing.httpx.Client.put")
    def test_omitting_the_grouping_leaves_the_stored_axis_alone(self, mock_put):
        """⚠ **THIS CALL USED TO CLEAR THE TENANT'S INVOICE LINES (fixed in #531).**

        The PUT is partial: an omitted field is left as stored, an explicit
        `""` clears it (F5.5 Fix 2 on the server). The wrapper defaulted the
        grouping to `""`, so turning consolidation on through the SDK also
        collapsed every invoice to a single line — the exact asymmetry the
        server's `None` sentinel exists to prevent, reintroduced one layer up.
        The default is `None` now, the same sentinel its sibling parameter
        always had, so the key is not sent at all."""
        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "group_by": "field:product_id",
            "consolidate_with_subscription": True})
        self.client.set_postpaid_config(consolidate_with_subscription=True)
        self.assertEqual(mock_put.call_args.kwargs["json"],
                         {"consolidate_with_subscription": True})

    @patch("ubb.billing.httpx.Client.put")
    def test_the_facade_forwards_the_grouping_and_omits_what_it_was_not_given(
            self, mock_put):
        """`UBBClient` has its own copy of this signature (#409's lesson: a
        facade is where a lower client's change goes to be lost)."""
        from ubb.client import UBBClient

        mock_put.return_value = MagicMock(status_code=200, json=lambda: {
            "group_by": "rollup:event_category",
            "consolidate_with_subscription": False})
        client = UBBClient(api_key="ubb_live_t", base_url="http://localhost:8001",
                           billing=True)
        try:
            client.set_postpaid_config(group_by="rollup:event_category")
            self.assertEqual(mock_put.call_args.kwargs["json"],
                             {"group_by": "rollup:event_category"})
            client.set_postpaid_config(consolidate_with_subscription=False)
            self.assertEqual(mock_put.call_args.kwargs["json"],
                             {"consolidate_with_subscription": False})
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
