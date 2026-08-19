"""The child measurement record starts refusing a prune it may not have (#354).

The posting / measurement split (2026-08-03) gave this record a **whole-record
rule** rather than per-column transition classes, on the ground that it has no
per-column lifecycle to describe::

    INSERT   once, in the same transaction as its posting
    UPDATE   never — no column of a measurement record is ever rewritten
    DELETE   permitted only at or after prunable_at, and only while the
             parent posting is not unresolved

**This migration installs the third line and only the third line.** It is the
one that decision called *"a cross-table condition on a `DELETE`, evaluated
against the parent's `costing_status`/`pricing_status`"*, and the reason it
could not be written until now is in that sentence: the second of the two
statuses it reads landed three migrations ago, in `0038`.

⚠ **NOTHING COUNTS THIS RULE.** It has no entry in the migration ledger and no
row in the gate manifest, and slice 4 owns no manifest row at all — so no number
moves, no allowlist shrinks and no tripwire fires whether this file exists or
not. The tests in
`apps/metering/usage/tests/test_a_measurement_is_pruned_only_when_it_may_be.py`
are the whole of the check on it.

**WHY THIS IS NOT GATE G19, AND WHY IT NONETHELESS EXTENDS IT.** G19's statement
is about *field* transition classes. Every column of this record is declared
`RECORD_RULE`, which `core/transitions.py` places outside `DATABASE_DEFENDED`,
so the declaration walk reaches nothing here and declaring a column into a
defended class to make it notice would be a false statement about that column.
What G19's notes did carry was this obligation, deferred **by name**; this is
its extension, and G19's row keeps its statement, its status and its enforcement
nodes.

**WHY A TRIGGER, AND WHY ON THIS TABLE.** A `CHECK` cannot see a `DELETE` at
all, so it cannot judge one. A model-level `delete()` override is not
enforcement — ADR-0007 §2 says so, the split decision refuses one for this
record by name, and two of the three doors ADR-0007 §2 names never load a model
instance. And it is a rule of this table rather than a fourth rule on
`ubb_posting`: the parent's three rules are `BEFORE UPDATE` triggers over
declared columns, and folding a cross-table lookup into the hottest update path
in the system to judge a statement that path never issues would be paid for on
every settlement forever.

**THE COST TO THE HOT PATH IS ZERO BY CONSTRUCTION, NOT BY MEASUREMENT.**
ADR-0007's Consequences require a database-enforced transition's per-insert and
per-update cost to be measured rather than assumed. A `BEFORE DELETE` trigger
cannot fire on an `INSERT` or an `UPDATE`; the recording path inserts into this
table on every metered call and deletes from it never, so there is no number to
take. `test_it_fires_before_each_deleted_row_and_on_nothing_else` reads the
statement mask out of `pg_trigger` and holds it there, which is a stronger claim
than a benchmark reporting a small number and one that cannot drift.

**THERE IS NO `WHEN` CLAUSE**, unlike all three rules on the parent table. Those
fire only when a declared column moves, which is what keeps an unrelated update
out of their bodies. Here every `DELETE` is exactly the statement under
judgement, so a `WHEN` clause could only ever exempt one.

**THE FIRST CONDITION REFUSES A NULL HORIZON, WHICH IS EVERY ROW IN THE TREE
TODAY.** `prunable_at` ships with no clock behind it — no job, no schedule, no
owner, no default — and the column's own comment says a clock nobody has decided
must not be started by accident. `prunable_at` names *the moment a permission
begins*, so no value is no permission, and the alternative reading (no horizon
means prune whenever) would have this rule admit every record in the system on
the day it shipped.

**⚠ THE SECOND CONDITION IS "NOT UNRESOLVED" AND DELIBERATELY NOT "IS
RESOLVED".** `waived` and `not_applicable` on the price side and
`not_applicable` on the cost side all carry a NULL amount exactly as the two
unresolved statuses do, so the amount cannot tell a decision somebody made from
information UBB is missing. Only the status can — and only
`costing_status = 'unresolved'` and `pricing_status = 'unknown'` mean UBB is
missing something, which is exactly the one status per pair that
`core.amount_status_pairs` names as that pair's `unresolved_status`. A predicate
written as *is resolved* would hold a waived posting's measurements forever, for
a resolution that is never coming.

⚠ **That is the opposite direction from the three rules on the parent table**,
which whitelist the one completable status precisely so that a waived charge
cannot be turned into a charged amount. The difference is what each predicate is
*for*: a transition rule asks whether a write may happen and must not admit one
it has no positive reason to admit; this one asks whether anything still needs
the record, and a decision already taken is not a need.

**⚠⚠ THE THIRD CONDITION IS NOT IN THE TICKET, AND IT IS HERE BECAUSE THE
TICKET'S TWO WOULD BRICK `reset_sandbox_tenant`.** A sandbox reset
(`apps/platform/tenants/tasks.py`) hard-deletes a sandbox tenant's customers,
which cascades to its postings and — because Django's collector deletes a child
before its parent — issues a `DELETE` against this table for every measurement
the sandbox ever recorded. Every one of those rows has a NULL horizon and many
belong to unresolved postings, so the ticket's predicate refuses the lot; the
task's per-label handler collects the failures and raises, leaving the sandbox
tenant `is_active = False` and unable to serve traffic. **No existing test would
have caught it**: every sandbox fixture builds its postings with
`Posting.objects.create` and therefore has no measurement children at all.

The rule's subject is **pruning** — removing the detail while the durable
economic record survives it — and neither obligation it protects exists for a
sandbox. The six-year retention promise and the recovery obligation are
statements about real customer money; a sandbox is a sibling tenant row whose
keys are `ubb_test_`, whose whole purpose is disposable traffic, and which the
product offers a button to reset. So the condition is stated as what it is,
positively and in the rule, rather than hidden behind a session setting or a
temporary drop — both of which would be doors, and ADR-0007 §2's whole point is
that a rule holds through every door.

The alternative considered and rejected was to condition on *the posting itself
going away*, which is what a discard actually is and would need no proxy. It is
not expressible here: Django's collector deletes the child first, so at the
moment this trigger runs the parent is still on disk, and the only mechanisms
that could see the difference — a `DEFERRABLE INITIALLY DEFERRED` constraint
trigger firing at commit, or moving the cascade into the database by giving the
foreign key `ON DELETE CASCADE` and Django `DO_NOTHING` — are respectively a
refusal that arrives far from its cause and never fires under a `TestCase`, and
a change to what deleting a posting means everywhere. Both are bigger decisions
than this rule, and both belong in a ticket that argues for them.

**How far the guard on that condition actually goes**, stated at its real
width. `ck_sandbox_iff_parent` on `ubb_tenant` holds `is_sandbox` to *sandbox if
and only if it has a parent tenant*, so a live tenant cannot acquire this
exemption by having one boolean set on it — and the same constraint would admit
`is_sandbox` written together with a `parent_tenant`. What that buys is not
unreachability but identity: a row taking this exemption has to become a sandbox
OF some parent, whose keys are `ubb_test_` and for whom
`uq_one_sandbox_per_parent` allows exactly one. Both halves have a test, because
a claim that the exemption had no door at all would be wrong in the direction
this programme keeps paying for.

**THE TOKENS BELOW ARE LITERALS AND THE REGISTRY'S ARE NOT.** `unresolved` and
`unknown` are frozen into the function body for the reason `0036` gives at
length: a migration records the schema as it was on the day it ran, and
importing living constants into a frozen file makes replay depend on today's
registry. What keeps the copy honest is a test rather than this file —
`test_the_rule_names_the_statuses_the_registry_declares` reads the installed
function's source out of `pg_proc`, strips its comments, and asserts each token
**joined to its own column** against `core.amount_status_pairs`.

**Each refusal names its own cause**, and that is not decoration: two conditions
sharing one mechanism means *"something refused this"* stops being evidence, and
the mutation test that removes each condition's cause in turn needs the two
refusals to stay tellable apart. The class is raised as SQLSTATE 23000,
`integrity_constraint_violation`, which is what Django maps to `IntegrityError`
— the same exception the constraints beside it raise, because a caller has no
business caring which mechanism held the line.

**The reverse is real and total.** Dropping this trigger and its function
returns the table to what `0031` left, which is a table whose child records come
away under any `DELETE` at all. Nothing has to be unpicked because nothing was
written: this migration adds no column and moves no row.
"""

from django.db import migrations

TRIGGER = "trg_posting_measurement_pruning"
FUNCTION = "ubb_posting_measurement_pruning"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_is_sandbox   boolean;
    parent_costing_status text;
    parent_pricing_status text;
BEGIN
    -- The parent, read once. The foreign key makes exactly one row certain, and
    -- the collector deletes this child before its posting, so the row is on
    -- disk here even when the whole posting is on its way out.
    SELECT t.is_sandbox, p.costing_status, p.pricing_status
      INTO parent_is_sandbox, parent_costing_status, parent_pricing_status
      FROM ubb_posting p
      JOIN ubb_tenant t ON t.id = p.tenant_id
     WHERE p.id = OLD.posting_id;

    -- A sandbox carries neither obligation this rule protects: not the
    -- six-year retention promise and not the recovery a resolution run makes,
    -- both of which are statements about real customer money. Its reset button
    -- discards the tenant's postings wholesale, and discarding is not pruning.
    IF parent_is_sandbox THEN
        RETURN OLD;
    END IF;

    -- prunable_at names the moment a permission BEGINS, so an instant nobody
    -- has named is not one that has passed. Every row in the tree carries NULL
    -- here today, and no job, schedule or owner sets it.
    IF OLD.prunable_at IS NULL OR now() < OLD.prunable_at THEN
        RAISE EXCEPTION
            'ubb_posting_measurement is governed by a whole-record rule '
            '(ADR-0007 §2): a measurement may be pruned only at or after its '
            'prunable_at, and this one is %',
            COALESCE('due ' || OLD.prunable_at::text, 'not released by any clock')
            USING ERRCODE = '23000';
    END IF;

    -- NOT UNRESOLVED, rather than IS RESOLVED. Three of this posting's statuses
    -- carry a null amount because somebody decided something (waived,
    -- not_applicable on either side) and two because UBB is missing
    -- information; only the second kind is what a resolution run still needs
    -- these quantities for.
    IF parent_costing_status = 'unresolved'
       OR parent_pricing_status = 'unknown' THEN
        RAISE EXCEPTION
            'ubb_posting_measurement is governed by a whole-record rule '
            '(ADR-0007 §2): a measurement may be pruned only while its posting '
            'is not unresolved; costing_status is % and pricing_status is %',
            parent_costing_status, parent_pricing_status
            USING ERRCODE = '23000';
    END IF;

    RETURN OLD;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE DELETE ON ubb_posting_measurement
FOR EACH ROW
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_posting_measurement;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0040_a_receipt_seals_when_its_unresolved_fields_complete"),
        # The rule reads `ubb_tenant.is_sandbox`, so the table carrying it must
        # exist before this trigger is created. Named rather than assumed: the
        # usage app's own chain says nothing about the tenants app's.
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(install, uninstall),
    ]

