from django.test import TestCase
from apps.invoicing.tasks import generate_weekly_invoices, _invoice_period


class InvoicingTaskImportTest(TestCase):
    def test_task_exists(self):
        self.assertTrue(callable(generate_weekly_invoices))

    def test_invoice_period_exists(self):
        self.assertTrue(callable(_invoice_period))

    def test_task_has_acks_late(self):
        self.assertTrue(generate_weekly_invoices.acks_late)
