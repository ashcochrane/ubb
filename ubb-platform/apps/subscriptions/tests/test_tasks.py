import pytest
from unittest.mock import patch
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestCalculateAllEconomicsTask:
    def test_runs_for_metering_tenants(self):
        from apps.subscriptions.tasks import calculate_all_economics_task
        t = Tenant.objects.create(name="metering-only", products=["metering"])
        with patch("apps.subscriptions.tasks.MarginService.snapshot_all") as mock_calc:
            mock_calc.return_value = []
            calculate_all_economics_task()
            assert mock_calc.call_count == 1
            assert mock_calc.call_args[0][0] == t.id
