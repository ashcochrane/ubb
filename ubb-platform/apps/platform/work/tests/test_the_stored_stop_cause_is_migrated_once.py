"""Migration `0026` moves the stored stop cause onto the registry's words —
key and values, once (#457, slice 6 §8, TD claim 11).

⚠ NOTHING HERE SPELLS A RETIRED WORD. Every retired spelling is read off the
migration's own map (`MIGRATION.BY_VALUE`, `MIGRATION.CUSTOMER_WIDE`), and
every current word is asserted by CONSTANT IDENTITY against `reasons` — the
migration's second encoding is held to the first, which is the rule the
terminal-event split's tests set for a migration that cannot import the code.

⚠ WHAT THESE CASES DO NOT COVER, said rather than left to be discovered: they
call the migration's two functions with the live app registry, exactly as
`events/0008`'s tests do, so nothing drives `0026` through the migration
RUNNER. That is sound for THIS migration — it changes no schema and touches
no column definition, so the live registry IS the state it would be handed —
and `makemigrations --check` covers the other half.
"""
import importlib

from django.apps import apps as global_apps
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import (
    CustomerSuspended, StopCleared, StopFired, SubtaskKilled, TaskExpired,
    TaskKilled)
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons
from apps.platform.work.models import Task
from apps.platform.work.services import STOP_CAUSE_KEY, TaskService
from core.vocabulary import (
    CUSTOMER_BILLING_MODE_POSTPAID, CUSTOMER_BILLING_MODE_PREPAID)

MIGRATION = importlib.import_module(
    "apps.platform.work.migrations.0026_a_stop_says_which_bound_was_reached")


def retired_spellings_of(current):
    """Every retired spelling the map rewrites to one current word."""
    return sorted(old for old, new in MIGRATION.BY_VALUE.items()
                  if new == current)


def a_retired_spelling_of(current):
    (spelling, *_) = retired_spellings_of(current)
    return spelling


def ceiling_spellings():
    """`(the whole unit's, the contained unit's)` retired ceiling spelling,
    read off the migration's own reverse so this module never orders them."""
    return tuple(
        MIGRATION.retired_word(reasons.TASK_COGS_CEILING,
                               is_contained=contained, on_a_suspension=False)
        for contained in (False, True))


# ---------------------------------------------------------------------------
# 1. The map, held to the constants
# ---------------------------------------------------------------------------

class TheMapIsTheRegistrysWordsTest(TestCase):
    def test_every_current_word_is_a_constant_the_reason_module_holds(self):
        current = set(MIGRATION.BY_VALUE.values()) | {
            MIGRATION.HARD_FLOOR, MIGRATION.CUSTOMER_SPEND_POOL,
            MIGRATION.PARENT_EXPIRED}
        self.assertEqual(current, {
            reasons.TASK_COGS_CEILING, reasons.SILENCE_WINDOW,
            reasons.ABSOLUTE_DEADLINE, reasons.HARD_FLOOR,
            reasons.CUSTOMER_SPEND_POOL, reasons.PARENT_EXPIRED})
        self.assertTrue(current <= reasons.KNOWN_REASONS)

    def test_the_key_it_moves_onto_is_the_one_the_service_writes(self):
        self.assertEqual(MIGRATION.CAUSE_KEY, STOP_CAUSE_KEY)
        self.assertNotEqual(MIGRATION.RETIRED_CAUSE_KEY, STOP_CAUSE_KEY)

    def test_no_retired_spelling_is_a_word_any_producer_still_writes(self):
        """The negative half: a spelling in the map must not be one the
        reason module still holds, or the migration rewrites live rows."""
        overlap = MIGRATION.RETIRED & reasons.ALL_REASONS
        self.assertEqual(overlap, set())

    def test_both_ceiling_spellings_collapse_onto_the_one_word(self):
        self.assertEqual(len(retired_spellings_of(reasons.TASK_COGS_CEILING)), 2)

    def test_the_split_is_by_mode_and_by_nothing_else(self):
        self.assertEqual(
            MIGRATION.current_word(MIGRATION.CUSTOMER_WIDE,
                                   CUSTOMER_BILLING_MODE_POSTPAID),
            reasons.CUSTOMER_SPEND_POOL)
        self.assertEqual(
            MIGRATION.current_word(MIGRATION.CUSTOMER_WIDE,
                                   CUSTOMER_BILLING_MODE_PREPAID),
            reasons.HARD_FLOOR)
        # The producers' own fork, held to the migration's: same input, same
        # word, so a historical row and a live stop agree.
        # The third mode is the tenant's default — the one that does not
        # bill through UBB — read off the model rather than spelled.
        for mode in (CUSTOMER_BILLING_MODE_POSTPAID,
                     CUSTOMER_BILLING_MODE_PREPAID,
                     Tenant._meta.get_field("billing_mode").default):
            self.assertEqual(
                MIGRATION.current_word(MIGRATION.CUSTOMER_WIDE, mode),
                reasons.customer_stop_reason(mode), mode)

    def test_the_migration_is_one_runpython_with_a_stated_reason(self):
        from django.db.migrations import RunPython
        operations = MIGRATION.Migration.operations
        self.assertEqual(len(operations), 1)
        self.assertIsInstance(operations[0], RunPython)
        self.assertIsNotNone(operations[0].reverse_code)
        self.assertIn("ADR-0007", MIGRATION.__doc__)
        self.assertIn("#412", MIGRATION.__doc__)


# ---------------------------------------------------------------------------
# 2. Unit rows
# ---------------------------------------------------------------------------

class MigrationTestBase(TestCase):
    def setUp(self):
        self.prepaid = Tenant.objects.create(
            name="Prepaid", products=["metering", "billing"],
            billing_mode=CUSTOMER_BILLING_MODE_PREPAID)
        self.postpaid = Tenant.objects.create(
            name="Postpaid", products=["metering", "billing"],
            billing_mode=CUSTOMER_BILLING_MODE_POSTPAID)
        self.prepaid_customer = Customer.objects.create(
            tenant=self.prepaid, external_id="pre-1")
        self.postpaid_customer = Customer.objects.create(
            tenant=self.postpaid, external_id="post-1")

    def _unit(self, tenant, customer, *, parent=None, **metadata):
        unit = TaskService.create_task(
            tenant, customer, balance_snapshot_micros=0,
            billing_owner_id=customer.id, parent=parent)
        Task.objects.filter(pk=unit.pk).update(metadata=metadata)
        unit.refresh_from_db()
        return unit

    def _stored_cause(self, unit):
        unit.refresh_from_db()
        return unit.metadata

    def _forward(self):
        MIGRATION._move_the_stored_cause(global_apps, None)

    def _backward(self):
        MIGRATION._put_the_stored_cause_back(global_apps, None)


class AUnitRowsCauseMovesKeyAndValueTest(MigrationTestBase):
    def test_the_customer_wide_word_splits_by_the_owners_tenant_mode(self):
        """The acceptance criterion, on real rows: one prepaid-owned and one
        postpaid-owned row under the retired word read `hard_floor` and
        `customer_spend_pool` back, under the new key."""
        pre = self._unit(self.prepaid, self.prepaid_customer,
                         **{MIGRATION.RETIRED_CAUSE_KEY: MIGRATION.CUSTOMER_WIDE})
        post = self._unit(self.postpaid, self.postpaid_customer,
                          **{MIGRATION.RETIRED_CAUSE_KEY: MIGRATION.CUSTOMER_WIDE})

        self._forward()

        self.assertEqual(self._stored_cause(pre),
                         {STOP_CAUSE_KEY: reasons.HARD_FLOOR})
        self.assertEqual(self._stored_cause(post),
                         {STOP_CAUSE_KEY: reasons.CUSTOMER_SPEND_POOL})

    def test_both_ceiling_spellings_become_the_one_word_at_either_altitude(self):
        whole_spelling, contained_spelling = ceiling_spellings()
        whole = self._unit(self.prepaid, self.prepaid_customer,
                           **{MIGRATION.RETIRED_CAUSE_KEY: whole_spelling})
        contained = self._unit(
            self.prepaid, self.prepaid_customer, parent=whole,
            **{MIGRATION.RETIRED_CAUSE_KEY: contained_spelling})

        self._forward()

        self.assertEqual(self._stored_cause(whole)[STOP_CAUSE_KEY],
                         reasons.TASK_COGS_CEILING)
        self.assertEqual(self._stored_cause(contained)[STOP_CAUSE_KEY],
                         reasons.TASK_COGS_CEILING)

    def test_the_two_expiry_spellings_take_the_registrys_words(self):
        silence = self._unit(
            self.prepaid, self.prepaid_customer,
            **{MIGRATION.RETIRED_CAUSE_KEY:
               a_retired_spelling_of(reasons.SILENCE_WINDOW)})
        deadline = self._unit(
            self.prepaid, self.prepaid_customer,
            **{MIGRATION.RETIRED_CAUSE_KEY:
               a_retired_spelling_of(reasons.ABSOLUTE_DEADLINE)})

        self._forward()

        self.assertEqual(self._stored_cause(silence)[STOP_CAUSE_KEY],
                         reasons.SILENCE_WINDOW)
        self.assertEqual(self._stored_cause(deadline)[STOP_CAUSE_KEY],
                         reasons.ABSOLUTE_DEADLINE)

    def test_a_current_word_under_the_retired_key_moves_key_only(self):
        """A row written by the cascade under the old key already carries a
        registry word; only its key moves, and the rest of the bag survives."""
        unit = self._unit(self.prepaid, self.prepaid_customer,
                          **{MIGRATION.RETIRED_CAUSE_KEY: reasons.PARENT_KILLED,
                             "trigger_source": "parent_cascade",
                             "tenant_key": "kept"})

        self._forward()

        self.assertEqual(self._stored_cause(unit), {
            STOP_CAUSE_KEY: reasons.PARENT_KILLED,
            "trigger_source": "parent_cascade", "tenant_key": "kept"})

    def test_a_row_holding_no_cause_is_not_written_at_all(self):
        self._unit(self.prepaid, self.prepaid_customer, tenant_key="kept")
        table = Task._meta.db_table

        with CaptureQueriesContext(connection) as queries:
            self._forward()

        writes = [q for q in queries.captured_queries
                  if q["sql"].startswith("UPDATE") and table in q["sql"]]
        self.assertEqual(writes, [])


# ---------------------------------------------------------------------------
# 3. Outbox payloads, under both keys
# ---------------------------------------------------------------------------

class AnOutboxPayloadsCauseIsRewrittenTest(MigrationTestBase):
    def _row(self, tenant, event_type, **payload):
        return OutboxEvent.objects.create(
            event_type=event_type, tenant_id=tenant.id,
            payload={"tenant_id": str(tenant.id), **payload})

    def _payload(self, row):
        row.refresh_from_db()
        return row.payload

    def test_a_terminal_events_reason_code_takes_the_registrys_word(self):
        whole_spelling, contained_spelling = ceiling_spellings()
        whole = self._row(self.prepaid, TaskKilled.EVENT_TYPE,
                          reason_code=whole_spelling, task_id="t1")
        contained = self._row(self.prepaid, SubtaskKilled.EVENT_TYPE,
                              reason_code=contained_spelling,
                              subtask_id="s1", parent_task_id="t1")
        expired = self._row(
            self.prepaid, TaskExpired.EVENT_TYPE,
            reason_code=a_retired_spelling_of(reasons.ABSOLUTE_DEADLINE))

        self._forward()

        self.assertEqual(self._payload(whole)["reason_code"],
                         reasons.TASK_COGS_CEILING)
        self.assertEqual(self._payload(contained)["reason_code"],
                         reasons.TASK_COGS_CEILING)
        self.assertEqual(self._payload(expired)["reason_code"],
                         reasons.ABSOLUTE_DEADLINE)

    def test_the_pre_split_rows_older_key_is_rewritten_too(self):
        """Rows `events/0008` routed spell the cause under `reason`, and
        that migration deliberately left the body as recorded — so this one
        has to reach the older key or those rows keep a retired spelling."""
        row = self._row(self.prepaid, TaskExpired.EVENT_TYPE,
                        reason=a_retired_spelling_of(reasons.SILENCE_WINDOW))

        self._forward()

        self.assertEqual(self._payload(row)["reason"], reasons.SILENCE_WINDOW)

    def test_the_customer_stop_pair_splits_by_the_tenants_mode(self):
        pre = self._row(self.prepaid, StopFired.EVENT_TYPE,
                        reason=MIGRATION.CUSTOMER_WIDE, owner_id="o1")
        post = self._row(self.postpaid, StopFired.EVENT_TYPE,
                         reason=MIGRATION.CUSTOMER_WIDE, owner_id="o2")

        self._forward()

        self.assertEqual(self._payload(pre)["reason"], reasons.HARD_FLOOR)
        self.assertEqual(self._payload(post)["reason"],
                         reasons.CUSTOMER_SPEND_POOL)

    def test_the_suspension_events_word_becomes_the_stop_that_suspended(self):
        floor = self._row(self.prepaid, CustomerSuspended.EVENT_TYPE,
                          reason=a_retired_spelling_of(reasons.HARD_FLOOR))
        pool = self._row(self.postpaid, CustomerSuspended.EVENT_TYPE,
                         reason=a_retired_spelling_of(
                             reasons.CUSTOMER_SPEND_POOL))

        self._forward()

        self.assertEqual(self._payload(floor)["reason"], reasons.HARD_FLOOR)
        self.assertEqual(self._payload(pool)["reason"],
                         reasons.CUSTOMER_SPEND_POOL)

    def test_a_payload_carrying_no_retired_spelling_is_not_written(self):
        self._row(self.prepaid, "usage.recorded", event_id="e1")
        self._row(self.prepaid, TaskKilled.EVENT_TYPE,
                  reason_code=reasons.TASK_COGS_CEILING)
        self._row(self.prepaid, StopCleared.EVENT_TYPE, reason="reconciled")
        table = OutboxEvent._meta.db_table

        with CaptureQueriesContext(connection) as queries:
            self._forward()

        writes = [q for q in queries.captured_queries
                  if q["sql"].startswith("UPDATE") and table in q["sql"]]
        self.assertEqual(writes, [])


# ---------------------------------------------------------------------------
# 4. The suspension column
# ---------------------------------------------------------------------------

class TheSuspensionColumnTakesTheStopWordTest(MigrationTestBase):
    def test_both_monetary_words_become_the_stop_that_opened_the_episode(self):
        self.prepaid_customer.status = "suspended"
        self.prepaid_customer.suspension_reason = a_retired_spelling_of(
            reasons.HARD_FLOOR)
        self.prepaid_customer.save()
        self.postpaid_customer.status = "suspended"
        self.postpaid_customer.suspension_reason = a_retired_spelling_of(
            reasons.CUSTOMER_SPEND_POOL)
        self.postpaid_customer.save()
        admin = Customer.objects.create(
            tenant=self.prepaid, external_id="fraud", status="suspended",
            suspension_reason="fraud")

        self._forward()

        self.prepaid_customer.refresh_from_db()
        self.postpaid_customer.refresh_from_db()
        admin.refresh_from_db()
        self.assertEqual(self.prepaid_customer.suspension_reason,
                         reasons.HARD_FLOOR)
        self.assertEqual(self.postpaid_customer.suspension_reason,
                         reasons.CUSTOMER_SPEND_POOL)
        # An admin/fraud suspension is not monetary and is left alone.
        self.assertEqual(admin.suspension_reason, "fraud")


# ---------------------------------------------------------------------------
# 5. After it, no retired spelling anywhere (TD claim 11)
# ---------------------------------------------------------------------------

class NoStoredRowHoldsARetiredSpellingTest(MigrationTestBase):
    def test_a_query_for_any_retired_spelling_over_every_store_returns_nothing(
            self):
        retired = sorted(MIGRATION.RETIRED)
        # One row per retired spelling, in every store and under every key.
        for spelling in retired:
            self._unit(self.postpaid, self.postpaid_customer,
                       **{MIGRATION.RETIRED_CAUSE_KEY: spelling})
            for key in MIGRATION.PAYLOAD_CAUSE_KEYS:
                OutboxEvent.objects.create(
                    event_type=TaskKilled.EVENT_TYPE, tenant_id=self.prepaid.id,
                    payload={"tenant_id": str(self.prepaid.id), key: spelling})
        for spelling in MIGRATION.BY_VALUE:
            Customer.objects.create(
                tenant=self.prepaid, external_id=f"c-{spelling}",
                status="suspended", suspension_reason=spelling)

        self._forward()

        self.assertFalse(
            Task.objects.filter(metadata__has_key=MIGRATION.RETIRED_CAUSE_KEY)
            .exists())
        self.assertFalse(
            Task.objects.filter(
                **{f"metadata__{STOP_CAUSE_KEY}__in": retired}).exists())
        for key in MIGRATION.PAYLOAD_CAUSE_KEYS:
            self.assertFalse(
                OutboxEvent.objects.filter(
                    **{f"payload__{key}__in": retired}).exists(), key)
        self.assertFalse(
            Customer.objects.filter(suspension_reason__in=retired).exists())
        # And what they became is what the producers write today.
        stored = {t.metadata[STOP_CAUSE_KEY] for t in Task.objects.all()}
        self.assertTrue(stored <= reasons.KNOWN_REASONS, stored)


# ---------------------------------------------------------------------------
# 6. The reverse, exact where it can be and lossy where it says
# ---------------------------------------------------------------------------

class TheReverseTest(MigrationTestBase):
    def test_a_unit_row_round_trips_at_either_altitude(self):
        whole_spelling, contained_spelling = ceiling_spellings()
        whole = self._unit(self.prepaid, self.prepaid_customer,
                           **{MIGRATION.RETIRED_CAUSE_KEY: whole_spelling})
        contained = self._unit(
            self.prepaid, self.prepaid_customer, parent=whole,
            **{MIGRATION.RETIRED_CAUSE_KEY: contained_spelling})

        self._forward()
        self._backward()

        self.assertEqual(self._stored_cause(whole),
                         {MIGRATION.RETIRED_CAUSE_KEY: whole_spelling})
        self.assertEqual(self._stored_cause(contained),
                         {MIGRATION.RETIRED_CAUSE_KEY: contained_spelling})

    def test_the_customer_wide_split_collapses_back_exactly(self):
        pre = self._unit(self.prepaid, self.prepaid_customer,
                         **{MIGRATION.RETIRED_CAUSE_KEY: MIGRATION.CUSTOMER_WIDE})
        post = self._unit(self.postpaid, self.postpaid_customer,
                          **{MIGRATION.RETIRED_CAUSE_KEY: MIGRATION.CUSTOMER_WIDE})

        self._forward()
        self._backward()

        for unit in (pre, post):
            self.assertEqual(self._stored_cause(unit)[MIGRATION.RETIRED_CAUSE_KEY],
                             MIGRATION.CUSTOMER_WIDE)

    def test_the_named_losses_are_exactly_the_named_ones(self):
        """The pre-registry silence spelling does not come back, and contained
        work that expired with its parent goes back to the silence window —
        both stated in the docstring, and both live so the claim is checked."""
        stale = self._unit(
            self.prepaid, self.prepaid_customer,
            **{MIGRATION.RETIRED_CAUSE_KEY:
               a_retired_spelling_of(reasons.SILENCE_WINDOW)})
        parent = self._unit(self.prepaid, self.prepaid_customer)
        cascaded = self._unit(self.prepaid, self.prepaid_customer,
                              parent=parent,
                              **{STOP_CAUSE_KEY: reasons.PARENT_EXPIRED})

        self._forward()
        self._backward()

        self.assertEqual(self._stored_cause(stale)[MIGRATION.RETIRED_CAUSE_KEY],
                         reasons.SILENCE_WINDOW)
        self.assertEqual(
            self._stored_cause(cascaded)[MIGRATION.RETIRED_CAUSE_KEY],
            reasons.SILENCE_WINDOW)

    def test_a_suspension_goes_back_to_the_word_the_reverted_code_clears(self):
        self.prepaid_customer.status = "suspended"
        self.prepaid_customer.suspension_reason = a_retired_spelling_of(
            reasons.HARD_FLOOR)
        self.prepaid_customer.save()
        event = OutboxEvent.objects.create(
            event_type=CustomerSuspended.EVENT_TYPE, tenant_id=self.prepaid.id,
            payload={"tenant_id": str(self.prepaid.id),
                     "reason": a_retired_spelling_of(reasons.HARD_FLOOR)})

        self._forward()
        self._backward()

        self.prepaid_customer.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(self.prepaid_customer.suspension_reason,
                         a_retired_spelling_of(reasons.HARD_FLOOR))
        self.assertEqual(event.payload["reason"],
                         a_retired_spelling_of(reasons.HARD_FLOOR))
