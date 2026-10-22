"""An agreed price becomes a line the publish act opens and closes (#553).

Until now nothing wrote `ubb_task_price`: the publish act's change body
required the quantity a line prices, which a whole-work line does not have, so
the table had a resolver and no declaration. The change body is now a union on
`line` (`api/v1/schemas.py`), and this migration gives the line what a publish
needs to record on it — the four things the rate side already carries.

* **The money column takes the public name**, `agreed_price_micros` — the field
  the change body, the diff, the read and the unit of work that pins it all
  publish, so one name runs from the declaration to the Charge. Its CHECK is
  re-made under the matching name; zero stays a price and a negative amount
  stays refused.
* **Provenance and lineage**, `book_version_from` / `book_version_to` /
  `lineage_id`, exactly the rate side's: which publish opened a line, which
  closed it, and which line it continues. Existing lines (none outside a test
  or a developer's database — UBB is not deployed) are given one lineage per
  `(book, altitude, kind of work)`, oldest first, the identity a reprice keeps.
* **The publish record lists what it opened and closed** in a pair of its own,
  `opened_agreed_price_ids` / `closed_agreed_price_ids`, so "rule" keeps
  meaning a rate on the two lists beside them. The record's whole-record
  trigger (`0023`) already covers both: it refuses every column of a
  published record.
* **A draft declared before a change named its line is given `line: rate`**,
  which is what every one of its changes was; otherwise the planner refuses
  the draft whole. A published record is history and is left as it was.
* **The window is declared and held**, as `0018` holds the rate's:
  `valid_from` FROZEN and `valid_to` SET_ONCE, by a `BEFORE UPDATE … FOR EACH
  ROW` trigger whose `WHEN` clause lets no other write in. `0018` argues the
  mechanism at length — a `CHECK` cannot see `OLD`, a rule rewrites rather than
  judges — and this is the same function body over this table's two columns,
  raising SQLSTATE 23000 and naming the class it enforces.

**The reverse is real.** It drops the trigger, takes `line: rate` back off
every draft, re-makes the old CHECK, drops the five columns and renames the money
column back.
"""

import uuid

from django.db import migrations, models

TRIGGER = "trg_task_price_declared_transitions"
FUNCTION = "ubb_task_price_declared_transitions"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- valid_from is declared FROZEN: when an agreed price took effect is a
    -- fact about the line, and the publish that opened it says so.
    IF NEW.valid_from IS DISTINCT FROM OLD.valid_from THEN
        RAISE EXCEPTION
            'valid_from is declared frozen (ADR-0007 §2): when an agreed price '
            'took effect is a fact about the line its publish recorded, and '
            'moving it rewrites which price was in force; got % to %',
            OLD.valid_from, NEW.valid_from
            USING ERRCODE = '23000';
    END IF;

    -- valid_to is declared SET_ONCE: nothing to a moment, once. Reopening a
    -- line, or moving its close, both land here.
    IF NEW.valid_to IS DISTINCT FROM OLD.valid_to
       AND OLD.valid_to IS NOT NULL THEN
        RAISE EXCEPTION
            'valid_to is declared set_once (ADR-0007 §2): closing an agreed '
            'price is a one-way act, and reopening one rewrites history '
            'rather than editing it; got % to %',
            OLD.valid_to, NEW.valid_to
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_task_price
FOR EACH ROW
WHEN (OLD.valid_from IS DISTINCT FROM NEW.valid_from
      OR OLD.valid_to IS DISTINCT FROM NEW.valid_to)
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_task_price;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


def one_lineage_per_identity(apps, schema_editor):
    """Each existing line its lineage: one per `(book, altitude, kind of
    work)`, the identity a reprice continues, oldest line first."""
    TaskPrice = apps.get_model("pricing", "TaskPrice")
    lineages = {}
    for line in TaskPrice.objects.order_by("valid_from", "created_at"):
        identity = (line.pricing_book_id, line.kind, line.task_type)
        TaskPrice.objects.filter(pk=line.pk).update(
            lineage_id=lineages.setdefault(identity, uuid.uuid4()))


#: The status a publish record holds until it is published, and the one line
#: every change was before a change could name its line. Spelled here, as a
#: migration spells the values it rewrites: it describes the schema at this
#: point, not whatever the registry says later.
DRAFT = "draft"
RATE = "rate"


def every_draft_names_its_line(apps, schema_editor):
    """A draft declared before a change named its line holds rate changes only
    — a rate was the one line a book held — so each is given `line: rate`, or
    the planner would refuse every one of them and the draft could neither be
    read as a diff nor published: a state nothing may be left in.

    Only drafts. A PUBLISHED record is history, its whole-record trigger
    (`0023`) keeps it as it was, and nothing plans it again."""
    PricingBookPublish = apps.get_model("pricing", "PricingBookPublish")
    for draft in PricingBookPublish.objects.filter(declaration_status=DRAFT):
        named = [change if "line" in change else {"line": RATE, **change}
                 for change in draft.changes]
        if named != draft.changes:
            PricingBookPublish.objects.filter(pk=draft.pk).update(
                changes=named)


def no_draft_names_its_line(apps, schema_editor):
    """The reverse: the body before this migration had no `line` field, so a
    rate change loses the one the forward gave it. An agreed-price change has
    no shape before this migration at all, and keeps its line — taking it off
    would make the forward name it a rate."""
    PricingBookPublish = apps.get_model("pricing", "PricingBookPublish")
    for draft in PricingBookPublish.objects.filter(declaration_status=DRAFT):
        unnamed = [{name: value for name, value in change.items()
                    if (name, value) != ("line", RATE)}
                   for change in draft.changes]
        if unnamed != draft.changes:
            PricingBookPublish.objects.filter(pk=draft.pk).update(
                changes=unnamed)


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0031_a_delivered_piece_of_work_is_charged_once'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='taskprice',
            name='ck_task_price_amount_not_negative',
        ),
        migrations.RenameField(
            model_name='taskprice',
            old_name='amount_micros',
            new_name='agreed_price_micros',
        ),
        migrations.AddConstraint(
            model_name='taskprice',
            constraint=models.CheckConstraint(
                condition=models.Q(agreed_price_micros__gte=0),
                name='ck_task_price_agreed_price_not_negative'),
        ),
        migrations.AddField(
            model_name='taskprice',
            name='book_version_from',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='taskprice',
            name='book_version_to',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='taskprice',
            name='lineage_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4,
                                   editable=False),
        ),
        migrations.RunPython(one_lineage_per_identity,
                             migrations.RunPython.noop),
        migrations.AddField(
            model_name='pricingbookpublish',
            name='opened_agreed_price_ids',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='pricingbookpublish',
            name='closed_agreed_price_ids',
            field=models.JSONField(default=list),
        ),
        migrations.RunPython(every_draft_names_its_line,
                             no_draft_names_its_line),
        migrations.RunPython(install, uninstall),
    ]
