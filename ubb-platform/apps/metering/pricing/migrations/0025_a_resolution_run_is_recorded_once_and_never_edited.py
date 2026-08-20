"""A Resolution Run is recorded once, and the record is never edited (#363).

A run completes fields a posting recorded as unresolved. Under the receipt's
sealing rule (`usage/migrations/0040`) that completion happens **exactly once**
and the receipt is sealed after it, so a run is **irreversible**: there is no
second act to undo one with. This row is therefore the only surviving
explanation of an irreversible, money-adjacent act — who ran it, what they
pointed it at, and what it completed — and a record that could be edited
afterwards would make that traceability a claim rather than a fact.

**THE RULE IS THE WHOLE RECORD AND NOT A COLUMN, WHICH IS WHY IT IS NOT A
TRANSITION CLASS.** ADR-0007 §2's four classes each say what one column may
become; here the answer is the same for every column and it is *nothing*.
`ResolutionRun.transition_classes` declares `RECORD_RULE` throughout — the
absence of a class, said out loud — and this is what governs instead. Declaring
sixteen `FROZEN` columns would be one claim written sixteen times, and G19's
walk would then require each column to be **named** by a rule on the table,
which a blanket refusal deliberately does not do: it refuses every update
whatever it touched, so there is nothing to name.

**A BLANKET `BEFORE UPDATE` REFUSAL, WITH NO `WHEN` CLAUSE.** The sibling rules
on `ubb_posting` carry one because they admit a permitted move and pay only for
statements that could be it. This admits none, so a `WHEN` clause could only
restate `TRUE` — and a condition that is always true is a condition somebody
will later read as a filter. Inserts pay nothing: `BEFORE UPDATE` never fires on
one, which is also why the shape does not tax the act it records.

**IT IS NOT A REPLACEMENT FOR THE SEALING RULE AND DOES NOT OVERLAP IT.** What
seals is the receipt, on `ubb_posting`, and what is refused here is an edit to
the record of the act. The two are different tables and different subjects: one
keeps a historical price from becoming a different historical price, the other
keeps the explanation of who changed it from being rewritten.

**Why there is no vendor guard**, when the neighbouring raw-SQL migrations in
this app guard on `connection.vendor`: those install indexes, which are
optimisations a backend without them still holds the data correctly for. This is
the enforcement half of a declaration the model makes, and a guard would encode
a fallback in which the promise is made and nothing keeps it — the precise state
`apps/platform/tests/test_transition_class_declarations.py` exists to refuse.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
the class Django maps to `IntegrityError` — the same exception the sealing rules
and the tables' `CHECK`s raise, because a caller has no business caring which
mechanism held the line. The message names this record, so a refusal on a page
touching several tables says which one refused.

**The reverse is real and it is total.** Dropping the trigger and its function
returns the table to an ordinary one; the table itself goes with the model in the
same reverse, and nothing has to be unpicked because the rule wrote no row.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models

TRIGGER = "trg_resolution_run_is_never_edited"
FUNCTION = "ubb_resolution_run_is_never_edited"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'a resolution run is recorded once and never edited: it is the record '
        'of an irreversible act, and the only surviving explanation of the '
        'numbers it completed; a correction belongs in a record beside it'
        USING ERRCODE = '23000';
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_resolution_run
FOR EACH ROW
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_resolution_run;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0014_customer_suspension_reason'),
        ('pricing', '0024_a_customer_override_replaces_a_whole_rule'),
        ('tenants', '0024_remove_tenant_require_cost_card_coverage'),
    ]

    operations = [
        migrations.CreateModel(
            name='ResolutionRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('actor_kind', models.CharField(blank=True, default='', max_length=32)),
                ('actor_id', models.CharField(blank=True, default='', max_length=255)),
                ('actor_display', models.CharField(blank=True, default='', max_length=255)),
                ('selected_from', models.DateTimeField(blank=True, null=True)),
                ('selected_to', models.DateTimeField(blank=True, null=True)),
                ('selected_event_type', models.CharField(blank=True, default='', max_length=100)),
                ('postings_examined', models.PositiveIntegerField(default=0)),
                ('costs_settled', models.PositiveIntegerField(default=0)),
                ('prices_resolved', models.PositiveIntegerField(default=0)),
                ('postings_left_unresolved', models.PositiveIntegerField(default=0)),
                ('more_to_do', models.BooleanField(default=False)),
                ('selected_customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='resolution_runs', to='customers.customer')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='resolution_runs', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_resolution_run',
                'indexes': [models.Index(fields=['tenant', 'created_at'], name='idx_resolution_run_tenant')],
            },
        ),
        migrations.RunPython(install, uninstall),
    ]
