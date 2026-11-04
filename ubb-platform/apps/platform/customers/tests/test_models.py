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
                transaction_type="usage_deduction",
                amount_micros=-amount_micros,
                balance_after_micros=locked.balance_micros,
                description="usage",
                idempotency_key=key,
            )
        wallet.refresh_from_db()
        return txn

    def _credit(self, wallet, amount_micros, key, txn_type="top_up"):
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
        self.assertEqual(txn.transaction_type, "usage_deduction")

    def test_wallet_credit(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="u2"
        )
        wallet = Wallet.objects.create(customer=customer)
        txn = self._credit(wallet, amount_micros=20_000_000, key="topup:u2:1")
        self.assertEqual(wallet.balance_micros, 20_000_000)
        self.assertEqual(txn.transaction_type, "top_up")

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


#: What decides a customer's billing owner (`Customer.resolve_billing_owner`).
TOPOLOGY_FIELDS = {"account_type", "parent", "billing_topology"}


class TopologyIsDeclaredAtCreationTest(TestCase):
    """A customer's billing topology is declared when it is created and is not
    editable afterwards in v1 (R10 Stage C3, F-7; owner/consultant ruling
    2026-11-04). The postpaid close bills a NEW invoice to the owner the
    topology names, and every posting carries the owner it was recorded under,
    so a mid-period change would bill recorded usage twice or not at all. The
    Django admin was the one supported surface that could change it; on an
    EXISTING customer its account type, parent and billing topology are now
    read-only there, and its add form still declares them at creation."""

    def setUp(self):
        from django.contrib import admin
        from django.contrib.auth import get_user_model
        from django.test import Client, RequestFactory

        self.tenant = Tenant.objects.create(name="Topology")
        self.pooled = Customer.objects.create(
            tenant=self.tenant, external_id="pooled-biz", account_type="business",
            billing_topology="pooled", metadata={"note": "pooled"})
        self.allocated = Customer.objects.create(
            tenant=self.tenant, external_id="allocated-biz", account_type="business",
            billing_topology="allocated", metadata={"note": "allocated"})
        self.seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat-1", account_type="seat",
            parent=self.pooled, metadata={"note": "seat"})
        self.solo = Customer.objects.create(
            tenant=self.tenant, external_id="solo", metadata={"note": "solo"})
        self.operator = get_user_model().objects.create_superuser(
            username="operator", email="operator@example.com", password="pw")
        self.http = Client()
        self.http.force_login(self.operator)
        self.model_admin = admin.site._registry[Customer]
        self.request = RequestFactory().get("/")
        self.request.user = self.operator

    @staticmethod
    def _form(customer, **overrides):
        """Every field the change form posts, at the customer's own values."""
        import json
        data = {
            "tenant": str(customer.tenant_id), "external_id": customer.external_id,
            "stripe_customer_id": customer.stripe_customer_id, "status": customer.status,
            "metadata": json.dumps(customer.metadata),
            "account_type": customer.account_type,
            "parent": str(customer.parent_id) if customer.parent_id else "",
            "billing_topology": customer.billing_topology,
            "suspension_reason": customer.suspension_reason,
            "deleted_at_0": "", "deleted_at_1": "",
        }
        data.update(overrides)
        return data

    def _change(self, customer, **overrides):
        from django.urls import reverse
        url = reverse("admin:customers_customer_change", args=[customer.pk])
        return self.http.post(url, self._form(customer, **overrides))

    def _change_form_fields(self, customer):
        from django.urls import reverse
        response = self.http.get(
            reverse("admin:customers_customer_change", args=[customer.pk]))
        self.assertEqual(response.status_code, 200)
        return set(response.context["adminform"].form.fields)

    def test_an_existing_seats_parent_is_read_only_in_the_admin(self):
        self.assertTrue(TOPOLOGY_FIELDS <= set(
            self.model_admin.get_readonly_fields(self.request, self.seat)))
        self.assertFalse(TOPOLOGY_FIELDS & self._change_form_fields(self.seat))

    def test_an_existing_businesss_billing_topology_is_read_only_in_the_admin(self):
        for business in (self.pooled, self.allocated):
            with self.subTest(business=business.external_id):
                self.assertTrue(TOPOLOGY_FIELDS <= set(
                    self.model_admin.get_readonly_fields(self.request, business)))
                self.assertFalse(TOPOLOGY_FIELDS & self._change_form_fields(business))

    def test_a_tampered_change_form_moves_no_topology_fact(self):
        """The form is VALID and saves (302) — the topology values posted
        beside the ordinary fields are simply not the form's to take."""
        cases = [
            (self.seat, {"parent": str(self.allocated.pk)}),
            (self.seat, {"parent": ""}),
            (self.seat, {"account_type": "individual", "parent": ""}),
            (self.pooled, {"billing_topology": "allocated"}),
            (self.allocated, {"billing_topology": "pooled"}),
            (self.allocated, {"account_type": "individual", "billing_topology": ""}),
            (self.solo, {"account_type": "seat", "parent": str(self.pooled.pk)}),
        ]
        for customer, tampered in cases:
            before = (customer.account_type, customer.parent_id, customer.billing_topology)
            owner_before = customer.resolve_billing_owner().id
            with self.subTest(customer=customer.external_id, tampered=tampered):
                response = self._change(customer, **tampered)
                self.assertEqual(response.status_code, 302)
                customer.refresh_from_db()
                self.assertEqual(
                    (customer.account_type, customer.parent_id, customer.billing_topology),
                    before)
                self.assertEqual(customer.resolve_billing_owner().id, owner_before)

    def test_an_ordinary_edit_still_saves(self):
        response = self._change(
            self.seat, stripe_customer_id="cus_Seat1", metadata='{"note": "edited"}')
        self.assertEqual(response.status_code, 302)
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.stripe_customer_id, "cus_Seat1")
        self.assertEqual(self.seat.metadata, {"note": "edited"})
        self.assertEqual((self.seat.account_type, self.seat.parent_id),
                         ("seat", self.pooled.id))

    def test_the_add_form_still_declares_topology_at_creation(self):
        from django.urls import reverse
        self.assertFalse(TOPOLOGY_FIELDS & set(
            self.model_admin.get_readonly_fields(self.request, None)))
        response = self.http.post(reverse("admin:customers_customer_add"), {
            "tenant": str(self.tenant.pk), "external_id": "seat-2",
            "stripe_customer_id": "", "status": "active",
            "metadata": '{"note": "new"}', "account_type": "seat",
            "parent": str(self.allocated.pk), "billing_topology": "",
            "suspension_reason": "", "deleted_at_0": "", "deleted_at_1": "",
        })
        self.assertEqual(response.status_code, 302)
        created = Customer.objects.get(tenant=self.tenant, external_id="seat-2")
        self.assertEqual((created.account_type, created.parent_id),
                         ("seat", self.allocated.id))
        self.assertEqual(created.resolve_billing_owner(), created)
