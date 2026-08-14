"""What the declared-transition trigger costs per insert and per update (#318).

ADR-0007's Consequences ask for this by name, of this decision specifically:

    Database-enforced transitions have a per-insert and per-update cost on the
    hottest path in the system. Which mechanism carries them — triggers, CHECK
    constraints, rules — is an implementation decision, and its cost should be
    measured rather than assumed.

So this measures it, against the mechanism actually installed, on a throwaway
database of its own. Three statements are timed, with the trigger installed and
again with it dropped, each the median of `--runs` batches of `--rows`:

    insert      a posting, the hottest write in the system
    update      a column the rule says nothing about — the ordinary write
    settlement  unresolved to known, the one statement the rule admits

**The insert number is the one to read first.** The trigger is `BEFORE UPDATE`,
so an insert should pay nothing at all; a number that says otherwise means the
enforcement is not the shape `usage/migrations/0037` claims.

**The unrelated-column update is where a badly-built rule would show up.** It is
the ordinary write on this table, and it is why the migration puts a `WHEN`
clause on the trigger: without one, every update on the table would enter a
`plpgsql` function to discover it had nothing to say. That number should be flat
too.

**The settlement is the only statement that should pay**, and it happens once
per posting in a remediation path. A rule that made it measurably slower would
still be worth having; a rule that made recording slower would not.

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

from core.vocabulary import (  # noqa: E402
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

TRIGGER = "trg_posting_declared_transitions"

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


def _rows(tenant, customer, rows, *, unresolved):
    """Unsaved postings, built OUTSIDE the timer that inserts them.

    Fresh each batch: `bulk_create` stamps primary keys onto the instances it
    is given, so a reused list would insert the same rows twice.
    """
    from apps.metering.usage.models import Posting

    cost = dict(
        provider_cost_micros=None,
        costing_status=COSTING_STATUS_UNRESOLVED,
        unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING) if unresolved \
        else dict(provider_cost_micros=1, costing_status=COSTING_STATUS_KNOWN)
    return [Posting(tenant=tenant, customer=customer,
                    idempotency_key=str(index), **cost)
            for index in range(rows)]


def _insert(postings):
    from apps.metering.usage.models import Posting

    Posting.objects.bulk_create(postings)


def _update_batch():
    _execute(UNRELATED_UPDATE)


def _settle_batch():
    _execute(SETTLEMENT)


def _trigger_is_installed():
    """Asked BY NAME, not by counting triggers on the table.

    Slice 4 declares its own columns on this table and may well install a second
    rule beside this one; a count would then answer "installed" for a table this
    script had just stripped, and every number below would be a measurement of
    nothing.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger t JOIN pg_class c "
            "ON c.oid = t.tgrelid "
            "WHERE c.relname = 'ubb_posting' AND t.tgname = %s", [TRIGGER])
        return cursor.fetchone()[0] > 0


def _set_trigger(state):
    """Install or drop **the shipped SQL**, imported from the migration itself.

    A copy of the trigger written out here would measure whatever this script
    happened to say rather than what the table actually carries.
    """
    migration = importlib.import_module(
        "apps.metering.usage.migrations"
        ".0037_a_cost_settles_once_and_the_table_holds_it")
    if state == "installed" and not _trigger_is_installed():
        _execute(migration.INSTALL)
    elif state == "dropped" and _trigger_is_installed():
        _execute(migration.UNINSTALL)
    assert _trigger_is_installed() == (state == "installed"), state


def _one_batch(tenant, customer, rows):
    """Three timings, each over a table that starts empty and unbloated.

    `TRUNCATE`, not `DELETE`: repeated deletes leave dead tuples behind, and the
    state measured second then pays for the state measured first. That is not a
    hypothetical — it is what the first version of this script reported, as a
    trigger that made every statement *faster*.
    """
    _execute("TRUNCATE ubb_posting CASCADE")
    known = _rows(tenant, customer, rows, unresolved=False)
    insert = _timed(lambda: _insert(known))
    update = _timed(_update_batch)

    _execute("TRUNCATE ubb_posting CASCADE")
    _insert(_rows(tenant, customer, rows, unresolved=True))
    settle = _timed(_settle_batch)
    return insert, update, settle


def measure(rows, runs):
    tenant, customer = _tenant_and_customer()
    samples = {"installed": [], "dropped": []}
    for run in range(runs):
        # Alternated, so that a machine drifting under load — or a table warming
        # up — cannot be read as the trigger's cost.
        order = ("installed", "dropped") if run % 2 == 0 \
            else ("dropped", "installed")
        for state in order:
            _set_trigger(state)
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
    print(f"{'':<18}{'insert':>10}{'update':>10}{'settle':>10}")
    for state, numbers in results.items():
        print(f"  trigger {state:<9}" + "".join(f"{n:>10.4f}" for n in numbers))
    print(f"  {'delta':<16}" + "".join(
        f"{installed - dropped:>+10.4f}"
        for installed, dropped in zip(results["installed"], results["dropped"])))
    print(f"  {'noise floor':<16}" + "".join(f"{n:>10.4f}" for n in noise))
    print("\n  A delta inside the noise floor is not a cost — it is this "
          "machine.\n  The insert column runs through `bulk_create` and carries "
          "the ORM's own\n  overhead in both states, so its absolute figure is "
          "not comparable with\n  the two update columns; the delta is. See "
          "`_rows` and the note above it.")


if __name__ == "__main__":
    main()
