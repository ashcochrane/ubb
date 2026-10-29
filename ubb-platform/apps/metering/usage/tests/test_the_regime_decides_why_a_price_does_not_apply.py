"""The removed posture reason stays removed, and the trigger that held it
stays on (#553 C2 and B5, ADR-0021 §5).

`tenant_not_billing` named the tenant's billing posture and lost its only
producer when the regime came to decide the reason for every tenant: a
fixed-price piece of work's postings say `fixed_task_pricing`, on the column and
in the receipt, whatever the tenant's posture (pinned where that work is
recorded, `api/v1/tests/test_the_postings_under_an_agreed_price_are_not_applicable.py`).
What this module holds of the end state:

* the removed value cannot be written again: the registry's set no longer holds
  it, and the table's closed set (`ck_posting_not_applicable_reason`) refuses it;
* the posting's price rule, `trg_posting_price_transitions`, is installed
  ENABLED — the rule that refuses any in-place change to the reason.

Before the cutover (#190) this module also held the HISTORY: `usage/0047`
rewrote the postings the old producer wrote to `fixed_task_pricing` under a
one-time lift of exactly that trigger, run here through Django's executor
backwards to `0046` and forwards again, and a sealed receipt that held the
removed value (at schemas 1 and 2) was read back as history. That chain and
the older receipt shapes are gone (ruling 8: one receipt shape, version 2), and
those cases retired with them. That the rule refuses a reason rewrite through
every door is `test_a_price_resolves_once.py`'s
`test_the_reason_cannot_be_re_diagnosed_in_place`.
"""
import pytest
from django.db import IntegrityError, connection, transaction

from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import committed_posting
from core.vocabulary import (
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING, NOT_APPLICABLE_REASON_VALUES,
    PRICING_STATUS_NOT_APPLICABLE)

#: The value this module is about, which the registry no longer has — so it is
#: spelled here, the one place a test needs the word.
REMOVED = "tenant_not_billing"
TRIGGER = "trg_posting_price_transitions"


def _the_trigger_is_enabled():
    """`O` is enabled (fires in origin and local replication mode); `D` is
    disabled. Read off the catalogue, not off a migration file."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgenabled FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE c.relname = %s AND t.tgname = %s",
            [Posting._meta.db_table, TRIGGER])
        (state,) = cursor.fetchone()
    return state == "O"


@pytest.mark.django_db
class TestTheRemovedReasonCannotBeWrittenAgain:

    def test_the_trigger_is_enabled_on_the_migrated_database(self):
        """The database every test runs on carries the price rule ENABLED, as
        `usage/0002_the_database_rules` installs it. Before the cutover (#190)
        this was the proof that `usage/0047`'s one-time lift left nothing
        behind; it stays as the end-state fact a lift left in place would
        break."""
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
