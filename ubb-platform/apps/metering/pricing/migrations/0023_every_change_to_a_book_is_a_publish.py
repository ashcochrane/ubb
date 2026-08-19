"""Every change to a Pricing Book is a publish, and a draft is not one (#358).

**The table.** One record per change to a book. It holds the intended changes
while it is a draft, and once published it holds what the publish did: the
instant it took effect, the principal whose decision it was, and the rule
versions it opened and closed. Adding a rule, repricing one and retiring one all
arrive here as kinds of one act, so a tenant asking *"why did this price
change, and who changed it"* has one record to read instead of three surfaces
that each wrote immediately and recorded nothing a reader could join up.

**A NEW TABLE, AND NOTHING IS BACKFILLED INTO IT.** The three immediate routes
survive this commit and keep writing rules with no publish record behind them —
their deletion is a later ticket's, and this migration would otherwise strand
its ledger entries. There is no honest row to invent for a rule already in the
tree: nothing recorded who wrote it or what it superseded, and manufacturing a
publish record saying otherwise would put a fabricated decision on the record
this table exists to make trustworthy. It is moot in practice — UBB is deployed
nowhere and holds no tenant data — and the migrations squash at cutover.

**THE VALUE SET IS A `CHECK`, AND THE TRANSITION IS A TRIGGER.** They are
different claims and they need different mechanisms:

* `ck_book_publish_declaration_status` says a row's status is one of the two the
  registry closed. A `CHECK` is evaluated against one row, which is exactly what
  a value set needs and all it can do — it cannot see `OLD` at all.
* The trigger says what may happen to a row that already exists. A `CHECK`
  cannot tell publishing a draft from editing a published record, because both
  are one legal row; that distinction is the whole of what `RESOLVE_ONCE` means
  and it needs `OLD`.

**ONE RULE, NOT TWO, AND THE ONE IS THE RECORD'S.** *Once `declaration_status`
is `published`, no column may change, ever.* That single sentence is what makes
the status resolve-once as well: `published` cannot be left, so it cannot be
entered twice. A second branch refusing "draft to anything but published" was
written and removed — within the closed set it is unreachable, since `published`
is the only other value, and outside it the `CHECK` above is the mechanism. A
branch that refuses nothing is how a rule comes to look enforced while holding
nothing (#325 measured exactly that), and two mechanisms over one condition is
how they come to disagree.

**Why `BEFORE UPDATE` and why a trigger at all**, on the ground `0018` on the
rule's own table and `0037` on the posting both state at length: a trigger sees
`OLD` and `NEW`, fires for every door — `save()`, `QuerySet.update()`, a data
migration, `psql` — and refuses before the write rather than unwinding one.
ADR-0007 §2 is explicit that a model-level guard is not enforcement.

**INSERTS PAY NOTHING, AND SO DOES THE RECORDING PATH.** The trigger is `BEFORE
UPDATE` only and its `WHEN` clause fires only for a row that is already
published, so declaring a draft, editing one, discarding one and publishing one
all skip it entirely. Metering never touches this table at all: it is written
when a human changes a price.

⚠ **`DELETE` IS NOT IN THE RULE, DELIBERATELY.** Discarding a draft is a
`DELETE`, and refusing one against a published record would read as the natural
other half of "immutable once published". It is not takeable here: a
`BEFORE DELETE` trigger cannot tell a discard from a cascade — at trigger time
the parent is still on disk — and a tenant wipe deletes every row this table
holds (#354 paid for exactly that mechanism, in the other direction). The route
that discards is what refuses a published record, and it can, because it knows
which act it is performing.

**No vendor guard**, on the ground `0018` and `0037` both state: this is the
enforcement half of a declaration the model makes, not an optimisation, and a
guard would encode a fallback in which the promise is made and nothing keeps it.

**The refusal is SQLSTATE 23000**, `integrity_constraint_violation`, the class
Django maps to `IntegrityError` — the same exception the table's `CHECK` raises,
because a caller has no business caring which mechanism held the line. The
*message* is what distinguishes them, and every test of this rule asserts the
column and the transition class by name rather than merely that something
refused.

**The reverse is real.** Dropping the trigger and its function, then the table,
returns the schema to what `0022` left. Nothing has to be unpicked: nothing else
references this table and no existing row is touched.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models

TRIGGER = "trg_book_publish_declared_transitions"
FUNCTION = "ubb_book_publish_declared_transitions"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- declaration_status is declared RESOLVE_ONCE, and this is the record rule
    -- that makes it so: a published record is what a decision did to a book on
    -- a day, and every column of it is fixed at that moment. A draft is
    -- untouched by this function -- the WHEN clause below never lets one in --
    -- which is what "freely editable, freely discardable" means.
    IF OLD.declaration_status = 'published' THEN
        RAISE EXCEPTION
            'declaration_status is declared resolve_once (ADR-0007 §2): a '
            'published pricing book publish records the decision that put a '
            'price in force, so no column of it moves afterwards -- including '
            'this one, which cannot return to draft; got status % to %',
            OLD.declaration_status, NEW.declaration_status
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_pricing_book_publish
FOR EACH ROW
WHEN (OLD.declaration_status = 'published')
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_pricing_book_publish;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0022_the_tenant_declares_its_default_markup_rung'),
        ('tenants', '0024_remove_tenant_require_cost_card_coverage'),
    ]

    operations = [
        migrations.CreateModel(
            name='PricingBookPublish',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('declaration_status', models.CharField(db_index=True, default='draft', max_length=32)),
                ('effective_at', models.DateTimeField(db_index=True)),
                ('changes', models.JSONField(default=list)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('actor_kind', models.CharField(blank=True, default='', max_length=32)),
                ('actor_id', models.CharField(blank=True, default='', max_length=255)),
                ('actor_display', models.CharField(blank=True, default='', max_length=255)),
                ('opened_rule_ids', models.JSONField(default=list)),
                ('closed_rule_ids', models.JSONField(default=list)),
                ('book', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='publishes', to='pricing.ratecard')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pricing_book_publishes', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_pricing_book_publish',
                'indexes': [models.Index(fields=['book', 'declaration_status'], name='idx_book_publish_pending')],
                'constraints': [models.CheckConstraint(condition=models.Q(('declaration_status__in', ['draft', 'published'])), name='ck_book_publish_declaration_status')],
            },
        ),
        migrations.RunPython(install, uninstall),
    ]
