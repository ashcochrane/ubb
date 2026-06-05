import pytest
from django.core.exceptions import ValidationError

from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestTenantBillingMode:
    def test_default_is_meter_only(self):
        t = Tenant.objects.create(name="T", products=["metering"])
        assert t.billing_mode == "meter_only"

    def test_prepaid_requires_billing_product(self):
        t = Tenant(name="T", products=["metering"], billing_mode="prepaid")
        with pytest.raises(ValidationError, match="billing"):
            t.full_clean(exclude=["branding_config", "metadata"])

    def test_postpaid_requires_billing_product(self):
        t = Tenant(name="T", products=["metering"], billing_mode="postpaid")
        with pytest.raises(ValidationError, match="billing"):
            t.full_clean(exclude=["branding_config", "metadata"])

    def test_prepaid_with_billing_product_valid(self):
        t = Tenant(name="T", products=["metering", "billing"], billing_mode="prepaid")
        t.full_clean(exclude=["branding_config", "metadata"])  # no raise

    def test_meter_only_with_billing_product_allowed(self):
        t = Tenant(name="T", products=["metering", "billing"], billing_mode="meter_only")
        t.full_clean(exclude=["branding_config", "metadata"])  # no raise
