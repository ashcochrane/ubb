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
  through the event route, as the history it is.

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
from apps.metering.pricing.receipts import validate_receipt
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


def _as_the_old_producer_wrote(posting):
    """A copy of `posting` as the fixed-price branch wrote it before #553: the
    posture reason on the column AND in its sealed receipt. Inserted, which is
    the only write the price trigger never sees."""
    planted = uuid.uuid4()
    receipt = copy.deepcopy(getattr(posting, Posting.RECEIPT_COLUMN))
    receipt["subject_id"] = str(planted)
    receipt["pricing"]["detail"]["not_applicable_reason"] = REMOVED
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

    def _a_historical_posting(self):
        """Back to `0046`, where the value was legal; a posting the old producer
        would have written; then `0047`, for real."""
        recorded = self._a_metered_posting(self._priced_work())
        _migrate_to(BEFORE_IT)
        historical = _as_the_old_producer_wrote(recorded)
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

    def test_a_sealed_receipt_keeps_the_value_and_still_reads(self):
        """RESOLVE_ONCE: the receipt is not rewritten, and nothing reading it
        checks its detail against today's value set — so it reads as history,
        beside a column that says the reason that was always true."""
        historical = self._a_historical_posting()

        response = self.client.get(f"/api/v1/metering/usage/{historical.id}",
                                   **self._auth())

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["not_applicable_reason"] == \
            NOT_APPLICABLE_REASON_FIXED_TASK_PRICING
        assert (body["pricing_receipt"]["pricing"]["detail"]
                ["not_applicable_reason"]) == REMOVED
        validate_receipt(getattr(historical, Posting.RECEIPT_COLUMN))


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

