from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.customers.models import Customer, TopUpAttempt
from apps.usage.models import Invoice


class TopUpReceiptTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com",
            stripe_customer_id="cus_test",
        )
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="manual",
            status="succeeded",
            stripe_checkout_session_id="cs_test",
        )

    @patch("apps.invoicing.services.stripe_call")
    def test_create_receipt_invoice(self, mock_stripe_call):
        mock_invoice = MagicMock()
        mock_invoice.id = "inv_test123"
        mock_stripe_call.return_value = mock_invoice

        from apps.invoicing.services import ReceiptService
        ReceiptService.create_topup_receipt(self.customer, self.attempt)

        invoice = Invoice.objects.get(top_up_attempt=self.attempt)
        self.assertEqual(invoice.total_amount_micros, 20_000_000)
        self.assertEqual(invoice.status, "paid")
        self.assertIsNotNone(invoice.paid_at)

    @patch("apps.invoicing.services.stripe_call")
    def test_stripe_failure_does_not_create_local_invoice(self, mock_stripe_call):
        """If Stripe fails, no local Invoice is created -- allows retry."""
        mock_stripe_call.side_effect = Exception("Stripe API error")

        from apps.invoicing.services import ReceiptService
        ReceiptService.create_topup_receipt(self.customer, self.attempt)

        self.assertFalse(Invoice.objects.filter(top_up_attempt=self.attempt).exists())

    def test_receipt_idempotent(self):
        Invoice.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            top_up_attempt=self.attempt,
            total_amount_micros=20_000_000,
            status="paid",
        )
        from apps.invoicing.services import ReceiptService
        ReceiptService.create_topup_receipt(self.customer, self.attempt)
        self.assertEqual(Invoice.objects.filter(top_up_attempt=self.attempt).count(), 1)
