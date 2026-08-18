"""What the declared-transition triggers cost per insert and per update (#318).

ADR-0007's Consequences ask for this by name, of this decision specifically:

    Database-enforced transitions have a per-insert and per-update cost on the
    hottest path in the system. Which mechanism carries them — triggers, CHECK
    constraints, rules — is an implementation decision, and its cost should be
    measured rather than assumed.

So this measures it, against the mechanisms actually installed, on a throwaway
database of its own. **There are THREE rules on this table since #353**, one per
declared subject, and all of them are installed and dropped together — a number
for one measured with the others standing would be a measurement of the set.
Five statements are timed, with the rules installed and again with them dropped,
each the median of `--runs` batches of `--rows`:

    insert      a posting, the hottest write in the system
    update      a column no rule says anything about — the ordinary write
    settlement  unresolved to known, the statement the supplier rule admits
    resolution  unknown to known, the statement the price rule admits
    completion  an unresolved receipt section completed, which the third admits

**The insert number is the one to read first.** All three triggers are `BEFORE
UPDATE`, so an insert should pay nothing at all; a number that says otherwise
means the enforcement is not the shape `usage/migrations/0037`, `0039` and
`0040` claim.

**⚠ The completion column is the one to read second, and it is not comparable
with the two beside it.** The other two permitted moves compare scalars; this
one walks a `jsonb` record, rebuilds it and compares it whole. That is expected
to cost more than a status comparison, and the question the number answers is
whether it costs enough to matter on a statement that happens once per posting
in a recovery path.

**The unrelated-column update is where a badly-built rule would show up, and it
is where each ADDITIONAL one shows up first.** It is the ordinary write on this
table, and it is why each migration puts a `WHEN` clause on its trigger: without
one, every update on the table would enter a `plpgsql` function to discover it
had nothing to say. With three rules there are three `WHEN` clauses to evaluate
per statement, so this is the column that answers whether a rule taxed the
writes that have nothing to do with it. That number should still be flat.

**The three permitted moves are the statements that should pay**, and each
happens once per posting in a remediation path. A rule that made those
measurably slower would still be worth having; a rule that made recording slower
would not. They are timed separately because they are different rules over
different columns: one number for "a transition" would hide any of them moving.

Run from `ubb-platform/`::

    python scripts/measure_posting_transition_cost.py [--rows 2000] [--runs 5]

It creates a database, measures, drops it, and writes nothing anywhere else.
"""
import argparse
import importlib
import os
import statistics
import sys
import time
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLATFORM_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402

from apps.metering.usage.models import Posting  # noqa: E402
from core.vocabulary import (  # noqa: E402
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

#: The receipt's column, taken from the model rather than spelled — the statement
#: below is living code, so the vocabulary rule applies to it in full and the
#: ticket that re-spells the column carries this statement with it.
RECEIPT_COLUMN = Posting.RECEIPT_COLUMN

#: The rules on this table, each as (migration module, trigger name). ONE ENTRY
#: PER RULE, and both halves matter: the trigger name is what is asked for by
#: name below, and the migration is where the shipped SQL is imported from.
#:
#: #352 added the second and #353 the third. A script that knew about some of
#: them would install and drop those while the rest stood, and every delta below
#: would be the cost of part of the table's enforcement measured against the
#: remainder.
RULES = (
    ("0037_a_cost_settles_once_and_the_table_holds_it",
     "trg_posting_declared_transitions"),
    ("0039_a_price_resolves_once_and_the_table_holds_it",
     "trg_posting_price_transitions"),
    ("0040_a_receipt_seals_when_its_unresolved_fields_complete",
     "trg_posting_receipt_sealing"),
)

#: **One statement per batch, not one per row.** Issuing a statement per row
#: measures the round trip to Postgres and not much else: at 2,000 rows that is
#: ~1.4 ms each, three orders of magnitude above anything a row-level trigger
#: does, and the difference between installed and dropped comes back inside the
#: noise — negative, on the first attempt at this. A set-oriented statement
#: fires the trigger once per row while paying for one round trip, which is what
#: isolates the number this script exists to report.
#:
#: The two updates below are single statements for that reason. **The insert is
#: not one** — `_rows` and `_insert` go through `bulk_create`, because a
#: hand-written `INSERT` would have to name every NOT NULL column on this table
#: and two of them are words the forbidden-term sweep is counting down. The
#: ORM's own cost is in both the installed and the dropped number, so it cancels
#: in the delta, which is the figure being reported; the absolute insert column
#: is correspondingly inflated and is not comparable with the update columns.

#: A column no declared rule mentions — the ordinary write on this table, and
#: where a trigger without a `WHEN` clause would show up as a tax on everything.
UNRELATED_UPDATE = "UPDATE ubb_posting SET balance_after_micros = 1"

#: The door's own statement, in bulk and with its guard clause intact. The two
#: status tokens are INTERPOLATED FROM THE REGISTRY rather than typed: this is
#: living code, so `docs/conventions/coding-standards.md` §Vocabulary applies to
#: it in full, and the migration's frozen-file exemption does not reach here.
SETTLEMENT = f"""
UPDATE ubb_posting SET provider_cost_micros = 42,
       costing_status = '{COSTING_STATUS_KNOWN}', unresolved_reason = NULL
 WHERE provider_cost_micros IS NULL
   AND costing_status = '{COSTING_STATUS_UNRESOLVED}'
"""

#: The price rule's own permitted move, and the reason there are four columns of
#: numbers rather than three. It is a different statement over different columns
#: from the settlement above, so it fires a different trigger; timing only one
#: of them and calling the answer "a transition" would let either rule's cost
#: move without the report noticing.
RESOLUTION = f"""
UPDATE ubb_posting SET billed_cost_micros = 42,
       pricing_status = '{PRICING_STATUS_KNOWN}'
 WHERE billed_cost_micros IS NULL
   AND pricing_status = '{PRICING_STATUS_UNKNOWN}'
"""

#: The receipt rule's own permitted move — one unresolved section completed.
#:
#: It touches ONLY the receipt column, so the two rules above never fire on it
#: and this number is the third rule measured alone. Written as `jsonb` surgery
#: rather than by handing over a whole record because a set-oriented statement
#: is what fires a row-level trigger per row while paying for one round trip,
#: which is the whole method of this script.
#:
#: The braces are doubled because this is an f-string: every `{{` below is one
#: literal brace in the SQL.
#:
#: Read it against `settle` and `resolve` knowing it is not the same kind of
#: work: those compare scalars, this walks a record, rebuilds it and compares it
#: whole. It is the dearest of the three by construction, and the question the
#: number answers is whether it is dear enough to matter on a statement that
#: happens once per posting in a recovery path.
COMPLETION = f"""
UPDATE ubb_posting
   SET {RECEIPT_COLUMN} = jsonb_set(
         jsonb_set({RECEIPT_COLUMN}, '{{pricing}}',
                   '{{"method": "{PRICING_METHOD_MARGIN_OVER_COST}",
                      "status": "{PRICING_STATUS_KNOWN}", "detail": {{}}}}'),
         '{{totals,billed_cost_micros}}', '42')
 WHERE {RECEIPT_COLUMN} #>> '{{pricing,status}}' = '{PRICING_STATUS_UNKNOWN}'
"""


def _an_unpriced_receipt():
    """A real receipt whose price section is unresolved, built at the boundary.

    Through `build_receipt` rather than written out here, so the row this script
    inserts is the record the rule is actually about — a hand-written dict could
    drift into a shape the construction boundary would never have admitted, and
    the completion above would then be timing a statement no rule would see.
    """
    from apps.metering.pricing.receipts import (
        ReceiptSubject, Resolution, build_receipt)

    return build_receipt(
        subject=ReceiptSubject(
            subject_type=PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
            subject_id="11111111-1111-1111-1111-111111111111"),
        effective_at="2026-08-18T09:00:00+00:00", currency="usd",
        pricing_engine_version="2.1.0",
        costing=Resolution(method=COSTING_METHOD_CALCULATED,
                           status=COSTING_STATUS_KNOWN, amount_micros=1,
                           detail={"components": []}),
        pricing=Resolution(method=None, status=PRICING_STATUS_UNKNOWN,
                           amount_micros=None, detail={}),
        provenance={})


def _execute(statement, params=None):
    with connection.cursor() as cursor:
        cursor.execute(statement, params)


def _tenant_and_customer():
    """The fixture, and nothing here is timed.

    One tenant and one customer for the whole run, created once and reused by
    every batch: what is being measured is what a rule costs per posting, and a
    fixture rebuilt per run would put its own cost inside the numbers.
    """
    from apps.platform.customers.models import Customer
    from apps.platform.tenants.models import Tenant

    tenant = Tenant.objects.create(name="measurement")
    return tenant, Customer.objects.create(tenant=tenant,
                                           external_id="measurement")


def _timed(work):
    start = time.perf_counter()
    work()
    return (time.perf_counter() - start) * 1000


def _rows(tenant, customer, rows, *, unresolved=False, unpriced=False,
          unpriced_receipt=False):
    """Unsaved postings, built OUTSIDE the timer that inserts them.

    Fresh each batch: `bulk_create` stamps primary keys onto the instances it
    is given, so a reused list would insert the same rows twice.

    The three axes are independent because the three rules are: a batch is made
    unresolved to time the supplier settlement, unpriced to time the price
    resolution, carrying an unresolved receipt to time the completion, and none
    of them to time the ordinary write. Each combination is a legal row — the
    table's combination `CHECK`s admit them all — so the state being timed is
    the one asked for rather than whatever survived insertion.
    """
    from apps.metering.usage.models import Posting

    cost = dict(
        provider_cost_micros=None,
        costing_status=COSTING_STATUS_UNRESOLVED,
        unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING) if unresolved \
        else dict(provider_cost_micros=1, costing_status=COSTING_STATUS_KNOWN)
    price = dict(
        billed_cost_micros=None,
        pricing_status=PRICING_STATUS_UNKNOWN) if unpriced \
        else dict(billed_cost_micros=1, pricing_status=PRICING_STATUS_KNOWN)
    receipt = {RECEIPT_COLUMN: _an_unpriced_receipt()} if unpriced_receipt \
        else {}
    return [Posting(tenant=tenant, customer=customer,
                    idempotency_key=str(index), **cost, **price, **receipt)
            for index in range(rows)]


def _insert(postings):
    from apps.metering.usage.models import Posting

    Posting.objects.bulk_create(postings)


def _update_batch():
    _execute(UNRELATED_UPDATE)


def _settle_batch():
    _execute(SETTLEMENT)


def _resolve_batch():
    _execute(RESOLUTION)


def _complete_batch():
    _execute(COMPLETION)


def _rule_is_installed(trigger):
    """Asked BY NAME, never by counting triggers on the table.

    ⚠ THIS IS THE ASSERTION THE WHOLE SCRIPT RESTS ON, AND #352 IS WHY IT IS
    PER-RULE. A count would answer "installed" for a table carrying one rule
    when two were asked for — so dropping the price rule and leaving the cost
    rule standing would read as a fully installed table, and every delta below
    would be a measurement of nothing. Each rule is asked for by its own name
    and both are required, so a stripped table cannot answer for a whole one in
    either direction.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger t JOIN pg_class c "
            "ON c.oid = t.tgrelid "
            "WHERE c.relname = 'ubb_posting' AND t.tgname = %s", [trigger])
        return cursor.fetchone()[0] > 0


def _rules_are_installed():
    return all(_rule_is_installed(trigger) for _, trigger in RULES)


def _set_rules(state):
    """Install or drop **the shipped SQL**, imported from the migrations.

    A copy of a trigger written out here would measure whatever this script
    happened to say rather than what the table actually carries.

    Both rules move together. What is being reported is the cost of this
    table's declared-transition enforcement, and half of it measured against
    the other half is neither rule's number.
    """
    for module, trigger in RULES:
        migration = importlib.import_module(
            f"apps.metering.usage.migrations.{module}")
        if state == "installed" and not _rule_is_installed(trigger):
            _execute(migration.INSTALL)
        elif state == "dropped" and _rule_is_installed(trigger):
            _execute(migration.UNINSTALL)
        assert _rule_is_installed(trigger) == (state == "installed"), (
            f"{trigger} is not {state}")
    assert _rules_are_installed() == (state == "installed"), state


def _one_batch(tenant, customer, rows):
    """Four timings, each over a table that starts empty and unbloated.

    `TRUNCATE`, not `DELETE`: repeated deletes leave dead tuples behind, and the
    state measured second then pays for the state measured first. That is not a
    hypothetical — it is what the first version of this script reported, as a
    trigger that made every statement *faster*. Each permitted move gets its own
    `TRUNCATE` for the same reason: the settlement rewrites every row, so a
    resolution timed after it on the same table would be paying the settlement's
    dead tuples rather than reporting its own rule.
    """
    _execute("TRUNCATE ubb_posting CASCADE")
    known = _rows(tenant, customer, rows)
    insert = _timed(lambda: _insert(known))
    update = _timed(_update_batch)

    _execute("TRUNCATE ubb_posting CASCADE")
    _insert(_rows(tenant, customer, rows, unresolved=True))
    settle = _timed(_settle_batch)

    _execute("TRUNCATE ubb_posting CASCADE")
    _insert(_rows(tenant, customer, rows, unpriced=True))
    resolve = _timed(_resolve_batch)

    _execute("TRUNCATE ubb_posting CASCADE")
    _insert(_rows(tenant, customer, rows, unpriced_receipt=True))
    complete = _timed(_complete_batch)
    return insert, update, settle, resolve, complete


def measure(rows, runs):
    tenant, customer = _tenant_and_customer()
    samples = {"installed": [], "dropped": []}
    for run in range(runs):
        # Alternated, so that a machine drifting under load — or a table warming
        # up — cannot be read as the trigger's cost.
        order = ("installed", "dropped") if run % 2 == 0 \
            else ("dropped", "installed")
        for state in order:
            _set_rules(state)
            samples[state].append(_one_batch(tenant, customer, rows))
    medians = {state: tuple(statistics.median(timings) / rows
                            for timings in zip(*batches))
               for state, batches in samples.items()}
    # Half the run-to-run range, per statement, taken over both states: the
    # floor below which a delta is not a measurement of anything. Reported
    # rather than left for the reader to infer, because the first version of
    # this script produced a confident-looking negative cost.
    noise = tuple(max((max(timings) - min(timings)) / 2 / rows
                      for timings in pair)
                  for pair in zip(*(zip(*batches)
                                    for batches in samples.values())))
    return medians, noise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=2_000)
    parser.add_argument("--runs", type=int, default=5)
    arguments = parser.parse_args()

    name = connection.creation.create_test_db(verbosity=0, autoclobber=True)
    try:
        results, noise = measure(arguments.rows, arguments.runs)
    finally:
        connection.creation.destroy_test_db(name, verbosity=0)

    print(f"{arguments.rows} rows x {arguments.runs} runs, "
          f"median ms per row")
    print(f"{'':<18}{'insert':>10}{'update':>10}{'settle':>10}"
          f"{'resolve':>10}{'complete':>10}")
    for state, numbers in results.items():
        print(f"  rules {state:<11}" + "".join(f"{n:>10.4f}" for n in numbers))
    print(f"  {'delta':<16}" + "".join(
        f"{installed - dropped:>+10.4f}"
        for installed, dropped in zip(results["installed"], results["dropped"])))
    print(f"  {'noise floor':<16}" + "".join(f"{n:>10.4f}" for n in noise))
    print("\n  A delta inside the noise floor is not a cost — it is this "
          "machine.\n  The insert column runs through `bulk_create` and carries "
          "the ORM's own\n  overhead in both states, so its absolute figure is "
          "not comparable with\n  the four update columns; the delta is. See "
          "`_rows` and the note above it.\n  All three rules are installed and "
          "dropped together (`RULES`), so each\n  permitted move reports its "
          "own rule against a table carrying none of them.\n  `complete` walks "
          "a jsonb record where the other two compare scalars, so it is\n  the "
          "dearest of the three by construction rather than by defect.")


if __name__ == "__main__":
    main()
