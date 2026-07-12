from unittest.mock import patch
from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.platform.tenants.models import Tenant
from apps.platform.events.models import OutboxEvent


class CustomerModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")

    def test_create_customer(self):
        customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="user_42",
        )
        self.assertEqual(customer.status, "active")

    def test_no_wallet_auto_created(self):
        """Wallet is no longer auto-created on Customer.save()."""
        customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="user_42",
        )
        self.assertFalse(Wallet.objects.filter(customer=customer).exists())

    def _deduct(self, wallet, amount_micros, key):
        """Keyed deduction helper — mirrors the real drawdown path."""
        from django.db import transaction
        with transaction.atomic():
            locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
            locked.balance_micros -= amount_micros
            locked.save(update_fields=["balance_micros", "updated_at"])
            txn = WalletTransaction.objects.create(
                wallet=locked,
                transaction_type="USAGE_DEDUCTION",
                amount_micros=-amount_micros,
                balance_after_micros=locked.balance_micros,
                description="usage",
                idempotency_key=key,
            )
        wallet.refresh_from_db()
        return txn

    def _credit(self, wallet, amount_micros, key, txn_type="TOP_UP"):
        """Keyed credit helper — mirrors the real top-up path."""
        from django.db import transaction
        with transaction.atomic():
            locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
            locked.balance_micros += amount_micros
            locked.save(update_fields=["balance_micros", "updated_at"])
            txn = WalletTransaction.objects.create(
                wallet=locked,
                transaction_type=txn_type,
                amount_micros=amount_micros,
                balance_after_micros=locked.balance_micros,
                description="top-up",
                idempotency_key=key,
            )
        wallet.refresh_from_db()
        return txn

    def test_wallet_deduct(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="u1"
        )
        wallet = Wallet.objects.create(customer=customer, balance_micros=10_000_000)
        txn = self._deduct(wallet, amount_micros=1_500_000, key="deduct:u1:1")
        self.assertEqual(wallet.balance_micros, 8_500_000)
        self.assertEqual(txn.transaction_type, "USAGE_DEDUCTION")

    def test_wallet_credit(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="u2"
        )
        wallet = Wallet.objects.create(customer=customer)
        txn = self._credit(wallet, amount_micros=20_000_000, key="topup:u2:1")
        self.assertEqual(wallet.balance_micros, 20_000_000)
        self.assertEqual(txn.transaction_type, "TOP_UP")

    def test_wallet_deduct_allows_negative(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="u3"
        )
        wallet = Wallet.objects.create(customer=customer)
        txn = self._deduct(wallet, amount_micros=1_000_000, key="deduct:u3:1")
        self.assertEqual(wallet.balance_micros, -1_000_000)

    def test_soft_delete_emits_customer_deleted_event(self):
        """soft_delete() emits a CustomerDeleted outbox event."""
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_del_1"
        )
        customer.soft_delete()

        event = OutboxEvent.objects.get(event_type="customer.deleted")
        self.assertEqual(event.payload["customer_id"], str(customer.id))
        self.assertEqual(event.payload["tenant_id"], str(self.tenant.id))

    def test_soft_delete_creates_outbox_event(self):
        """soft_delete() creates an outbox event atomically with the delete."""
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_del_atomic"
        )
        customer.soft_delete()

        # Both the soft delete and the outbox event should exist
        customer.refresh_from_db()
        self.assertTrue(customer.is_deleted)
        self.assertTrue(OutboxEvent.objects.filter(event_type="customer.deleted").exists())

    def test_soft_delete_rolls_back_on_event_failure(self):
        """If write_event fails, the soft delete should roll back."""
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_del_rollback"
        )
        with patch(
            "apps.platform.events.outbox.write_event",
            side_effect=RuntimeError("outbox failure"),
        ):
            with self.assertRaises(RuntimeError):
                customer.soft_delete()

        # Customer should NOT be soft-deleted because the transaction rolled back
        customer.refresh_from_db()
        self.assertFalse(customer.is_deleted)
