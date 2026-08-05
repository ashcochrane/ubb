"""The thirteen renamed events, and the subscriptions that survive them (#222).

`TenantWebhookConfig.event_types` is a stored `JSONField` holding event names
verbatim, and `is_valid_event_selector` only runs at config-create time. So a
row written before the rename would go on existing, pass every validation it
will ever face again, and match nothing — the exact defect `events/catalog.py`
records in its own docstring, which hid `customer.deleted` from subscribers
while the delivery path emitted it (#75).

That is why these tests are about the DELIVERY PATH and not only about the
column. `test_a_pre_existing_subscription_still_matches_after_the_rename` runs
the real fan-out; its negative control runs the same fan-out over an unmigrated
row and proves it silently matches nothing, so the migration is what makes the
positive case pass rather than something else in the setup.
"""
import importlib
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps as global_apps
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES
from apps.platform.events.models import OutboxEvent
from apps.platform.events.webhook_models import (
    TenantWebhookConfig, WebhookDeliveryAttempt,
)
from apps.platform.events.webhooks import deliver_webhook
from apps.platform.tenants.models import Tenant

MIGRATION = importlib.import_module(
    "apps.platform.events.migrations.0007_rename_thirteen_webhook_event_types")

#: The seven G8 debts #222 deliberately leaves in the migration ledger. Each is
#: blocked on work that is not a rename: slice 5 SPLITS the two Task events into
#: `killed` and `expired` (#140 §4.3), and slice 6 rewrites the five control
#: emitters under #150's four families. A migration that renamed them now would
#: be guessing at a target state that does not exist yet.
#:
#: A second encoding of the ledger's remaining entries, and it does not need an
#: agreement test to keep it honest: the day slice 5 pays one of these, the name
#: leaves the catalogue and `test_the_deferred_seven_are_not_renamed` goes red
#: naming it. The check that DOES need a separate home is the one this list
#: cannot make — that `RENAMES` names only retired terms — because the registry
#: is YAML and this suite has no PyYAML. It lives in
#: tests/contracts/test_webhook_rename_migration.py.
DEFERRED = (
    "task.limit_exceeded", "subtask.limit_exceeded", "stop.fired",
    "stop.cleared", "soft_floor.crossed", "soft_floor.cleared",
    "budget.threshold_reached",
)


def _stub_client(mock_client_class):
    """Wire the patched `httpx.Client` to answer 200 to any POST."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.post.return_value = MagicMock(status_code=200, text="OK")
    mock_client_class.return_value = client
    return client


# ---------------------------------------------------------------------------
# 1. The map itself, held against the live catalogue
# ---------------------------------------------------------------------------

def test_the_migration_renames_exactly_thirteen_events():
    assert len(MIGRATION.RENAMES) == 13


def test_every_old_name_has_left_the_catalogue():
    """A key that is still published means the rename did not happen in code,
    and the migration would be rewriting live subscriptions onto nothing."""
    published = set(WEBHOOK_EVENT_TYPES)
    still_there = sorted(set(MIGRATION.RENAMES) & published)
    assert not still_there, (
        f"{still_there} are still published, so migrating a subscription away "
        f"from them would break it rather than repair it")


def test_every_new_name_is_a_published_event():
    """The other direction: a target the catalogue does not publish would leave
    the migrated subscription matching nothing, which is the defect itself."""
    published = set(WEBHOOK_EVENT_TYPES)
    missing = sorted(set(MIGRATION.RENAMES.values()) - published)
    assert not missing, f"{missing} are not events UBB publishes"


def test_the_deferred_seven_are_not_renamed():
    """#222 renames only what depends on nothing. The Task pair becomes TWO
    events in slice 5 and the five control events are rewritten in slice 6, so
    a 1:1 rename here would encode a target state nobody has agreed."""
    for name in DEFERRED:
        assert name not in MIGRATION.RENAMES, name
        assert name in WEBHOOK_EVENT_TYPES, (
            f"{name} left the catalogue, so its ledger entry is now stale")


# ---------------------------------------------------------------------------
# 2. The delivery path — the acceptance criterion
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSubscriptionsSurviveTheRename:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Acme")
        self.config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/hook",
            secret="test-secret", event_types=["billing.balance_low"])
        self.event = OutboxEvent.objects.create(
            event_type="wallet.balance_low",
            payload={"tenant_id": str(self.tenant.id), "customer_id": "c1"},
            tenant_id=str(self.tenant.id))

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_a_pre_existing_subscription_still_matches_after_the_rename(
            self, mock_client_class, _mock_validate):
        _stub_client(mock_client_class)

        MIGRATION.rename_subscriptions(global_apps, None)

        self.config.refresh_from_db()
        assert self.config.event_types == ["wallet.balance_low"]
        deliver_webhook(self.event)
        assert WebhookDeliveryAttempt.objects.filter(success=True).count() == 1

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_negative_control_an_unmigrated_row_silently_matches_nothing(
            self, mock_client_class, _mock_validate):
        """Without the migration the subscriber goes quiet and nothing says so.

        This is what makes the test above a proof rather than a coincidence: the
        only difference between the two is whether the migration ran.
        """
        _stub_client(mock_client_class)

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 0

    def test_other_selectors_keep_their_place_in_the_list(self):
        """Element-wise, order preserved: a mixed subscription is common and a
        rewrite that reordered or dropped its untouched entries would be a
        second, silent change to a public contract."""
        config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/mixed",
            secret="s", event_types=[
                "usage.recorded", "margin.provider_cost_spike",
                "task.limit_exceeded", "billing.credit_grant_expired"])

        MIGRATION.rename_subscriptions(global_apps, None)

        config.refresh_from_db()
        assert config.event_types == [
            "usage.recorded", "provider.cost_spike",
            "task.limit_exceeded", "credit_grant.expired"]

    def test_the_wildcard_and_the_empty_subscription_are_untouched(self):
        """`["*"]` is all events and `[]` is none (0003's explicit opt-in). Both
        are selectors rather than names, so neither has anything to rename."""
        every = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/all",
            secret="s", event_types=["*"])
        none = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/none",
            secret="s", event_types=[])

        MIGRATION.rename_subscriptions(global_apps, None)

        every.refresh_from_db()
        none.refresh_from_db()
        assert every.event_types == ["*"]
        assert none.event_types == []

    def test_the_rename_reverses_losslessly(self):
        """The map is 1:1 and no old name survives in the catalogue, so a
        rollback restores exactly the subscription it found — which is what lets
        this ship as `RunPython(forward, backward)` rather than with a noop
        reverse that would strand every subscriber on a name the reverted code
        no longer publishes.
        """
        before = ["billing.balance_low", "usage.recorded",
                  "auto_topup.requires_action"]
        config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/round-trip",
            secret="s", event_types=list(before))

        MIGRATION.rename_subscriptions(global_apps, None)
        config.refresh_from_db()
        assert config.event_types == ["wallet.balance_low", "usage.recorded",
                                      "auto_top_up.requires_action"]

        MIGRATION.restore_subscriptions(global_apps, None)
        config.refresh_from_db()
        assert config.event_types == before

    def test_a_subscription_needing_no_change_is_not_written_at_all(self):
        """The migration writes the subscriptions carrying a retired name, and
        no others — a rewrite of every webhook config in the table would churn
        rows whose public contract did not change.

        Counted as UPDATE statements against the config table rather than by
        comparing `updated_at`, which a queryset `.update()` does not touch — so
        a timestamp assertion would pass over exactly the rewrite being ruled
        out. The outbox sweep's own statements are excluded by the table name:
        it issues one per renamed type unconditionally, which for a one-shot
        migration is cheaper than thirteen existence checks.
        """
        self.config.delete()
        TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/clean",
            secret="s", event_types=["usage.recorded", "*"])
        table = TenantWebhookConfig._meta.db_table

        with CaptureQueriesContext(connection) as queries:
            MIGRATION.rename_subscriptions(global_apps, None)

        writes = [q["sql"] for q in queries.captured_queries
                  if q["sql"].lstrip().upper().startswith("UPDATE")
                  and table in q["sql"]]
        assert not writes, writes


@pytest.mark.django_db
class TestQueuedEventsSurviveTheRename:
    """The outbox is a work queue and a dedup index keyed on `event_type`, not
    the record of what a subscriber received — that is `WebhookDeliveryAttempt`,
    which stores no name and so has nothing to migrate. Three live reads key on
    the outbox name (the delivery match, the handler registry's dispatch, and
    `MarginService`'s spike dedup), so the queue moves with the catalogue or
    they quietly stop agreeing with it."""

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Acme")
        self.event = OutboxEvent.objects.create(
            event_type="billing.balance_low",
            payload={"tenant_id": str(self.tenant.id), "customer_id": "c1"},
            tenant_id=str(self.tenant.id))

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_an_event_queued_before_the_rename_still_reaches_its_subscriber(
            self, mock_client_class, _mock_validate):
        """Both sides move together, so an in-flight delivery is not stranded
        between a migrated subscription and an unmigrated event."""
        _stub_client(mock_client_class)
        TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/hook",
            secret="test-secret", event_types=["billing.balance_low"])

        MIGRATION.rename_subscriptions(global_apps, None)

        self.event.refresh_from_db()
        assert self.event.event_type == "wallet.balance_low"
        deliver_webhook(self.event)
        assert WebhookDeliveryAttempt.objects.filter(success=True).count() == 1

    def test_a_queued_event_the_rename_does_not_touch_keeps_its_name(self):
        """`past_limit.py` reads the outbox for `stop.fired` and its siblings —
        five of the seven debts this ticket leaves alone — so a sweep that
        widened past the thirteen would break a shipped report."""
        other = OutboxEvent.objects.create(
            event_type="stop.fired",
            payload={"tenant_id": str(self.tenant.id), "owner_id": "o1"},
            tenant_id=str(self.tenant.id))

        MIGRATION.rename_subscriptions(global_apps, None)

        other.refresh_from_db()
        assert other.event_type == "stop.fired"
