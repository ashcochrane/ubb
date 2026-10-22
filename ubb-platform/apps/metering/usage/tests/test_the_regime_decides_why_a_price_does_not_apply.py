"""The removed posture reason, the migration that rewrote it, and the trigger
it lifted once (#553 C2 and B5, ADR-0021 §5).

`tenant_not_billing` named the tenant's billing posture and lost its only
producer when the regime came to decide the reason for every tenant. So
`usage/0047` rewrote the postings that held it to `fixed_task_pricing` — and,
because the posting's price trigger refuses ANY in-place change to the reason,
it did so under a one-time lift of exactly that trigger, inside its own
transaction. What this module holds:

* the migration, run for real against a posting the old producer wrote, rewrites
  it;
* afterwards the trigger is ENABLED, read off `pg_trigger.tgenabled`, and still
  refuses a reason rewrite through every door — the exception was one UPDATE;
* the removed value cannot be written again: the table's closed set refuses it;
* a sealed Pricing Receipt that holds it is not rewritten and still reads,
  through the event route, as the history it is — at EVERY receipt schema that
  could hold it (owner's review of #615). The reason entered a receipt's
  `pricing.detail` with #351, which wrote schema 1 and descends from the commit
  that introduced versioning (#349); #603 moved the writer to schema 2 while
  the producer still lived. So schemas 1 and 2 can hold it. Schema 0 cannot:
  a legacy receipt predates both the versioning and the value, and no fixture
  is invented for it.

⚠ THE MIGRATION IS RUN THROUGH DJANGO'S OWN EXECUTOR, backwards to `0046` and
forwards again, inside the test's transaction: PostgreSQL runs the DDL
transactionally, so it leaves with the test. `SET CONSTRAINTS ALL IMMEDIATE`
first, because a row this test just inserted leaves deferred foreign-key
checks pending, and PostgreSQL will not `ALTER` a table with pending trigger
events — a state a real migration run, which starts its own transaction, never
meets.
"""
import copy
import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from api.v1.tests.test_the_postings_under_an_agreed_price_are_not_applicable import (
    AgreedPriceTestBase)
from apps.metering.pricing.receipts import (
    CANONICAL_QUANTITY_SCHEMA_VERSION, QUANTITY_KEY, SECTIONED_SCHEMA_VERSION,
    SECTIONS, pricing_mode_of, recorded_quantities, schema_version_of,
    subject_type_of, validate_receipt)
from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import DOORS, committed_posting
from core.transitions import RESOLVE_ONCE
from core.vocabulary import (
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING, NOT_APPLICABLE_REASON_VALUES,
    PRICING_STATUS_NOT_APPLICABLE)

#: The value this module is about, which the registry no longer has — so it is
#: spelled here, the one place a test needs the word.
REMOVED = "tenant_not_billing"
TRIGGER = "trg_posting_price_transitions"
REWRITTEN_BY = ("usage", "0047_the_regime_decides_why_a_price_does_not_apply")
BEFORE_IT = ("usage", "0046_the_price_status_carries_its_own_reason")


def _migrate_to(target):
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    MigrationExecutor(connection).migrate([target])


def _the_trigger_is_enabled():
    """`O` is enabled (fires in origin and local replication mode); `D` is
    disabled. Read off the catalogue, not off the migration file."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgenabled FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE c.relname = %s AND t.tgname = %s",
            [Posting._meta.db_table, TRIGGER])
        (state,) = cursor.fetchone()
    return state == "O"


def _in_schema_one(receipt):
    """The same receipt in the shape #351 wrote it in: schema 1, whose
    components hold each quantity as a whole NUMBER where schema 2 holds its
    canonical text — and nothing else between them differs."""
    one = copy.deepcopy(receipt)
    one["receipt_schema_version"] = SECTIONED_SCHEMA_VERSION
    for section in SECTIONS:
        for component in one[section]["detail"].get("components", []):
            component[QUANTITY_KEY] = int(component[QUANTITY_KEY])
    costing = one["costing"]["detail"]
    for held in ("uncosted_quantities", "undeclared_quantities"):
        if held in costing:
            costing[held] = {key: int(value)
                             for key, value in costing[held].items()}
    return one


def _as_the_old_producer_wrote(posting, schema=CANONICAL_QUANTITY_SCHEMA_VERSION):
    """A copy of `posting` as the fixed-price branch wrote it before #553: the
    posture reason on the column AND in its sealed receipt, in the receipt
    `schema` it was written in. Inserted, which is the only write the price
    trigger never sees."""
    planted = uuid.uuid4()
    receipt = copy.deepcopy(getattr(posting, Posting.RECEIPT_COLUMN))
    receipt["subject_id"] = str(planted)
    receipt["pricing"]["detail"]["not_applicable_reason"] = REMOVED
    if schema == SECTIONED_SCHEMA_VERSION:
        receipt = _in_schema_one(receipt)
    columns = {field.attname: getattr(posting, field.attname)
               for field in Posting._meta.concrete_fields
               if field.attname not in ("id", "created_at", "updated_at",
                                        "idempotency_key")}
    columns.update(id=planted, idempotency_key=f"historical-{planted}",
                   not_applicable_reason=REMOVED,
                   **{Posting.RECEIPT_COLUMN: receipt})
    Posting.objects.bulk_create([Posting(**columns)])
    return Posting.objects.get(pk=planted)


@pytest.mark.django_db
class TestTheRemovedReasonIsRewrittenOnceUnderALiftedTrigger(
        AgreedPriceTestBase):
    """A metering-only tenant's fixed-price work: exactly the population the
    old producer wrote the value for."""

    PRODUCTS = ["metering"]
    BILLING_MODE = None

    def _a_historical_posting(self, schema=CANONICAL_QUANTITY_SCHEMA_VERSION):
        """Back to `0046`, where the value was legal; a posting the old producer
        would have written, its receipt in `schema`; then `0047`, for real.
        The posting it was copied from is kept, as one written NOW. Its cost
        is RESOLVED from a declared quantity, so its receipt holds that
        quantity in a component — the field the two shapes spell differently,
        and so the one a reader of either has to get right."""
        self.recorded = self._a_finely_measured_posting(self._priced_work())
        _migrate_to(BEFORE_IT)
        historical = _as_the_old_producer_wrote(self.recorded, schema)
        assert historical.not_applicable_reason == REMOVED
        _migrate_to(REWRITTEN_BY)
        historical.refresh_from_db()
        return historical

    def test_the_migration_rewrites_what_the_old_producer_wrote(self):
        historical = self._a_historical_posting()

        assert (historical.not_applicable_reason
                == NOT_APPLICABLE_REASON_FIXED_TASK_PRICING)

    def test_the_trigger_it_lifted_is_enabled_again(self):
        self._a_historical_posting()

        assert _the_trigger_is_enabled()

    def test_the_trigger_still_refuses_a_reason_rewrite_through_every_door(
            self):
        """The exception was one UPDATE. Every write after it meets the rule."""
        historical = self._a_historical_posting()

        for name, door in DOORS:
            try:
                with transaction.atomic():
                    door(historical, not_applicable_reason=None)
            except IntegrityError as refusal:
                assert RESOLVE_ONCE in str(refusal), name
                assert "billed_cost_micros and pricing_status" in str(refusal)
            else:
                raise AssertionError(f"{name} rewrote the reason in place")
            historical.refresh_from_db()
            assert (historical.not_applicable_reason
                    == NOT_APPLICABLE_REASON_FIXED_TASK_PRICING)

    def _reads_as_history(self, schema):
        """RESOLVE_ONCE: the receipt is not rewritten, and nothing reading it
        checks its detail against today's value set — so it reads as history,
        beside a column that says the reason that was always true."""
        historical = self._a_historical_posting(schema)
        sealed = getattr(historical, Posting.RECEIPT_COLUMN)
        assert schema_version_of(sealed) == schema

        response = self.client.get(f"/api/v1/metering/usage/{historical.id}",
                                   **self._auth())

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["not_applicable_reason"] == \
            NOT_APPLICABLE_REASON_FIXED_TASK_PRICING
        # Returned exactly as it was sealed: the historical text unchanged.
        assert body["pricing_receipt"] == sealed
        assert (body["pricing_receipt"]["pricing"]["detail"]
                ["not_applicable_reason"]) == REMOVED
        # Every reader that dispatches on the shape reads it — the same bag of
        # quantities as the receipt it was copied from, whichever shape.
        now = getattr(self.recorded, Posting.RECEIPT_COLUMN)
        # Not vacuous: the receipt holds a quantity for the readers to read.
        assert recorded_quantities(now)
        assert recorded_quantities(sealed) == recorded_quantities(now)
        assert pricing_mode_of(sealed) == pricing_mode_of(now)
        assert subject_type_of(sealed) == subject_type_of(now)
        # And nothing new produces the value: the receipt written today says
        # the regime's reason.
        assert now["pricing"]["detail"]["not_applicable_reason"] == \
            NOT_APPLICABLE_REASON_FIXED_TASK_PRICING
        return sealed

    def test_a_sealed_schema_two_receipt_keeps_the_value_and_still_reads(self):
        sealed = self._reads_as_history(CANONICAL_QUANTITY_SCHEMA_VERSION)
        # The writer's own check is about the shape, never this value.
        validate_receipt(sealed)

    def test_a_sealed_schema_one_receipt_keeps_the_value_and_still_reads(self):
        """`validate_receipt` is the WRITER's check, of the one shape written
        today, so it is not asked of a schema-1 receipt; the readers above,
        which know every readable shape, are what read it."""
        self._reads_as_history(SECTIONED_SCHEMA_VERSION)


@pytest.mark.django_db
class TestTheRemovedReasonCannotBeWrittenAgain:

    def test_the_trigger_is_enabled_on_the_migrated_database(self):
        """The database every test runs on was migrated through `0047`, so a
        migration that left its lift in place would leave this false here."""
        assert _the_trigger_is_enabled()

    def test_the_value_set_no_longer_holds_it(self):
        assert NOT_APPLICABLE_REASON_VALUES == {
            NOT_APPLICABLE_REASON_FIXED_TASK_PRICING}

    def test_the_table_refuses_it_at_insert(self):
        with pytest.raises(IntegrityError, match="ck_posting_not_applicable_reason"):
            with transaction.atomic():
                committed_posting(billed_cost_micros=None,
                                  pricing_status=PRICING_STATUS_NOT_APPLICABLE,
                                  not_applicable_reason=REMOVED)

