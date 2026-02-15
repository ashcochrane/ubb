import pytest

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestTopupModelsInBillingApp:
    def test_import_from_billing(self):
        from apps.billing.topups.models import AutoTopUpConfig, TopUpAttempt
        assert AutoTopUpConfig is not None
        assert TopUpAttempt is not None

    def test_create_auto_topup_config(self):
        from apps.billing.topups.models import AutoTopUpConfig

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        config = AutoTopUpConfig.objects.create(
            customer=customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000,
        )
        assert config.is_enabled
        assert config.trigger_threshold_micros == 5_000_000

    def test_create_topup_attempt(self):
        from apps.billing.topups.models import TopUpAttempt

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        attempt = TopUpAttempt.objects.create(
            customer=customer,
            amount_micros=10_000_000,
            trigger="manual",
        )
        assert attempt.status == "pending"
        assert attempt.trigger == "manual"
