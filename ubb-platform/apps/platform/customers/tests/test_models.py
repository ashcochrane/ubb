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
#: An existing customer's creation-only fields: its tenant and its topology.
CREATION_ONLY_FIELDS = TOPOLOGY_FIELDS | {"tenant"}


class _CustomerAdminCase(TestCase):
    """The Customer admin under an operator's login, with a pooled and an
    allocated business, a seat and a solo customer, and the change-form
    helpers. Shared by the creation-only (C3) and lifecycle (C4) tests below;
    it holds no test of its own."""

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


class TopologyIsDeclaredAtCreationTest(_CustomerAdminCase):
    """A customer's tenant and billing topology are declared when it is created
    and are not editable afterwards in v1 (R10 Stage C3, F-7; owner/consultant
    rulings 2026-11-04). The postpaid close bills a NEW invoice to the owner the
    topology names, and every posting carries the owner it was recorded under,
    so a mid-period change would bill recorded usage twice or not at all; and a
    customer moved between tenants would carry its ownership and history across
    the tenant boundary. The Django admin was the one supported surface that
    could change them; on an EXISTING customer its tenant, account type, parent
    and billing topology are read-only there. And the admin creates no
    customer at all: `POST /customers` is the one creation path, so these
    facts are only ever declared where they are validated."""

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

    def test_an_existing_customers_tenant_is_read_only_in_the_admin(self):
        for customer in (self.seat, self.pooled, self.solo):
            with self.subTest(customer=customer.external_id):
                self.assertIn("tenant", set(
                    self.model_admin.get_readonly_fields(self.request, customer)))
                self.assertNotIn("tenant", self._change_form_fields(customer))

    def test_a_tampered_change_form_cannot_move_a_customer_to_another_tenant(self):
        """The form is VALID and saves (302); the tenant posted beside the
        ordinary fields is not the form's to take, so nothing crosses."""
        elsewhere = Tenant.objects.create(name="Elsewhere")
        for customer in (self.seat, self.pooled, self.solo):
            with self.subTest(customer=customer.external_id):
                response = self._change(customer, tenant=str(elsewhere.pk))
                self.assertEqual(response.status_code, 302)
                customer.refresh_from_db()
                self.assertEqual(customer.tenant_id, self.tenant.id)
        self.assertFalse(Customer.all_objects.filter(tenant=elsewhere).exists())

    def test_a_tampered_change_form_mutates_none_of_the_four_at_once(self):
        elsewhere = Tenant.objects.create(name="Elsewhere")
        owner_before = self.seat.resolve_billing_owner().id
        response = self._change(
            self.seat, tenant=str(elsewhere.pk), account_type="business",
            parent="", billing_topology="allocated", stripe_customer_id="cus_Seat9")
        self.assertEqual(response.status_code, 302)
        self.seat.refresh_from_db()
        self.assertEqual(
            (self.seat.tenant_id, self.seat.account_type, self.seat.parent_id,
             self.seat.billing_topology),
            (self.tenant.id, "seat", self.pooled.id, ""))
        self.assertEqual(self.seat.resolve_billing_owner().id, owner_before)
        self.assertEqual(self.seat.stripe_customer_id, "cus_Seat9")  # the ordinary field saved

    def test_an_ordinary_edit_still_saves(self):
        response = self._change(
            self.seat, stripe_customer_id="cus_Seat1", metadata='{"note": "edited"}')
        self.assertEqual(response.status_code, 302)
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.stripe_customer_id, "cus_Seat1")
        self.assertEqual(self.seat.metadata, {"note": "edited"})
        self.assertEqual((self.seat.account_type, self.seat.parent_id),
                         ("seat", self.pooled.id))

    def _add(self, tenant, external_id, account_type, parent=None, topology=""):
        from django.urls import reverse
        return self.http.post(reverse("admin:customers_customer_add"), {
            "tenant": str(tenant.pk), "external_id": external_id,
            "stripe_customer_id": "", "status": "active",
            "metadata": '{"note": "new"}', "account_type": account_type,
            "parent": str(parent.pk) if parent else "", "billing_topology": topology,
            "suspension_reason": "", "deleted_at_0": "", "deleted_at_1": "",
        })

    def test_the_admin_is_not_a_customer_creation_surface(self):
        """Customers are created through `POST /customers` only (owner/
        consultant ruling 2026-11-04, R1). The admin's add form was a second
        creation workflow with other semantics: it could give a seat a billing
        owner in another tenant, or a pooled owner that is not a business, and
        it skipped the seat-quantity sync and the creation audit. It is closed:
        no permission, the add page refused, and nothing created by a POST —
        a legitimate shape or the corrupt ones alike."""
        from django.urls import reverse
        elsewhere = Tenant.objects.create(name="Elsewhere")
        elsewhere_pooled = Customer.objects.create(
            tenant=elsewhere, external_id="elsewhere-pooled", account_type="business",
            billing_topology="pooled", metadata={"note": "elsewhere"})
        before = Customer.all_objects.count()
        self.assertFalse(self.model_admin.has_add_permission(self.request))
        changelist = self.http.get(reverse("admin:customers_customer_changelist"))
        self.assertFalse(changelist.context["has_add_permission"])  # no "Add" button
        self.assertEqual(
            self.http.get(reverse("admin:customers_customer_add")).status_code, 403)
        attempts = [
            (self.tenant, "seat-2", "seat", self.pooled, ""),            # legitimate
            (self.tenant, "seat-x", "seat", elsewhere_pooled, ""),       # owner in another tenant
            (self.tenant, "indiv-pooled", "individual", None, "pooled"),  # a pooled non-business
            (self.tenant, "seat-y", "seat", self.solo, ""),              # a non-business parent
        ]
        for tenant, external_id, account_type, parent, topology in attempts:
            with self.subTest(external_id=external_id):
                response = self._add(tenant, external_id, account_type,
                                     parent=parent, topology=topology)
                self.assertEqual(response.status_code, 403)
        # Django's "save as new" on the change page is the add path too: it
        # posts to the change URL and is refused, whatever the topology says.
        response = self.http.post(
            reverse("admin:customers_customer_change", args=[self.seat.pk]),
            self._form(self.seat, external_id="seat-copy", tenant=str(elsewhere.pk),
                       parent=str(elsewhere_pooled.pk), _saveasnew="Save as new"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Customer.all_objects.count(), before)

    def _staff_with_every_customer_permission(self):
        """A staff user (not a superuser) granted add, change and view on
        customers — so a refusal to add is the admin's own rule, not a
        missing permission."""
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        from django.test import Client
        staff = get_user_model().objects.create_user(
            username="staff", email="staff@example.com", password="pw", is_staff=True)
        staff.user_permissions.set(Permission.objects.filter(
            content_type__app_label="customers", content_type__model="customer"))
        http = Client()
        http.force_login(staff)
        return http

    def test_even_a_user_granted_the_add_permission_cannot_add(self):
        from django.urls import reverse
        http = self._staff_with_every_customer_permission()
        self.assertEqual(http.get(reverse("admin:customers_customer_add")).status_code, 403)

    def test_the_changelist_and_an_existing_customers_change_page_remain(self):
        from django.urls import reverse
        staff = self._staff_with_every_customer_permission()
        for who, http in (("superuser", self.http), ("staff", staff)):
            with self.subTest(who=who):
                changelist = http.get(reverse("admin:customers_customer_changelist"))
                self.assertEqual(changelist.status_code, 200)
                for customer in (self.seat, self.pooled, self.solo):
                    self.assertEqual(http.get(reverse(
                        "admin:customers_customer_change", args=[customer.pk])).status_code, 200)
        for customer in (self.seat, self.pooled, self.solo):
            self.assertTrue(self.model_admin.has_change_permission(self.request, customer))
        # The staff user's ordinary edit saves, as the superuser's does.
        response = staff.post(
            reverse("admin:customers_customer_change", args=[self.solo.pk]),
            self._form(self.solo, stripe_customer_id="cus_Solo1"))
        self.assertEqual(response.status_code, 302)
        self.solo.refresh_from_db()
        self.assertEqual(self.solo.stripe_customer_id, "cus_Solo1")


#: A customer's lifecycle fields: changed only by the workflows that own their
#: side effects, never as raw fields in the admin (R10 Stage C4, PLAN §7 item 41).
LIFECYCLE_FIELDS = {"status", "suspension_reason", "deleted_at"}


class LifecycleFieldsAreNotAdminControlsTest(_CustomerAdminCase):
    """``status``, ``suspension_reason`` and ``deleted_at`` are read-only on an
    existing customer, and the bulk delete action is gone (R10 Stage C4;
    owner/consultant ruling 2026-11-05, PLAN §7 item 41). Edited raw, they
    bypassed every lifecycle side effect: a ``status`` edit suspended, lifted
    or closed a seat with no announcement and no roster notification; a
    ``deleted_at`` edit soft-deleted one the same way; a ``suspension_reason``
    edit from ``hard_floor`` to ``payment_failed`` let the AR pass lift a
    customer still past its floor; and the bulk action HARD-deleted rows. The
    manual hold has its own workflow (``set_customer_manual_hold``)."""

    def _roster_notifications(self):
        """Swap the roster's listeners for a recorder, for this test only."""
        from apps.platform.customers import hooks
        calls = []
        saved = list(hooks._listeners)
        hooks._listeners[:] = [calls.append]
        self.addCleanup(lambda: hooks._listeners.__setitem__(slice(None), saved))
        return calls

    def _lifecycle_events(self, customer):
        return OutboxEvent.objects.filter(
            event_type__in=("customer.suspended", "customer.reactivated",
                            "customer.deleted"),
            payload__customer_id=str(customer.id)).count()

    def test_the_lifecycle_fields_are_read_only_on_an_existing_customer(self):
        for customer in (self.seat, self.solo, self.pooled):
            with self.subTest(customer.external_id):
                self.assertTrue(LIFECYCLE_FIELDS <= set(
                    self.model_admin.get_readonly_fields(self.request, customer)))
                self.assertFalse(LIFECYCLE_FIELDS & self._change_form_fields(customer))

    def test_a_tampered_change_form_moves_no_lifecycle_field(self):
        notified = self._roster_notifications()
        tampers = {
            "status": {"status": "suspended"},
            "status to closed": {"status": "closed"},
            "suspension_reason": {"suspension_reason": "payment_failed"},
            "deleted_at": {"deleted_at_0": "2026-11-05", "deleted_at_1": "10:00:00"},
            "all at once": {"status": "suspended", "suspension_reason": "hard_floor",
                            "deleted_at_0": "2026-11-05", "deleted_at_1": "10:00:00"},
        }
        for name, tampered in tampers.items():
            with self.subTest(name):
                response = self._change(self.seat, **tampered)
                self.assertEqual(response.status_code, 302)
                self.seat.refresh_from_db()
                self.assertEqual((self.seat.status, self.seat.suspension_reason,
                                  self.seat.deleted_at), ("active", "", None))
                self.assertTrue(Customer.objects.filter(id=self.seat.id).exists())
        self.assertEqual(self._lifecycle_events(self.seat), 0)
        self.assertEqual(notified, [])

    def test_a_held_customer_stays_held_through_an_ordinary_edit(self):
        Customer.objects.filter(id=self.solo.id).update(status="suspended")
        self.solo.refresh_from_db()
        response = self._change(self.solo, status="active", metadata='{"note": "kept"}',
                                stripe_customer_id="cus_kept")
        self.assertEqual(response.status_code, 302)
        self.solo.refresh_from_db()
        self.assertEqual((self.solo.status, self.solo.metadata, self.solo.stripe_customer_id),
                         ("suspended", {"note": "kept"}, "cus_kept"))

    def test_an_ordinary_edit_never_writes_back_a_lifecycle_change_made_meanwhile(self):
        """The submit request reads the row, a manual hold commits, then the
        operator's ordinary edit saves: only the field the form changed is
        written, so the hold stands (a whole-row save wrote the `active` it had
        read back over it)."""
        loaded = Customer.objects.get(id=self.solo.id)        # the page's copy
        Customer.objects.filter(id=self.solo.id).update(status="suspended")   # meanwhile
        form_class = self.model_admin.get_form(self.request, loaded, change=True)
        form = form_class(self._form(loaded, metadata='{"note": "edited"}'), instance=loaded)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.changed_data, ["metadata"])
        self.model_admin.save_model(self.request, form.save(commit=False), form, change=True)
        self.solo.refresh_from_db()
        self.assertEqual((self.solo.status, self.solo.metadata),
                         ("suspended", {"note": "edited"}))

    def test_bulk_delete_is_not_an_admin_action(self):
        from django.urls import reverse
        self.assertNotIn("delete_selected", self.model_admin.get_actions(self.request))
        response = self.http.post(reverse("admin:customers_customer_changelist"), {
            "action": "delete_selected", "_selected_action": [str(self.solo.pk)],
            "post": "yes"})
        self.assertEqual(response.status_code, 200)           # re-rendered: no such action
        row = Customer.all_objects.get(id=self.solo.id)       # never hard-deleted
        self.assertIsNone(row.deleted_at)                      # nor deleted at all

    def test_the_single_object_delete_is_the_canonical_soft_delete(self):
        from django.urls import reverse
        notified = self._roster_notifications()
        response = self.http.post(
            reverse("admin:customers_customer_delete", args=[self.seat.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Customer.objects.filter(id=self.seat.id).exists())
        self.assertIsNotNone(Customer.all_objects.get(id=self.seat.id).deleted_at)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="customer.deleted", payload__customer_id=str(self.seat.id)).count(), 1)
        self.assertEqual([b.id for b in notified], [self.pooled.id])


def _the_forms_own_post(form, **changes):
    """An admin change form's own current values as a browser posts them, with
    ``changes`` applied — so the post is the form's, not the test's. A tenant's
    two JSON settings are required and an empty object reads as empty, so an
    operator fills each in, and so does this post (as
    ``api/v1/tests/test_a_money_mode_needs_its_payment_rail.py:_posted`` does)."""
    from django import forms
    changes = {"branding_config": {"filled_in": "by the operator"},
               "metadata": {"filled_in": "by the operator"}, **changes}
    data = {}
    for name, field in form.fields.items():
        value = changes.get(name, form[name].value())
        if isinstance(field, forms.BooleanField):
            if value:
                data[name] = "on"
        elif value is None:
            data[name] = ""
        else:
            data[name] = value if isinstance(value, str) else field.prepare_value(value)
    return data


class ATenantIsNotDeletedThroughTheAdminTest(_CustomerAdminCase):
    """Deleting a tenant row CASCADES to every one of its customers
    (``Customer.tenant``) as a database HARD delete with no lifecycle event —
    the route around the Customer admin's own ruling (no bulk delete; the
    single delete is the canonical soft delete). Tenant deletion is not a
    supported v1 operation, so the Tenant admin offers neither its delete page
    nor the bulk action, and inspection and ordinary maintenance are unchanged
    (R10 Stage C4; owner/consultant Ruling C, 2026-11-05, PLAN §7 item 41)."""

    def setUp(self):
        super().setUp()
        from django.contrib import admin
        self.tenant_admin = admin.site._registry[Tenant]
        # A tenant nothing else would shield: no seat holds a business by
        # PROTECT, so before Ruling C its delete went through, customers and all.
        self.doomed = Tenant.objects.create(name="Doomed")
        for external_id in ("first", "second"):
            Customer.objects.create(tenant=self.doomed, external_id=external_id)

    def _everything_survives(self):
        self.assertTrue(Tenant.objects.filter(id=self.doomed.id).exists())
        self.assertEqual(Customer.all_objects.filter(
            tenant_id=self.doomed.id, deleted_at__isnull=True).count(), 2)

    def test_the_tenant_admin_has_no_delete_permission_and_no_bulk_delete(self):
        self.assertFalse(self.tenant_admin.has_delete_permission(self.request, self.doomed))
        self.assertFalse(self.tenant_admin.has_delete_permission(self.request))
        self.assertNotIn("delete_selected", self.tenant_admin.get_actions(self.request))

    def test_the_delete_page_is_forbidden_and_no_customer_is_deleted(self):
        from django.urls import reverse
        url = reverse("admin:tenants_tenant_delete", args=[self.doomed.pk])
        self.assertEqual(self.http.get(url).status_code, 403)
        self.assertEqual(self.http.post(url, {"post": "yes"}).status_code, 403)
        self._everything_survives()

    def test_the_bulk_delete_action_cannot_be_posted(self):
        from django.urls import reverse
        response = self.http.post(reverse("admin:tenants_tenant_changelist"), {
            "action": "delete_selected", "_selected_action": [str(self.doomed.pk)],
            "post": "yes"})
        self.assertEqual(response.status_code, 200)           # re-rendered: no such action
        self._everything_survives()

    def test_inspection_and_ordinary_maintenance_remain(self):
        from django.urls import reverse
        self.assertEqual(
            self.http.get(reverse("admin:tenants_tenant_changelist")).status_code, 200)
        url = reverse("admin:tenants_tenant_change", args=[self.doomed.pk])
        form = self.http.get(url).context["adminform"].form
        response = self.http.post(url, _the_forms_own_post(form, name="Renamed"))
        self.assertEqual(response.status_code, 302, getattr(response, "context", None)
                         and response.context["adminform"].form.errors)
        self.doomed.refresh_from_db()
        self.assertEqual(self.doomed.name, "Renamed")
        self._everything_survives()
