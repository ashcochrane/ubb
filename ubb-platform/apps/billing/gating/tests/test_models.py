import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestBudgetConfig:
    def test_defaults(self):
        from apps.billing.gating.models import BudgetConfig
        t = Tenant.objects.create(name="T")
        cfg = BudgetConfig.objects.create(tenant=t, cap_micros=1_000_000_000)
        assert cfg.customer is None
        assert cfg.enforce_mode == "advisory"
        assert cfg.hard_stop_pct == 100
        assert cfg.alert_levels == [50, 80, 100, 110]
        assert cfg.fail_closed is False

    def test_tenant_default_and_customer_override_coexist(self):
        from apps.billing.gating.models import BudgetConfig
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        BudgetConfig.objects.create(tenant=t, customer=None, cap_micros=1_000)
        BudgetConfig.objects.create(tenant=t, customer=c, cap_micros=2_000)
        assert BudgetConfig.objects.filter(tenant=t).count() == 2

    def test_risk_config_fail_closed_default(self):
        from apps.billing.gating.models import RiskConfig
        t = Tenant.objects.create(name="T")
        rc = RiskConfig.objects.create(tenant=t)
        assert rc.gate_fail_closed is False
