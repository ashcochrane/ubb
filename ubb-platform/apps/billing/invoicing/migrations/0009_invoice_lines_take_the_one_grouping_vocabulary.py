"""A tenant's invoice-line grouping becomes an axis of the one vocabulary (#503).

`PostpaidUsageConfig.usage_line_item_group_by` held a free-text key — the third
of ADR-0005's ad-hoc label reads, the sharpest of its three free-text hatches,
and the only one a paying customer reads. Slice 7 §11 replaces it with one axis
of the SAME vocabulary every chart uses, so the column is renamed to say what it
now holds and its stored values are carried onto the new words.

**HAND-WRITTEN, AND `RenameField` RATHER THAN AN ADD PLUS A REMOVE**, on
`0008_the_usage_line_names_its_grouped_value`'s reasoning: run without a TTY
`makemigrations` never asks *did you rename this?* and emits `AddField` plus
`RemoveField`, which on a populated table adds an empty column beside the full
one and then drops the full one — every tenant's invoice grouping, gone.

**WHAT EACH OLD VALUE ACTUALLY DID IS WHAT IT IS CARRIED TO**, and the two
readings are not the same fact:

* ``""`` grouped nothing. It still does, and it is left alone.
* ``"tag:<key>"`` read the free-form bag. #273 closed that hatch for grouping —
  the surviving bag is filterable and readable but **never groupable** — so the
  axis it named does not exist in the new vocabulary. Where the tenant has since
  DECLARED a grouping field of the same name, that declaration is what they meant
  and the value becomes ``field:<key>``. Where they have not, there is no axis to
  carry it to and the value is cleared: one line per period, which is a legible
  invoice the tenant can re-group deliberately, rather than a heading UBB
  invented for them.
* **Anything else meant the first slot**, whatever it spelled — the silent
  fall-through `apps/metering/usage/tests/test_the_second_open_bag_folds.py`
  recorded as a slice-7-owned defect rather than repairing it there. So it is
  carried to the axis that column really is: ``field:<the key declared at
  grouping_field_1>``, or cleared where no key is bound to that slot, because a
  declaration is what makes a column an axis.

⚠ **THE AXIS WORDS ARE SPELLED AS LITERALS HERE.** A migration is frozen history
and may not follow a constant that later moves; `apps.metering.queries.
grouping_axis` is the living spelling and this file is a snapshot of it.

**Reversible, and the reverse is honest about what it cannot restore.** Going
back renames the column and leaves the carried values in it — a `field:` word
is exactly the *anything else* the old reader mapped to the first slot, which is
the column those values came from. The bag reading is not restored, because
nothing records which values were once bag keys.

**Nothing published moves.** `PostpaidConfigIn`/`PostpaidConfigOut` keep their
field names, which the composition layer maps onto this column; renaming those
is phase B2's (§21), so `openapi/v1.json` regenerates byte-identical here.
"""

from django.db import migrations

#: The kind prefix and separator, frozen at this migration (see the note above).
FIELD_AXIS = "field:"
#: The bag prefix the retired reader recognised, frozen for the same reason.
BAG_PREFIX = "tag:"
#: The slot the retired reader fell through to.
FIRST_SLOT = "grouping_field_1"


def _carry_onto_the_one_vocabulary(apps, schema_editor):
    PostpaidUsageConfig = apps.get_model("invoicing", "PostpaidUsageConfig")
    GroupingField = apps.get_model("grouping_fields", "GroupingField")

    for config in PostpaidUsageConfig.objects.exclude(invoice_line_grouping=""):
        stored = config.invoice_line_grouping
        declared = GroupingField.objects.filter(tenant_id=config.tenant_id)
        if stored.startswith(BAG_PREFIX):
            key = stored[len(BAG_PREFIX):]
            match = declared.filter(key=key).first()
        else:
            match = declared.filter(slot=FIRST_SLOT).first()
        config.invoice_line_grouping = (
            f"{FIELD_AXIS}{match.key}" if match is not None else "")
        config.save(update_fields=["invoice_line_grouping"])


def _leave_the_carried_values_where_they_are(apps, schema_editor):
    """The reverse: the rename is undone by `RenameField` and the values stay.

    Deliberately not a restoration. A `field:<key>` word is exactly what the old
    reader treated as *anything else* and mapped to the first slot — the column
    those values were carried off — so a reversed tenant groups by the column
    they were grouping by. What cannot come back is the bag reading, because
    nothing here records which values were once bag keys, and inventing one
    would be a worse answer than the honest no-op.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("invoicing", "0008_the_usage_line_names_its_grouped_value"),
        # The carry reads the tenant's declared axes, so the registry's table
        # must exist. A product migration depending on the kernel is the
        # permitted direction (ADR-001); the reverse is not.
        ("grouping_fields", "0004_the_stored_slot_identifier_takes_the_canonical_noun"),
    ]

    operations = [
        migrations.RenameField(
            model_name="postpaidusageconfig",
            old_name="usage_line_item_group_by",
            new_name="invoice_line_grouping",
        ),
        migrations.RunPython(_carry_onto_the_one_vocabulary,
                             _leave_the_carried_values_where_they_are),
    ]
