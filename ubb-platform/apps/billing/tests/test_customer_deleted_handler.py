import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet
from apps.billing.topups.models import AutoTopUpConfig
from apps.billing.handlers import handle_customer_deleted_billing


@pytest.mark.django_db
class TestHandleCustomerDeletedBilling:
    def _make_tenant(self, **kwargs):
        defaults = {
            "name": "Test Tenant",
            "products": ["metering", "billing"],
        }
        defaults.update(kwargs)
        return Tenant.objects.create(**defaults)

    def test_soft_deletes_wallet(self):
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        wallet = customer.wallet  # auto-created by Customer.save()

        handle_customer_deleted_billing("evt-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
        })

        wallet.refresh_from_db()
        assert wallet.is_deleted is True

    def test_soft_deletes_auto_topup_config(self):
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        AutoTopUpConfig.objects.create(
            customer=customer,
            trigger_threshold_micros=1000000,
            top_up_amount_micros=5000000,
        )

        handle_customer_deleted_billing("evt-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
        })

        config = AutoTopUpConfig.all_objects.get(customer=customer)
        assert config.is_deleted is True

    def test_handles_no_wallet(self):
        """No error if wallet doesn't exist."""
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        # Delete the auto-created wallet to simulate no wallet
        Wallet.objects.filter(customer=customer).delete()

        # Should not raise
        handle_customer_deleted_billing("evt-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
        })

    def test_handles_no_auto_topup_config(self):
        """No error if AutoTopUpConfig doesn't exist."""
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")

        # Should not raise (no AutoTopUpConfig exists)
        handle_customer_deleted_billing("evt-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
        })

    def test_idempotent(self):
        """Running twice doesn't error."""
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
        }
        handle_customer_deleted_billing("evt-1", payload)
        # Second call should not raise
        handle_customer_deleted_billing("evt-1", payload)
