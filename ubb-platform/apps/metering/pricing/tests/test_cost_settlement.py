"""One door settles a supplier cost, and it tells the caller what happened (#318).

ADR-0007 §2 gives the shape of the statement — a conditional update that asserts
exactly one affected row. Spelled for these columns, and with the third one the
ADR's generic form does not carry:

    UPDATE ... SET provider_cost_micros = %s, costing_status = 'known',
                   unresolved_reason = NULL
     WHERE id = %s AND provider_cost_micros IS NULL AND costing_status =
     'unresolved'

**The reason column is not an embellishment**: #317's combination `CHECK`
requires a `known` row to carry no reason, so the two-column statement the ADR
writes generically cannot commit against this table. The `WHERE` clause is the
ADR's, unchanged, and it is the whole of the precondition.

**Zero affected rows is not a retry**, and that is the whole reason the door
exists as a function rather than as a line in whichever service happens to learn
a cost. A read-then-write settles twice under a race and nobody finds out; this
statement decides at the database, and the caller is told which of the two
things happened: the cost was already settled, or the posting was never
unresolved in the first place.

**The two answers are honestly derived, not guessed.** After a zero-row update
the posting's status is read back, and the mapping is the one the table can
actually support: `known` means a resolved amount is already there, and
`not_applicable` means this posting is not the kind of thing that gets a
supplier cost at all. UBB cannot tell a row that was settled a moment ago from
one born `known`, and does not pretend to — `already_settled` is a statement
about the row's current answer, not about its history.

**A third answer would be a lie**, so it is a raise instead: a posting that does
not exist is not "already settled", and a posting still reading `unresolved`
after a statement whose `WHERE` clause names that exact state means the door
itself is broken. Neither is reported as an outcome.
"""
import ast
import pathlib
import threading
import uuid
from unittest.mock import patch

from django.db import connection
from django.db.models.query import QuerySet
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from apps.metering.pricing.services.cost_settlement import (
    Settlement, settle_provider_cost)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)


def _posting(**columns):
    tenant = Tenant.objects.create(name="T")
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    columns.setdefault("idempotency_key", "k")
    return Posting.objects.create(tenant=tenant, customer=customer, **columns)


def _unresolved():
    return _posting(provider_cost_micros=None,
                    costing_status=COSTING_STATUS_UNRESOLVED,
                    unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING)


class AnUnresolvedCostSettlesOnceTest(TestCase):

    def test_it_reports_that_it_settled(self):
        posting = _unresolved()
        self.assertIs(
            settle_provider_cost(posting_id=posting.pk,
                                 provider_cost_micros=4_200),
            Settlement.SETTLED)

    def test_the_amount_the_status_and_the_reason_all_move(self):
        """One statement, three columns. The table refuses any subset of them.

        Read back through a cursor rather than off the instance, because an
        in-memory object would agree with whatever the caller set on it.
        """
        posting = _unresolved()
        settle_provider_cost(posting_id=posting.pk, provider_cost_micros=4_200)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT provider_cost_micros, costing_status, unresolved_reason "
                f"FROM {Posting._meta.db_table} WHERE id = %s", [str(posting.pk)])
            self.assertEqual(cursor.fetchone(),
                             (4_200, COSTING_STATUS_KNOWN, None))

    def test_a_cost_of_exactly_zero_settles(self):
        """The reading `NULL` was stealing before #317.

        A supplier that charged nothing is resolved at zero, and a door that
        treated a falsy amount as "nothing to settle" would leave those postings
        unresolved for ever — the same conflation, one layer up.
        """
        posting = _unresolved()
        self.assertIs(
            settle_provider_cost(posting_id=posting.pk, provider_cost_micros=0),
            Settlement.SETTLED)
        posting.refresh_from_db()
        self.assertEqual(posting.provider_cost_micros, 0)

    def test_it_settles_in_exactly_one_statement(self):
        """No read-then-write, asserted as SQL rather than as intention.

        A settlement that checked the row first and wrote second would pass
        every other test in this class and lose a race in production. What rules
        that out is that there is one statement and its `WHERE` clause carries
        the whole precondition.
        """
        posting = _unresolved()
        with CaptureQueriesContext(connection) as queries:
            settle_provider_cost(posting_id=posting.pk,
                                 provider_cost_micros=1)
        statements = [q["sql"] for q in queries.captured_queries
                      if q["sql"].lstrip().upper().startswith("UPDATE")]
        self.assertEqual(len(statements), 1)
        self.assertEqual(len(queries.captured_queries), 1)
        for condition in ("provider_cost_micros", "IS NULL", "costing_status"):
            self.assertIn(condition, statements[0])


class ASettlementThatFindsNothingSaysWhichTest(TestCase):
    """The two zero-row answers, told apart.

    Reporting them as one — or as a failure to be retried — is how a settlement
    loop turns a resolved posting into an infinite one.
    """

    def test_settling_twice_is_refused_and_says_it_was_already_settled(self):
        posting = _unresolved()
        settle_provider_cost(posting_id=posting.pk, provider_cost_micros=100)
        self.assertIs(
            settle_provider_cost(posting_id=posting.pk,
                                 provider_cost_micros=999),
            Settlement.ALREADY_SETTLED)

    def test_the_second_settlement_does_not_move_the_amount(self):
        """The answer, not just the return value.

        `ALREADY_SETTLED` reported over a row that had quietly taken the second
        amount would be the correction ADR-0007 §2 prohibits, wearing the label
        of the thing that refused it.
        """
        posting = _unresolved()
        settle_provider_cost(posting_id=posting.pk, provider_cost_micros=100)
        settle_provider_cost(posting_id=posting.pk, provider_cost_micros=999)
        posting.refresh_from_db()
        self.assertEqual(posting.provider_cost_micros, 100)

    def test_settling_a_not_applicable_posting_is_refused(self):
        """An Event Type that declares no cost never acquires one.

        Not a race, not a retry, and not the same fact as a cost that has not
        arrived yet: this posting is not waiting for anything.
        """
        posting = _posting(provider_cost_micros=None,
                           costing_status=COSTING_STATUS_NOT_APPLICABLE)
        self.assertIs(
            settle_provider_cost(posting_id=posting.pk,
                                 provider_cost_micros=100),
            Settlement.NEVER_UNRESOLVED)
        posting.refresh_from_db()
        self.assertIsNone(posting.provider_cost_micros)

    def test_a_posting_born_known_reports_already_settled(self):
        """The honest limit of what the table can answer.

        A row that arrived with a cost and a row settled a second ago are the
        same row now. The door reports what it can see rather than inventing a
        distinction it would have to keep a history to support.
        """
        posting = _posting(provider_cost_micros=7,
                           costing_status=COSTING_STATUS_KNOWN)
        self.assertIs(
            settle_provider_cost(posting_id=posting.pk,
                                 provider_cost_micros=100),
            Settlement.ALREADY_SETTLED)

    def test_a_posting_that_does_not_exist_is_not_an_outcome(self):
        """Neither answer is true of it, so neither is returned."""
        with self.assertRaises(Posting.DoesNotExist):
            settle_provider_cost(posting_id=uuid.uuid4(),
                                 provider_cost_micros=100)

    def test_a_settlement_with_no_amount_is_refused_before_the_statement(self):
        """`None` is what "unresolved" means; it cannot be what settles one."""
        posting = _unresolved()
        with self.assertRaises(ValueError):
            settle_provider_cost(posting_id=posting.pk,
                                 provider_cost_micros=None)

    def test_matching_more_than_one_posting_is_an_error_not_a_success(self):
        """ADR-0007 §2's "exactly one affected row", reached the only way it can be.

        The statement filters on a primary key, so no fixture can make it match
        twice — the guard is there for the edit that widens that filter, and a
        bulk settlement that reported success is precisely what it is for. The
        row count is forced rather than staged, because staging it would mean
        shipping the widened filter to test the guard against it.
        """
        posting = _unresolved()
        with patch.object(QuerySet, "update", return_value=2):
            with self.assertRaises(RuntimeError):
                settle_provider_cost(posting_id=posting.pk,
                                     provider_cost_micros=1)


class ASecondSettlementLosesCleanlyTest(TransactionTestCase):
    """Two threads, one row, real Postgres row locking.

    The repository's existing race tests (`apps/billing/tests/
    test_concurrency_races.py`) are the pattern: `TransactionTestCase` so the
    fixture is committed before the workers start, a `Barrier` to put both
    inside the critical section at once, and each worker closing its
    thread-local connection on the way out.

    Serialised retries would satisfy every other test in this module. This is
    the one that fails if the door ever reads before it writes.
    """

    def test_exactly_one_of_two_racing_settlements_wins(self):
        posting = _posting(provider_cost_micros=None,
                           costing_status=COSTING_STATUS_UNRESOLVED,
                           unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING)
        barrier = threading.Barrier(2)
        outcomes = {}
        failures = []

        def settle(name, amount):
            try:
                barrier.wait(timeout=10)
                outcomes[name] = settle_provider_cost(
                    posting_id=posting.pk, provider_cost_micros=amount)
            except Exception as error:            # pragma: no cover - reported
                failures.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=settle, args=("first", 100)),
                   threading.Thread(target=settle, args=("second", 200))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(failures, [])
        self.assertEqual(sorted(outcome.value for outcome in outcomes.values()),
                         [Settlement.ALREADY_SETTLED.value,
                          Settlement.SETTLED.value])

    def test_the_row_holds_the_winning_amount_and_no_trace_of_the_other(self):
        """The loser leaves nothing behind, which is what "cleanly" means."""
        posting = _posting(provider_cost_micros=None,
                           costing_status=COSTING_STATUS_UNRESOLVED,
                           unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING)
        barrier = threading.Barrier(2)
        outcomes = {}

        def settle(amount):
            try:
                barrier.wait(timeout=10)
                outcomes[amount] = settle_provider_cost(
                    posting_id=posting.pk, provider_cost_micros=amount)
            finally:
                connection.close()

        threads = [threading.Thread(target=settle, args=(100,)),
                   threading.Thread(target=settle, args=(200,))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        posting.refresh_from_db()
        winner = next(amount for amount, outcome in outcomes.items()
                      if outcome is Settlement.SETTLED)
        self.assertEqual(posting.provider_cost_micros, winner)
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertIsNone(posting.unresolved_reason)


class ItIsTheOnlyApplicationWriterOfACostResolutionTest(TestCase):
    """Exactly one function settles a cost, checked by walking the tree.

    The trigger refuses every shape but the settlement, so a second writer
    cannot corrupt a posting — but it can perfectly well settle one, and then
    there are two places where "this cost is now known" is decided and only one
    of them is tested. ADR-0007 §2 gives the service layer the commands and the
    database the refusals; this is the half the database cannot hold.

    Walked as source rather than asserted in prose, because a prose claim about
    the rest of the repository ages the moment someone adds a line.

    **What it covers, stated rather than implied**: an ORM `update` or
    `bulk_update` naming a cost column in either argument shape, and a raw
    `UPDATE ... SET` statement that names one. What it does not cover is
    `setattr` plus `save()`, which names nothing to match — that door is shut by
    the model itself and the last test here is where that is written down.
    """

    COLUMNS = {"provider_cost_micros", "costing_status", "unresolved_reason"}

    #: Living backend code, named rather than globbed from the root: a walk over
    #: everything would wander into a virtualenv or a build directory the day
    #: someone runs this from a checkout that has one.
    ROOTS = ("apps", "api", "core", "config", "scripts")

    DOOR = "apps/metering/pricing/services/cost_settlement.py"

    #: The one file allowed to write a settlement outside the door, declared
    #: here rather than left undetected. It measures what the enforcement costs
    #: (ADR-0007's Consequences), and it does so against a database it creates
    #: and destroys in the same run — so its statement never meets a tenant's
    #: data. A declared exception a reader can see beats a hole in the check.
    MEASUREMENT_HARNESS = "scripts/measure_posting_transition_cost.py"

    def _orm_writers(self, tree):
        """`.update(...)` / `.bulk_update(...)` calls naming a cost column.

        Both argument shapes count, and the second is why this is not a keyword
        check: `bulk_update(postings, ["provider_cost_micros"])` passes its
        columns as a LIST OF STRINGS, so a keyword-only test would have had
        `bulk_update` in its list of names and no way whatever to see one. Any
        string constant inside the call is compared, which also covers
        `update(**{"provider_cost_micros": ...})`.
        """
        return [node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("update", "bulk_update")
                and ({keyword.arg for keyword in node.keywords}
                     | {inner.value for inner in ast.walk(node)
                        if isinstance(inner, ast.Constant)
                        and isinstance(inner.value, str)}) & self.COLUMNS]

    def _raw_sql_writers(self, tree):
        """String constants that are an `UPDATE` statement setting a column.

        The ORM is not the only door — the door itself was very nearly written
        with a cursor. Both `UPDATE` and `SET` are required so that prose
        mentioning a column in passing is not a finding, and a statement that
        updates this table without touching a cost column is not one either.
        """
        return [node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "UPDATE" in node.value.upper()
                and "SET" in node.value.upper()
                and any(column in node.value for column in self.COLUMNS)]

    def _writers_in(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return self._orm_writers(tree) + self._raw_sql_writers(tree)

    def test_no_other_module_writes_a_cost_resolution(self):
        platform = pathlib.Path(__file__).resolve().parents[4]
        excused = {self.DOOR, self.MEASUREMENT_HARNESS}
        offenders = []
        for root in self.ROOTS:
            for path in sorted((platform / root).glob("**/*.py")):
                relative = path.relative_to(platform).as_posix()
                if ("/tests/" in f"/{relative}"
                        or "/migrations/" in f"/{relative}"
                        or relative in excused):
                    continue
                offenders += [f"{relative}:{line}"
                              for line in self._writers_in(path)]
        self.assertEqual(offenders, [])

    def test_the_walk_finds_both_kinds_of_writer_when_not_excused(self):
        """The vacuity guard, one arm per detector, through the real helpers.

        Without it, a walk that silently matched nothing — a renamed keyword, an
        `ast` shape that no longer occurs, a directory list that went stale —
        would report a clean tree for a repository it never read. Each excused
        file is also the positive control for the detector that would catch it:
        the door is the ORM writer, the harness is the raw-SQL one.
        """
        platform = pathlib.Path(__file__).resolve().parents[4]
        door = ast.parse((platform / self.DOOR).read_text(encoding="utf-8"))
        harness = ast.parse(
            (platform / self.MEASUREMENT_HARNESS).read_text(encoding="utf-8"))
        self.assertEqual(len(self._orm_writers(door)), 1)
        self.assertEqual(len(self._raw_sql_writers(harness)), 1)

    def test_a_writer_cannot_hide_behind_save(self):
        """The third door, closed by the model rather than by this walk.

        `setattr` then `save()` names no column an `ast` walk could match, so
        the walk cannot see it — and it cannot settle anything either, because
        the posting refuses every update through that door. Asserted here so
        that the gap in the walk is a stated one rather than an oversight.
        """
        posting = _unresolved()
        posting.provider_cost_micros = 100
        posting.costing_status = COSTING_STATUS_KNOWN
        with self.assertRaises(ValueError):
            posting.save()
