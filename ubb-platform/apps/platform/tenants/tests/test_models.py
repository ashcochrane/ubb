from django.test import TestCase

from apps.platform.tenants.models import Tenant, TenantApiKey


class TenantModelTest(TestCase):
    def test_create_tenant(self):
        tenant = Tenant.objects.create(
            name="LocalScouta",
            stripe_connected_account_id="acct_test123",
            platform_fee_percentage=1.0,
        )
        self.assertEqual(tenant.name, "LocalScouta")
        self.assertTrue(tenant.is_active)

    def test_create_api_key(self):
        tenant = Tenant.objects.create(name="Test App")
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="production")
        self.assertTrue(raw_key.startswith("ubb_live_"))
        self.assertTrue(key_obj.key_hash)
        self.assertNotEqual(key_obj.key_hash, raw_key)

    def test_verify_api_key(self):
        tenant = Tenant.objects.create(name="Test App")
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        found = TenantApiKey.verify_key(raw_key)
        self.assertEqual(found.tenant_id, tenant.id)

    def test_revoked_key_fails_verification(self):
        tenant = Tenant.objects.create(name="Test App")
        key_obj, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        key_obj.is_active = False
        key_obj.save()
        result = TenantApiKey.verify_key(raw_key)
        self.assertIsNone(result)


class TenantProductsFieldTest(TestCase):
    def test_products_default_is_empty_list(self):
        tenant = Tenant.objects.create(name="Default Products")
        tenant.refresh_from_db()
        self.assertEqual(tenant.products, [])

    def test_products_single_product(self):
        tenant = Tenant.objects.create(name="Metering Only", products=["metering"])
        tenant.refresh_from_db()
        self.assertEqual(tenant.products, ["metering"])

    def test_products_multiple_products(self):
        tenant = Tenant.objects.create(
            name="Full Suite", products=["metering", "billing"]
        )
        tenant.refresh_from_db()
        # Products are sorted alphabetically on save
        self.assertEqual(tenant.products, ["billing", "metering"])
