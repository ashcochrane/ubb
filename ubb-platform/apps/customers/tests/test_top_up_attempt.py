from django.test import TestCase
from django.db import IntegrityError, transaction
from apps.tenants.models import Tenant
from apps.customers.models import Customer, TopUpAttempt


class TopUpAttemptModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", email="t@t.com"
        )

    def test_create_pending_attempt(self):
        attempt = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        self.assertEqual(attempt.status, "pending")
        self.assertEqual(attempt.amount_micros, 20_000_000)
        self.assertIsNone(attempt.stripe_payment_intent_id)
        self.assertIsNone(attempt.failure_reason)

    def test_unique_pending_auto_topup_per_customer(self):
        TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TopUpAttempt.objects.create(
                    customer=self.customer,
                    amount_micros=10_000_000,
                    trigger="auto_topup",
                    status="pending",
                )

    def test_multiple_manual_pending_allowed(self):
        TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="manual",
            status="pending",
        )
        attempt2 = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=30_000_000,
            trigger="manual",
            status="pending",
        )
        self.assertEqual(attempt2.trigger, "manual")

    def test_pending_auto_topup_allowed_after_previous_succeeded(self):
        attempt1 = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        attempt1.status = "succeeded"
        attempt1.save()
        attempt2 = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        self.assertEqual(attempt2.status, "pending")

    def test_expired_status(self):
        attempt = TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        attempt.status = "expired"
        attempt.save()
        self.assertEqual(attempt.status, "expired")
