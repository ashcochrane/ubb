"""Migration `0008` carries the stored rows onto the four terminal events.

Two tables, two different rules, because they answer two different questions
(#140 §4.3). A subscription is a standing request — the subscriber asked to
hear about work terminating, and one of the two successors delivers half of
that — so it FANS OUT to both. An outbox row is one past event about one unit
of work, so it ROUTES to exactly one, chosen by evidence the row already
carries.

⚠ NOTHING HERE SPELLS A RETIRED EVENT NAME, and that is not squeamishness.
Both names leave the catalogue in the commit that adds this module, and their
ledger entries go with them — after which any living file naming one fails the
sweep outright with no entry left to widen. Every name below is read off
`MIGRATION.SPLIT`, which is also the better assertion: it holds the stored data
to the map that moved it rather than to a literal that would agree with both
until one of them moved (#370's rule for a module written after a rename).

⚠ AND EVERY REASON IS ASSERTED BY CONSTANT IDENTITY. The routing rule turns on
values belonging to a vocabulary slice 6 owns, so a case naming one as a string
would be this module spelling another slice's word and would go stale silently
the day that slice renames it — which is precisely what happened to the silence
window's stop once already (#412), and is why `REAPER_REASONS` has three
members rather than two.
"""
import importlib

import pytest
from django.apps import apps as global_apps

from apps.platform.events.models import OutboxEvent
from apps.platform.events.catalog import WEBHOOK_EVENT_TYPES
from apps.platform.events.webhook_models import TenantWebhookConfig
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons

MIGRATION = importlib.import_module(
    "apps.platform.events.migrations."
    "0008_the_two_terminal_task_events_become_four")

#: The whole-unit pair and the contained-work pair, read off the map. Sorted so
#: `killed` comes before `expired` whichever order the map declares them in —
#: the map's own order is not significant and this module should not depend on
#: it.
(WHOLE_UNIT, CONTAINED_WORK) = sorted(MIGRATION.SPLIT)


def _successors(retired):
    """`(the spend stop, the expiry)` for a retired name, by what they mean.

    Derived from the catalogue rather than from the map's tuple order: the
    successors are told apart by the state each names, which is the whole
    subject of the split, so reading them positionally would make this module
    agree with a map that had them the wrong way round.
    """
    killed, = [n for n in MIGRATION.SPLIT[retired] if n.endswith(".killed")]
    expired, = [n for n in MIGRATION.SPLIT[retired] if n.endswith(".expired")]
    return killed, expired


# ---------------------------------------------------------------------------
# 1. The map, held against the live catalogue
# ---------------------------------------------------------------------------

def test_the_migration_splits_exactly_the_two_terminal_events():
    assert len(MIGRATION.SPLIT) == 2
    assert all(len(pair) == 2 for pair in MIGRATION.SPLIT.values())


def test_every_retired_name_has_left_the_catalogue():
    """A key still published would mean the split did not happen in code, and
    the migration would be rewriting live subscriptions onto nothing."""
    still_there = sorted(set(MIGRATION.SPLIT) & set(WEBHOOK_EVENT_TYPES))
    assert not still_there, (
        f"{still_there} are still published, so migrating a subscription away "
        f"from them would break it rather than repair it")


def test_every_successor_is_a_published_event():
    """The other direction: a target the catalogue does not publish would leave
    the migrated subscription matching nothing, which is the defect itself."""
    successors = {name for pair in MIGRATION.SPLIT.values() for name in pair}
    missing = sorted(successors - set(WEBHOOK_EVENT_TYPES))
    assert not missing, f"{missing} are not events UBB publishes"


def test_the_reaper_reasons_are_the_ones_the_expiry_paths_produce():
    """The migration cannot import `reasons` — a migration must keep working
    when the code has moved on — so this holds its second encoding to the
    first.

    ⚠ IT IS A SUPERSET BY EXACTLY ONE, and that one is the point. The silence
    window's stop was spelled `stale` until it was sourced from the registry
    (#412), and the rows written before that are exactly the rows this
    migration exists for — so the set has to name the older spelling too or a
    pre-#412 expiry is routed as a spend stop. That extra member is asserted to
    be the ONLY extra one, which is what stops the set drifting into a
    catch-all.
    """
    from_the_module = {reasons.SILENCE_WINDOW, reasons.STALE_MAX_AGE}
    assert from_the_module <= set(MIGRATION.REAPER_REASONS)
    superseded = set(MIGRATION.REAPER_REASONS) - from_the_module
    assert len(superseded) == 1, (
        f"{sorted(superseded)} are spellings no current constant carries; "
        f"exactly one — the pre-registry silence window — is expected")


def test_the_reverse_map_is_derived_from_the_forward_one():
    """Every successor collapses back onto exactly the name it came from.

    Asserted here rather than in the contract suite because `COLLAPSE` is a
    comprehension over `SPLIT` — which is what stops the two directions
    drifting — and that suite reads the migration with `ast` and never imports
    it. A missing successor here would strand a rolled-back subscription on a
    name the reverted code no longer publishes.
    """
    assert MIGRATION.COLLAPSE == {
        successor: (retired,)
        for retired, successors in MIGRATION.SPLIT.items()
        for successor in successors}


def test_no_reason_that_is_not_a_reaper_reason_is_named_as_one():
    """The negative half: every OTHER reason UBB produces must fall to the
    default, so a case that only checked membership above would miss a set that
    had quietly grown to include a ceiling."""
    not_an_expiry = {reasons.TASK_LIMIT, reasons.SUBTASK_LIMIT,
                     reasons.CUSTOMER_WIDE_STOP, reasons.PARENT_KILLED,
                     reasons.TASK_NOT_ACTIVE}
    overlap = not_an_expiry & set(MIGRATION.REAPER_REASONS)
    assert not overlap, (
        f"{sorted(overlap)} would route a stop UBB applied to the event that "
        f"says nobody ever told UBB how the work ended")


# ---------------------------------------------------------------------------
# 2. Subscriptions FAN OUT
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestASubscriptionFansOutToBoth:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Acme")

    def _config(self, event_types, url="https://example.com/hook"):
        return TenantWebhookConfig.objects.create(
            tenant=self.tenant, url=url, secret="s",
            event_types=list(event_types))

    def test_the_retired_name_is_replaced_by_both_successors_in_place(self):
        """The acceptance criterion, on real stored data: a subscriber who
        asked to hear about work terminating still hears about all of it, and
        the rest of their subscription is untouched.

        Order matters and is asserted whole: a subscription is a public
        contract, so reordering or dropping its other entries would be a
        second, silent change to one.
        """
        killed, expired = _successors(WHOLE_UNIT)
        config = self._config(
            ["usage.recorded", WHOLE_UNIT, "customer.suspended"])

        MIGRATION.split_the_terminal_events(global_apps, None)

        config.refresh_from_db()
        assert config.event_types == [
            "usage.recorded", killed, expired, "customer.suspended"]

    def test_a_successor_already_subscribed_to_is_not_duplicated(self):
        """A subscriber who had already asked for one of the states by name —
        possible the moment the events exist — must not end up holding it
        twice. Delivery matches on membership, so a duplicate selects nothing
        extra; it is simply a subscription UBB rewrote worse than it found it.
        """
        killed, expired = _successors(WHOLE_UNIT)
        config = self._config([killed, WHOLE_UNIT])

        MIGRATION.split_the_terminal_events(global_apps, None)

        config.refresh_from_db()
        assert config.event_types == [killed, expired]

    def test_contained_works_subscription_fans_out_on_the_same_rule(self):
        """One model, one status set, one rule (#154 §3.1) — asserted rather
        than assumed, because the two halves of the map are two entries and
        nothing but a test says they behave alike."""
        killed, expired = _successors(CONTAINED_WORK)
        config = self._config([CONTAINED_WORK])

        MIGRATION.split_the_terminal_events(global_apps, None)

        config.refresh_from_db()
        assert config.event_types == [killed, expired]

    def test_the_wildcard_and_the_empty_subscription_are_untouched(self):
        """`["*"]` is all events and `[]` is none (0003's explicit opt-in).
        Both are selectors rather than names, so neither has anything to
        map."""
        every = self._config(["*"], url="https://example.com/all")
        none = self._config([], url="https://example.com/none")

        MIGRATION.split_the_terminal_events(global_apps, None)

        every.refresh_from_db()
        none.refresh_from_db()
        assert every.event_types == ["*"]
        assert none.event_types == []

    def test_the_reverse_collapses_both_successors_onto_the_one_name(self):
        """The lossy half, driven rather than described. A subscription that
        held the retired name round-trips exactly — which is what makes the
        reverse worth shipping over a noop that would strand every subscriber
        on a name the reverted code no longer publishes.
        """
        before = ["usage.recorded", WHOLE_UNIT]
        config = self._config(before)

        MIGRATION.split_the_terminal_events(global_apps, None)
        MIGRATION.collapse_the_terminal_events(global_apps, None)

        config.refresh_from_db()
        assert config.event_types == before

    def test_the_one_case_the_reverse_does_not_round_trip(self):
        """Named in the migration's docstring and proved here rather than
        promised: a subscription written AFTER the split naming only ONE
        successor reverses to the retired name and re-forwards to BOTH, so the
        subscriber gains an event they never asked for.

        It exists only in a rollback of the slice itself, for which #155 §10.1
        has ruled there is no meaningful revert. It is a live case so that the
        claim in the docstring is checked by something.
        """
        killed, expired = _successors(WHOLE_UNIT)
        config = self._config([killed])

        MIGRATION.collapse_the_terminal_events(global_apps, None)
        config.refresh_from_db()
        assert config.event_types == [WHOLE_UNIT]

        MIGRATION.split_the_terminal_events(global_apps, None)
        config.refresh_from_db()
        assert config.event_types == [killed, expired]

    def test_a_subscription_needing_no_change_is_not_written_at_all(self):
        """A data migration that rewrote every row would churn a whole table to
        no purpose. Counted as UPDATE statements against the config table, not
        by comparing `updated_at`, which a queryset `.update()` does not touch
        — so a timestamp assertion would pass over exactly the rewrite being
        ruled out.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._config(["usage.recorded", "*"])
        table = TenantWebhookConfig._meta.db_table

        with CaptureQueriesContext(connection) as queries:
            MIGRATION.split_the_terminal_events(global_apps, None)

        writes = [q for q in queries.captured_queries
                  if q["sql"].startswith("UPDATE") and table in q["sql"]]
        assert writes == []


# ---------------------------------------------------------------------------
# 3. Outbox rows ROUTE, one row to one successor
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAPendingRowRoutesByItsOwnRecordedReason:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Acme")

    def _row(self, event_type, **payload):
        return OutboxEvent.objects.create(
            event_type=event_type, tenant_id=str(self.tenant.id),
            payload={"tenant_id": str(self.tenant.id), **payload})

    def _routed(self, row):
        MIGRATION.split_the_terminal_events(global_apps, None)
        row.refresh_from_db()
        return row.event_type

    def test_a_row_recording_a_reaper_reason_lands_on_expired(self):
        """The evidenced claim: this unit of work went quiet inside its
        silence window and a sweeper wrote the honest answer."""
        _, expired = _successors(WHOLE_UNIT)
        row = self._row(WHOLE_UNIT, reason=reasons.SILENCE_WINDOW)

        assert self._routed(row) == expired

    def test_the_absolute_deadline_is_a_reaper_reason_too(self):
        """Both sweeper reasons, because they are two rungs of one ladder and
        a set holding only the first would route the other as a spend stop."""
        _, expired = _successors(WHOLE_UNIT)
        row = self._row(WHOLE_UNIT, reason=reasons.STALE_MAX_AGE)

        assert self._routed(row) == expired

    def test_a_row_recording_any_other_reason_lands_on_killed(self):
        """A ceiling crossing is a stop UBB applied, which is what `killed`
        claims — and the retired event is documented as the kill fan-out."""
        killed, _ = _successors(WHOLE_UNIT)
        row = self._row(WHOLE_UNIT, reason=reasons.TASK_LIMIT)

        assert self._routed(row) == killed

    def test_the_customer_wide_stop_and_the_parent_cascade_land_on_killed_too(
            self):
        """Named separately from the ceiling above because the default is a
        claim about EVERY other reason, and a case exercising one of them
        proves the branch rather than the rule."""
        killed, _ = _successors(WHOLE_UNIT)
        wide = self._row(WHOLE_UNIT, reason=reasons.CUSTOMER_WIDE_STOP)
        cascaded = self._row(WHOLE_UNIT, reason=reasons.PARENT_KILLED)

        MIGRATION.split_the_terminal_events(global_apps, None)

        wide.refresh_from_db()
        cascaded.refresh_from_db()
        assert wide.event_type == killed
        assert cascaded.event_type == killed

    def test_a_row_with_no_recognisable_reason_lands_on_killed(self):
        """⚠ THE DEFAULT IS STATED, NOT ACCIDENTAL. `expired` is the strictly
        narrower claim — *nobody ever told UBB how this ended* — and it is
        assertable only from a reaper's reason. Asserting the narrow claim
        without evidence is the worse error: it would tell a subscriber a
        worker went quiet when UBB had in fact stopped the work.

        Both shapes of "no evidence" are driven: a reason nothing recognises,
        and no reason recorded at all.
        """
        killed, _ = _successors(WHOLE_UNIT)
        unrecognised = self._row(WHOLE_UNIT, reason="something_nobody_declared")
        silent = self._row(WHOLE_UNIT)

        MIGRATION.split_the_terminal_events(global_apps, None)

        unrecognised.refresh_from_db()
        silent.refresh_from_db()
        assert unrecognised.event_type == killed
        assert silent.event_type == killed

    def test_contained_works_rows_route_on_the_same_rule(self):
        killed, expired = _successors(CONTAINED_WORK)
        reaped = self._row(CONTAINED_WORK, reason=reasons.SILENCE_WINDOW)
        stopped = self._row(CONTAINED_WORK, reason=reasons.SUBTASK_LIMIT)

        MIGRATION.split_the_terminal_events(global_apps, None)

        reaped.refresh_from_db()
        stopped.refresh_from_db()
        assert reaped.event_type == expired
        assert stopped.event_type == killed

    def test_one_row_becomes_one_row(self):
        """A pending row is one past event about one unit of work. Duplicating
        it — the subscription rule, applied to the wrong table — would deliver
        a stop twice that happened once."""
        self._row(WHOLE_UNIT, reason=reasons.TASK_LIMIT)

        MIGRATION.split_the_terminal_events(global_apps, None)

        assert OutboxEvent.objects.count() == 1

    def test_rows_of_other_kinds_are_left_alone(self):
        """The filter is the retired name, and a migration that rewrote every
        row would churn the whole outbox."""
        other = self._row("usage.recorded", event_id="e1")

        MIGRATION.split_the_terminal_events(global_apps, None)

        other.refresh_from_db()
        assert other.event_type == "usage.recorded"

    def test_the_outbox_reverse_round_trips_through_the_same_evidence(self):
        """The exact half of the lossy reverse: the payload's recorded reason
        is untouched, so collapsing a routed row and re-forwarding it lands it
        back where it was."""
        _, expired = _successors(WHOLE_UNIT)
        row = self._row(WHOLE_UNIT, reason=reasons.SILENCE_WINDOW)

        MIGRATION.split_the_terminal_events(global_apps, None)
        MIGRATION.collapse_the_terminal_events(global_apps, None)
        row.refresh_from_db()
        assert row.event_type == WHOLE_UNIT
        assert row.payload["reason"] == reasons.SILENCE_WINDOW

        MIGRATION.split_the_terminal_events(global_apps, None)
        row.refresh_from_db()
        assert row.event_type == expired
