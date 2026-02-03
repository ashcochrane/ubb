from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.db import transaction

from apps.tenants.models import Tenant
from apps.customers.models import Customer, AutoTopUpConfig, TopUpAttempt
from apps.usage.services.auto_topup_service import AutoTopUpService


class AutoTopUpServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        self.wallet = self.customer.wallet
        self.wallet.balance_micros = -1_000_000  # below threshold
        self.wallet.save()
        AutoTopUpConfig.objects.create(
            customer=self.customer,
            is_enabled=True,
            trigger_threshold_micros=0,
            top_up_amount_micros=20_000_000,
        )

    def test_creates_pending_attempt(self):
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.status, "pending")
        self.assertEqual(attempt.trigger, "auto_topup")
        self.assertEqual(attempt.amount_micros, 20_000_000)

    def test_returns_none_if_pending_exists(self):
        TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNone(attempt)

    def test_returns_none_if_balance_above_threshold(self):
        self.wallet.balance_micros = 10_000_000  # above threshold
        self.wallet.save()
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNone(attempt)

    def test_returns_none_if_not_enabled(self):
        config = self.customer.auto_top_up_config
        config.is_enabled = False
        config.save()
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNone(attempt)

    def test_returns_none_if_no_config(self):
        # Hard delete (bypass soft-delete) to truly remove the config
        AutoTopUpConfig.all_objects.filter(customer=self.customer).delete()
        # Refresh to clear Django's cached reverse relation
        self.customer = Customer.objects.get(pk=self.customer.pk)
        with transaction.atomic():
            attempt = AutoTopUpService.create_pending_attempt(self.customer, self.wallet)
        self.assertIsNone(attempt)
