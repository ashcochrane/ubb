import pytest
from django.core.exceptions import ValidationError

from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestTenantProductsValidation:
    def test_valid_products(self):
        tenant = Tenant(name="Test", products=["metering", "billing"])
        tenant.full_clean(exclude=["branding_config", "metadata"])  # Should not raise

    def test_metering_must_be_present(self):
        tenant = Tenant(name="Test", products=["billing"])
        with pytest.raises(ValidationError, match="metering"):
            tenant.full_clean(exclude=["branding_config", "metadata"])

    def test_unknown_product_rejected(self):
        tenant = Tenant(name="Test", products=["metering", "unknown_product"])
        with pytest.raises(ValidationError, match="unknown_product"):
            tenant.full_clean(exclude=["branding_config", "metadata"])

    def test_empty_products_rejected(self):
        tenant = Tenant(name="Test", products=[])
        with pytest.raises(ValidationError, match="metering"):
            tenant.full_clean(exclude=["branding_config", "metadata"])

    def test_products_sorted_and_deduplicated_on_save(self):
        tenant = Tenant.objects.create(
            name="Test",
            products=["billing", "metering", "billing", "metering"],
        )
        assert tenant.products == ["billing", "metering"]

    def test_valid_product_names(self):
        """All known product names pass validation."""
        tenant = Tenant(
            name="Test",
            products=["metering", "billing", "subscriptions", "referrals"],
        )
        tenant.full_clean(exclude=["branding_config", "metadata"])  # Should not raise
