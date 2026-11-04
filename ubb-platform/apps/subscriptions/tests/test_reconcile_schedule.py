from unittest.mock import patch

import pytest
from django.conf import settings

from apps.platform.tenants.models import Tenant


class TestReconcilerIsScheduled:
    def test_mirror_reconciler_is_in_the_beat_schedule(self):
        """The Stripe subscription mirror is a pure cache of another system's
        state. Every other cache in this codebase has a scheduled reconciler;
        this one was dead code until 2026-07-27."""
        entry = settings.CELERY_BEAT_SCHEDULE["reconcile-subscription-mirrors"]
        assert entry["task"] == (
            "apps.subscriptions.tasks.reconcile_subscription_mirrors")


@pytest.mark.django_db
class TestReconcilerFansOut:
    def test_only_tenants_with_a_connected_account_are_synced(self):
        from apps.subscriptions.tasks import reconcile_subscription_mirrors

        Tenant.objects.create(name="connected", products=["metering", "billing"],
                              stripe_connected_account_id="acct_1")
        Tenant.objects.create(name="unconnected", products=["metering", "billing"])
        target = "apps.subscriptions.tasks.sync_tenant_subscriptions_task.delay"
        with patch(target) as delay:
            reconcile_subscription_mirrors()
        assert delay.call_count == 1
