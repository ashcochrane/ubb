"""The receipt's column takes the ratified name of what it holds (#370).

The record had three names — this column's, an endpoint docstring calling it the
receipt, and `apps/metering/CONTEXT.md` calling it the audit trail, which
already named the governance ledger. The registry ratified one of them
(`pricing_receipt_subject_type`) and retired the other two as aliases; the word
`provenance` survives as the name of a SECTION inside the record and nowhere
else. The column and the wire key carry the ratified name.

**THE RETIRED NAMES ARE NEVER SPELLED HERE**, and that is not decoration: the
sweep's ledger entries for the column's old name reached ZERO on all four
surfaces in #370, so a living test module containing it would put the count
back above its entry — and the entry is gone, which makes any occurrence at all
an unaccounted site. They are read off the registry that retired them
(`economics.yaml`, the concept's `retired_aliases`), through
`api.v1.tests._helpers.retired_aliases`. Until the cutover (#190) the old
column name was read off `usage/0042`'s `RenameField` instead; that migration
is gone, and the registry is the source that outlives it.

**WHAT THIS MODULE IS FOR, AND WHAT IT IS NOT.** Two claims about the end
state, neither of which the other modules over this column make:

- the posting table answers to the ratified name and to no retired one;
- the SEALING RULE names the column it is about — every refusal it raises
  names it, and no body text names a retired spelling.

That the rule still refuses what it refuses is
`test_a_receipt_seals_once_it_is_complete.py`'s, driven through three doors
against real rows. Asserting it twice would fail in two places for one cause.

Before the cutover this module also held the RENAME itself: that `usage/0042`
was a `RenameField` and never an add-plus-remove (ADR-0007 §1), that it ran no
statement writing a row (old receipts read, never rewritten), and that it took
the rule off and put it back around the rename. Those were facts about one
migration's operations, and they retired with it.
"""

from django.db import connection
from django.test import TestCase

from api.v1.tests._helpers import retired_aliases
from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import rule_on_the_table

#: The rule that has to name this column, addressed by name.
TRIGGER = "trg_posting_receipt_sealing"

#: THE RETIRED SPELLINGS, read off the registry that retired them — never
#: spelled. Both of the record's rival names, which is wider than the one
#: column name the rename moved, and the wider claim is the true one: the
#: column answers to neither.
RETIRED = tuple(retired_aliases("economics", "pricing_receipt_subject_type"))

#: THE RATIFIED SPELLING, taken from the MODEL: what everything else addresses
#: the column through.
RATIFIED = Posting.RECEIPT_COLUMN


class TheColumnTakesTheRatifiedNameTest(TestCase):
    """The column's final name, asked of the live table."""

    def test_the_column_answers_to_the_ratified_name_and_not_the_retired_one(
            self):
        """Asked of the live table, because a migration that ran is evidence
        that a file executed and not that a column carries a name."""
        columns = self._columns_of_the_posting_table()

        self.assertIn(RATIFIED, columns)
        for retired in RETIRED:
            with self.subTest(retired=retired):
                self.assertNotIn(retired, columns)

    def _columns_of_the_posting_table(self):
        with connection.cursor() as cursor:
            return {column.name for column
                    in connection.introspection.get_table_description(
                        cursor, Posting._meta.db_table)}


class TheSealingRuleNamesTheColumnTest(TestCase):
    """The rule's body names the column it is about, asked of the live database.

    Postgres stores a trigger's `WHEN` clause as a parsed expression over
    attribute numbers, but the trigger FUNCTION's body as text: `pg_proc.prosrc`
    is whatever the installer wrote, so a body spelling a column the table does
    not have stays listed in `pg_trigger`, the declaration gate over it stays
    green, and the first `UPDATE` to fire it fails at runtime. That is why this
    class reads the installed body rather than trusting any file's account of
    it. (Before the cutover, #190, this was the half a column rename did not do
    for you, and `usage/0042` re-created the rule around its rename.)
    """

    def test_the_rules_body_names_the_ratified_column(self):
        _, body = rule_on_the_table(TRIGGER)

        self.assertIn(RATIFIED, body)

    def test_the_rules_body_no_longer_names_the_retired_column(self):
        """The direction that would have been silent.

        A body naming a column the table does not carry is not a subtle wrong
        answer: it is a rule that cannot run. Asserted separately from the arm
        above because the two fail for different reasons — one says the rule
        does not name its column, the other says it names one that is gone.
        """
        _, body = rule_on_the_table(TRIGGER)

        for retired in RETIRED:
            with self.subTest(retired=retired):
                self.assertNotIn(retired, body)

    def test_every_refusal_names_the_column_a_reader_will_go_looking_for(self):
        """The messages are what tell this rule apart from the three beside it
        on this table, so a message naming a column nobody can find is worse
        than a bare refusal.

        ⚠ **THE NUMBER IS DERIVED FROM THE BODY, NOT WRITTEN HERE**, and the
        first draft of this test is why: it asserted six and the rule raises
        SEVEN. A literal count taken from a reading is a claim about my memory,
        it goes stale the day a refusal is added or removed, and — worse — it
        goes stale in the passing direction, because a refusal added WITHOUT the
        column name would leave the count of NAMED messages where it was.
        Counting the `RAISE` statements and requiring every one of them to be a
        named refusal makes that case red.

        `test_a_receipt_seals_once_it_is_complete.py` asserts what each message
        SAYS, driven through real statements. What is asserted here is only that
        each one names the column.
        """
        _, body = rule_on_the_table(TRIGGER)
        raises = body.count("RAISE EXCEPTION")
        named = body.count(f"{RATIFIED} is declared resolve_once")

        self.assertTrue(raises, "the rule raises nothing — the walk is broken")
        self.assertEqual(named, raises)
        for retired in RETIRED:
            with self.subTest(retired=retired):
                self.assertNotIn(f"{retired} is declared", body)
