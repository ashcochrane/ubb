import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import TENANT_PRODUCT_METERING, TENANT_PRODUCT_VALUES


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
    def test_products_default_is_metering(self):
        tenant = Tenant.objects.create(name="Default Products")
        tenant.refresh_from_db()
        self.assertEqual(tenant.products, ["metering"])

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


@pytest.mark.django_db
class TestTheAcceptedProductsAreTheRegistrys:
    """The model keeps no product vocabulary of its own (#240).

    It used to: a literal set sat beside these rules, so a product retired in
    `domain-vocabulary/` stayed configurable here until somebody remembered
    this file. What the class pins is the consequence — every value the
    registry declares configures, and anything else is refused — so the
    accepted set moves when the registry moves and at no other time.

    That the set arrives BY IMPORT rather than by agreeing with the registry
    coincidentally is not asserted here and cannot be: it is G2's question, and
    `tests/contracts/test_consumer_census.py` answers it off the import graph
    for the same reason #191 decision 3 refuses a literal scan.

    Every refusal below goes through `save`, and asserts that the complaint
    names `products`. The predecessor called `full_clean()` on an unsaved
    `Tenant`, where `branding_config` and `metadata` are blank and raise on
    their own — so it would have passed with the products rule deleted.
    """

    def test_every_declared_product_configures(self):
        for product in sorted(TENANT_PRODUCT_VALUES):
            tenant = Tenant.objects.create(
                name=f"Declared {product}",
                products=sorted({TENANT_PRODUCT_METERING, product}))
            tenant.refresh_from_db()
            assert product in tenant.products

    def test_a_product_the_registry_does_not_declare_is_refused(self):
        with pytest.raises(ValidationError) as refusal:
            Tenant.objects.create(
                name="T", products=[TENANT_PRODUCT_METERING, "clairvoyance"])
        assert "products" in refusal.value.message_dict

    def test_the_default_is_itself_a_declared_product(self):
        """Defaulting and validation read the same set, so a tenant created
        with no products can never be one the next `save` refuses."""
        tenant = Tenant.objects.create(name="Default Products")
        assert tenant.products
        assert set(tenant.products) <= TENANT_PRODUCT_VALUES

    def test_subscriptions_is_not_one_of_them(self):
        assert "subscriptions" not in TENANT_PRODUCT_VALUES

    def test_configuring_subscriptions_is_rejected(self):
        with pytest.raises(ValidationError) as refusal:
            Tenant.objects.create(name="T",
                                  products=["metering", "subscriptions"])
        assert "products" in refusal.value.message_dict
