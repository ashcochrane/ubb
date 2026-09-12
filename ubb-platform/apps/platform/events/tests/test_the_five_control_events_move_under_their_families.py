"""Migration `0009` carries the five control events under their families, and
the catalogue holds every name by reference (#464, slice 6 §16).

Two tables, one 1:1 map, one real reverse — `0007`'s shape, on the five names
`0007` deliberately left alone: the customer stop pair, the soft-floor pair
and the pool's threshold event. `TenantWebhookConfig.event_types` is a stored
`JSONField` and `is_valid_event_selector` only runs at config-create time, so a
row written before the rename would go on existing, pass every validation it
will ever face again, and match nothing (#75). That is why the first case here
is about the DELIVERY PATH and not only about the column, and why its negative
control runs the same fan-out over an unmigrated row.

⚠ NOTHING HERE SPELLS A RETIRED EVENT NAME. All five leave the catalogue in
the commit that adds this module and their ledger entries go with them, after
which any living file naming one fails the sweep outright with no entry left
to widen. Every retired name below is read off `MIGRATION.REVERSE` through the
payload class's own constant — `MIGRATION.REVERSE[StopFired.EVENT_TYPE]` — which
is also the better assertion: it holds the stored data to the map that moved it
rather than to a literal that would agree with both until one moved (#457's
rule for a module written after a rename).

⚠ WHAT THESE CASES DO NOT COVER, said rather than left to be discovered: they
call the migration's two functions with the live app registry, exactly as
`0007`'s and `0008`'s tests do, so nothing here drives `0009` through the
migration RUNNER. `0009` changes no schema and touches no column, so the live
registry IS the state it would be handed; `makemigrations --check --dry-run`
covers the other half.
"""
from unittest.mock import patch

import pytest
from django.apps import apps as global_apps
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import (
    CustomerSpendPoolThresholdReached, SoftFloorCleared, SoftFloorCrossed,
    StopCleared, StopFired, UsageRecorded, payload_schema_classes,
)
from apps.platform.events.tests._helpers import (
    THE_CATALOGUE_RENAME as MIGRATION, as_it_was_spelled,
    stub_webhook_client as _stub_client,
)
from apps.platform.events.webhook_models import (
    TenantWebhookConfig, WebhookDeliveryAttempt,
)
from apps.platform.events.webhooks import deliver_webhook
from apps.platform.tenants.models import Tenant
from core.vocabulary import WEBHOOK_EVENT_TYPE_VALUES

#: The five, by the class that publishes each successor.
THE_FIVE = (StopFired, StopCleared, SoftFloorCrossed, SoftFloorCleared,
            CustomerSpendPoolThresholdReached)


def retired(cls):
    """The name ``cls`` published before #464, read off the map's reverse —
    and it must differ from today's, or the case is planting the successor."""
    old = as_it_was_spelled(cls.EVENT_TYPE)
    assert old != cls.EVENT_TYPE, cls
    return old


# ---------------------------------------------------------------------------
# 1. The map, held against the live catalogue
# ---------------------------------------------------------------------------

def test_the_migration_renames_exactly_the_five_control_events():
    assert set(MIGRATION.RENAMES.values()) == {cls.EVENT_TYPE for cls in THE_FIVE}
    assert len(MIGRATION.RENAMES) == 5


def test_every_old_name_has_left_the_catalogue():
    """A key still published would mean the rename did not happen in code, and
    the migration would be rewriting live subscriptions onto nothing."""
    still_there = sorted(set(MIGRATION.RENAMES) & set(WEBHOOK_EVENT_TYPES))
    assert not still_there, (
        f"{still_there} are still published, so migrating a subscription away "
        f"from them would break it rather than repair it")


def test_every_new_name_is_a_published_event():
    missing = sorted(set(MIGRATION.RENAMES.values()) - set(WEBHOOK_EVENT_TYPES))
    assert not missing, f"{missing} are not events UBB publishes"


def test_the_map_is_one_to_one_so_the_reverse_is_exact():
    assert len(set(MIGRATION.RENAMES.values())) == len(MIGRATION.RENAMES)
    assert {MIGRATION.REVERSE[new]: new for new in MIGRATION.REVERSE} == \
        MIGRATION.RENAMES


def test_the_catalogue_publishes_exactly_the_registrys_set():
    """The assertion the fifth rename made true, in place of the tripwire that
    waited for it (#222's `DEFERRED` and its test, deleted in #464).

    Every payload class takes its name from `core.vocabulary`, so the
    catalogue cannot publish a name the registry does not declare — and this
    holds the other direction too: a declared name nothing publishes would be
    a contract promise about an event that never fires. The registry-side
    twin, with the retired aliases in hand, is
    `tests/contracts/test_webhook_catalogue.py`.
    """
    assert set(WEBHOOK_EVENT_TYPES) == set(WEBHOOK_EVENT_TYPE_VALUES)
    assert len(WEBHOOK_EVENT_TYPES) == len(payload_schema_classes())


# ---------------------------------------------------------------------------
# 2. Subscriptions — the delivery path is the acceptance criterion
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSubscriptionsSurviveTheRename:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Acme")
        self.config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/hook",
            secret="test-secret", event_types=[retired(StopFired)])
        self.event = OutboxEvent.objects.create(
            event_type=StopFired.EVENT_TYPE,
            payload={"tenant_id": str(self.tenant.id), "owner_id": "o1"},
            tenant_id=str(self.tenant.id))

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_a_pre_existing_subscription_still_matches_after_the_rename(
            self, mock_client_class, _mock_validate):
        _stub_client(mock_client_class)

        MIGRATION.move_under_the_families(global_apps, None)

        self.config.refresh_from_db()
        assert self.config.event_types == [StopFired.EVENT_TYPE]
        deliver_webhook(self.event)
        assert WebhookDeliveryAttempt.objects.filter(success=True).count() == 1

    @patch("apps.platform.events.webhooks.validate_webhook_url")
    @patch("apps.platform.events.webhooks.httpx.Client")
    def test_negative_control_an_unmigrated_row_silently_matches_nothing(
            self, mock_client_class, _mock_validate):
        """The only difference from the case above is whether the migration
        ran, which is what makes that case a proof rather than a coincidence."""
        _stub_client(mock_client_class)

        deliver_webhook(self.event)

        assert WebhookDeliveryAttempt.objects.count() == 0

    def test_each_of_the_five_comes_out_holding_its_successor_in_place(self):
        """Element-wise, order preserved: a mixed subscription keeps its
        untouched entries where they were, and every retired entry is replaced
        at its own position."""
        before = [UsageRecorded.EVENT_TYPE] + [retired(cls) for cls in THE_FIVE]
        config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/mixed",
            secret="s", event_types=list(before))

        MIGRATION.move_under_the_families(global_apps, None)

        config.refresh_from_db()
        assert config.event_types == (
            [UsageRecorded.EVENT_TYPE] + [cls.EVENT_TYPE for cls in THE_FIVE])

    def test_a_successor_already_held_is_not_duplicated(self):
        """A list holding both spellings of one event comes out holding the
        successor once, at the position of whichever came first."""
        config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/both",
            secret="s", event_types=[
                StopCleared.EVENT_TYPE, retired(StopCleared),
                UsageRecorded.EVENT_TYPE])

        MIGRATION.move_under_the_families(global_apps, None)

        config.refresh_from_db()
        assert config.event_types == [
            StopCleared.EVENT_TYPE, UsageRecorded.EVENT_TYPE]

    def test_the_wildcard_and_the_empty_subscription_are_untouched(self):
        every = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/all",
            secret="s", event_types=["*"])
        none = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/none",
            secret="s", event_types=[])

        MIGRATION.move_under_the_families(global_apps, None)

        every.refresh_from_db()
        none.refresh_from_db()
        assert every.event_types == ["*"]
        assert none.event_types == []

    def test_the_rename_reverses_losslessly(self):
        """The map is 1:1 and no old name survives in the catalogue, so a
        rollback restores exactly the subscription it found."""
        before = [retired(SoftFloorCrossed), UsageRecorded.EVENT_TYPE,
                  retired(CustomerSpendPoolThresholdReached)]
        config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/round-trip",
            secret="s", event_types=list(before))

        MIGRATION.move_under_the_families(global_apps, None)
        config.refresh_from_db()
        assert config.event_types == [
            SoftFloorCrossed.EVENT_TYPE, UsageRecorded.EVENT_TYPE,
            CustomerSpendPoolThresholdReached.EVENT_TYPE]

        MIGRATION.restore_the_mechanism_names(global_apps, None)
        config.refresh_from_db()
        assert config.event_types == before

    def test_a_subscription_needing_no_change_is_not_written_at_all(self):
        """Counted as UPDATE statements against the config table, because a
        queryset `.update()` does not touch `updated_at`; the outbox sweep's
        own statements are excluded by table name."""
        self.config.delete()
        TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/clean",
            secret="s", event_types=[UsageRecorded.EVENT_TYPE, "*"])
        table = TenantWebhookConfig._meta.db_table

        with CaptureQueriesContext(connection) as queries:
            MIGRATION.move_under_the_families(global_apps, None)

        writes = [q["sql"] for q in queries.captured_queries
                  if q["sql"].lstrip().upper().startswith("UPDATE")
                  and table in q["sql"]]
        assert not writes, writes


# ---------------------------------------------------------------------------
# 3. The outbox — renamed by name; the attempts and the body left alone
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestQueuedEventsSurviveTheRename:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Acme")
        self.payload = {"tenant_id": str(self.tenant.id), "owner_id": "o1",
                        "episode_seq": 3}
        self.event = OutboxEvent.objects.create(
            event_type=retired(StopFired), payload=dict(self.payload),
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
            secret="test-secret", event_types=[retired(StopFired)])

        MIGRATION.move_under_the_families(global_apps, None)

        self.event.refresh_from_db()
        assert self.event.event_type == StopFired.EVENT_TYPE
        deliver_webhook(self.event)
        assert WebhookDeliveryAttempt.objects.filter(success=True).count() == 1

    def test_every_row_bearing_a_retired_name_is_renamed_and_nothing_else_is(self):
        rows = {cls: OutboxEvent.objects.create(
                    event_type=retired(cls), payload={}, tenant_id=str(self.tenant.id))
                for cls in THE_FIVE}
        other = OutboxEvent.objects.create(
            event_type=UsageRecorded.EVENT_TYPE, payload={},
            tenant_id=str(self.tenant.id))

        MIGRATION.move_under_the_families(global_apps, None)

        for cls, row in rows.items():
            row.refresh_from_db()
            assert row.event_type == cls.EVENT_TYPE
        other.refresh_from_db()
        assert other.event_type == UsageRecorded.EVENT_TYPE

    def test_a_recorded_body_keeps_its_spelling(self):
        """Only the NAME is rewritten — it is what a subscription is matched
        against and what the registry dispatches on. The body is the record of
        a past event and is delivered verbatim either way."""
        MIGRATION.move_under_the_families(global_apps, None)

        self.event.refresh_from_db()
        assert self.event.payload == self.payload

    def test_a_delivery_attempt_is_untouched(self):
        """The attempts are the history of what a subscriber actually
        received; the queue is the work list. Only the work list moves."""
        config = TenantWebhookConfig.objects.create(
            tenant=self.tenant, url="https://example.com/hook",
            secret="s", event_types=["*"])
        attempt = WebhookDeliveryAttempt.objects.create(
            webhook_config=config, outbox_event=self.event,
            status_code=500, success=False, error_message="boom")
        before = (attempt.webhook_config_id, attempt.outbox_event_id,
                  attempt.status_code, attempt.success, attempt.error_message)

        MIGRATION.move_under_the_families(global_apps, None)

        attempt.refresh_from_db()
        assert (attempt.webhook_config_id, attempt.outbox_event_id,
                attempt.status_code, attempt.success,
                attempt.error_message) == before
        assert WebhookDeliveryAttempt.objects.count() == 1

    def test_the_outbox_reverse_restores_the_retired_names(self):
        MIGRATION.move_under_the_families(global_apps, None)
        MIGRATION.restore_the_mechanism_names(global_apps, None)

        self.event.refresh_from_db()
        assert self.event.event_type == retired(StopFired)
