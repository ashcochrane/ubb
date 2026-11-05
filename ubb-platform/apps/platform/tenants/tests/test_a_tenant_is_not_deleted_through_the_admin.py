"""A tenant is inspected and maintained in the Django admin, never deleted
there (R10 Stage C4; owner/consultant Ruling C, 2026-11-05, PLAN §7 item 41).

Deleting a tenant row CASCADES to every one of its customers
(``Customer.tenant``) as a database HARD delete with no lifecycle event — the
route around the Customer admin's own ruling (no bulk delete; the single
delete is the canonical soft delete). Tenant deletion is not a supported v1
operation, so the Tenant admin offers neither its delete page nor the bulk
action; inspection and ordinary maintenance are unchanged.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.tests._helpers import the_forms_own_post


class ATenantIsNotDeletedThroughTheAdminTest(TestCase):
    def setUp(self):
        operator = get_user_model().objects.create_superuser(
            username="operator", email="operator@example.com", password="pw")
        self.http = Client()
        self.http.force_login(operator)
        self.request = RequestFactory().get("/")
        self.request.user = operator
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
        url = reverse("admin:tenants_tenant_delete", args=[self.doomed.pk])
        self.assertEqual(self.http.get(url).status_code, 403)
        self.assertEqual(self.http.post(url, {"post": "yes"}).status_code, 403)
        self._everything_survives()

    def test_the_bulk_delete_action_cannot_be_posted(self):
        response = self.http.post(reverse("admin:tenants_tenant_changelist"), {
            "action": "delete_selected", "_selected_action": [str(self.doomed.pk)],
            "post": "yes"})
        self.assertEqual(response.status_code, 200)           # re-rendered: no such action
        self._everything_survives()

    def test_inspection_and_ordinary_maintenance_remain(self):
        self.assertEqual(
            self.http.get(reverse("admin:tenants_tenant_changelist")).status_code, 200)
        url = reverse("admin:tenants_tenant_change", args=[self.doomed.pk])
        form = self.http.get(url).context["adminform"].form
        response = self.http.post(url, the_forms_own_post(form, name="Renamed"))
        self.assertEqual(response.status_code, 302, getattr(response, "context", None)
                         and response.context["adminform"].form.errors)
        self.doomed.refresh_from_db()
        self.assertEqual(self.doomed.name, "Renamed")
        self._everything_survives()
