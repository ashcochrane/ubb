"""Tests for the 0003 data migration that preserves existing webhook configs.

Under the old semantics an empty event_types list meant "deliver all events".
The new semantics make [] mean "deliver nothing", so existing empty configs
must be backfilled to ["*"] or they would silently stop delivering.
"""
import importlib

import pytest
from django.apps import apps as global_apps

from apps.platform.tenants.models import Tenant
from apps.platform.events.webhook_models import TenantWebhookConfig

MIGRATION = "apps.platform.events.migrations.0003_webhook_event_types_explicit_optin"


@pytest.mark.django_db
def test_backfill_empty_event_types_to_wildcard():
    mig = importlib.import_module(MIGRATION)
    tenant = Tenant.objects.create(name="mig", products=["metering"])
    empty = TenantWebhookConfig.objects.create(
        tenant=tenant, url="https://a.example.com/h", secret="x" * 32, event_types=[]
    )
    specific = TenantWebhookConfig.objects.create(
        tenant=tenant, url="https://b.example.com/h", secret="x" * 32,
        event_types=["usage.recorded"],
    )
    already_all = TenantWebhookConfig.objects.create(
        tenant=tenant, url="https://c.example.com/h", secret="x" * 32, event_types=["*"]
    )

    mig.backfill_empty_event_types(global_apps, None)

    empty.refresh_from_db()
    specific.refresh_from_db()
    already_all.refresh_from_db()
    assert empty.event_types == ["*"]                    # old "all" behavior preserved
    assert specific.event_types == ["usage.recorded"]    # specific lists untouched
    assert already_all.event_types == ["*"]              # already-wildcard untouched
