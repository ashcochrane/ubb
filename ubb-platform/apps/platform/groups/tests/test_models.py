from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.groups.models import Group


class GroupModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")

    def test_create_group(self):
        group = Group.objects.create(
            tenant=self.tenant,
            name="Enterprise",
            slug="enterprise",
        )
        self.assertEqual(group.name, "Enterprise")
        self.assertEqual(group.slug, "enterprise")
        self.assertEqual(group.status, "active")
        self.assertIsNone(group.margin_pct)
        self.assertIsNone(group.parent)

    def test_group_with_margin(self):
        group = Group.objects.create(
            tenant=self.tenant,
            name="Premium",
            slug="premium",
            margin_pct=Decimal("65.00"),
        )
        group.refresh_from_db()
        self.assertEqual(group.margin_pct, Decimal("65.00"))

    def test_unique_active_slug_per_tenant(self):
        Group.objects.create(
            tenant=self.tenant,
            name="Enterprise",
            slug="enterprise",
        )
        with self.assertRaises(IntegrityError):
            Group.objects.create(
                tenant=self.tenant,
                name="Enterprise Copy",
                slug="enterprise",
            )

    def test_archived_slug_does_not_conflict(self):
        Group.objects.create(
            tenant=self.tenant,
            name="Enterprise",
            slug="enterprise",
            status="archived",
        )
        # Creating an active group with the same slug should succeed
        group = Group.objects.create(
            tenant=self.tenant,
            name="Enterprise v2",
            slug="enterprise",
            status="active",
        )
        self.assertEqual(group.status, "active")

    def test_parent_relationship(self):
        parent = Group.objects.create(
            tenant=self.tenant,
            name="Parent",
            slug="parent",
        )
        child = Group.objects.create(
            tenant=self.tenant,
            name="Child",
            slug="child",
            parent=parent,
        )
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.children.all())

    def test_parent_set_null_on_delete(self):
        parent = Group.objects.create(
            tenant=self.tenant,
            name="Parent",
            slug="parent",
        )
        child = Group.objects.create(
            tenant=self.tenant,
            name="Child",
            slug="child",
            parent=parent,
        )
        parent.delete()
        child.refresh_from_db()
        self.assertIsNone(child.parent)

    def test_different_tenants_same_slug(self):
        other_tenant = Tenant.objects.create(name="Other Tenant")
        Group.objects.create(
            tenant=self.tenant,
            name="Enterprise",
            slug="enterprise",
        )
        # Same slug on different tenant should succeed
        group = Group.objects.create(
            tenant=other_tenant,
            name="Enterprise",
            slug="enterprise",
        )
        self.assertEqual(group.tenant, other_tenant)
