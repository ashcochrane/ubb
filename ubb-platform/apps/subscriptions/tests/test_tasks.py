import pytest
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestCalculateAllEconomicsTask:
    def test_runs_for_subscriptions_tenants_only(self):
        from apps.subscriptions.tasks import calculate_all_economics_task

        Tenant.objects.create(name="metering-only", products=["metering"])
        sub_tenant = Tenant.objects.create(
            name="sub-tenant", products=["metering", "subscriptions"],
        )

        with patch(
            "apps.subscriptions.tasks.EconomicsService.calculate_all_economics"
        ) as mock_calc:
            mock_calc.return_value = []
            calculate_all_economics_task()

            assert mock_calc.call_count == 1
            assert mock_calc.call_args[0][0] == sub_tenant.id
