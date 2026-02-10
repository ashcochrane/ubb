import pytest
from django.db import IntegrityError, transaction

from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.models import ProductFeeConfig


@pytest.mark.django_db
class TestProductFeeConfig:
    def test_create_percentage_fee(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        config = ProductFeeConfig.objects.create(
            tenant=tenant,
            product="billing",
            fee_type="percentage",
            config={"percentage": "1.00"},
        )
        assert config.product == "billing"
        assert config.fee_type == "percentage"
        assert config.config["percentage"] == "1.00"

    def test_create_flat_monthly_fee(self):
        tenant = Tenant.objects.create(name="Test", products=["metering"])
        config = ProductFeeConfig.objects.create(
            tenant=tenant,
            product="metering",
            fee_type="flat_monthly",
            config={"amount_micros": 49_000_000},
        )
        assert config.fee_type == "flat_monthly"

    def test_unique_per_tenant_product(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        ProductFeeConfig.objects.create(
            tenant=tenant,
            product="billing",
            fee_type="percentage",
            config={"percentage": "1.00"},
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProductFeeConfig.objects.create(
                    tenant=tenant,
                    product="billing",
                    fee_type="flat_monthly",
                    config={"amount_micros": 10_000_000},
                )

    def test_different_tenants_same_product_ok(self):
        t1 = Tenant.objects.create(name="T1", products=["metering", "billing"])
        t2 = Tenant.objects.create(name="T2", products=["metering", "billing"])
        ProductFeeConfig.objects.create(tenant=t1, product="billing", fee_type="percentage", config={})
        ProductFeeConfig.objects.create(tenant=t2, product="billing", fee_type="percentage", config={})
