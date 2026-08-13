"""The usage invoice line's grouped value takes the canonical noun (#312).

`UsageInvoiceLineItem.dimension` held the label a period's usage was grouped
under before it was pushed to Stripe — the value of whichever axis
`TenantBillingConfig.usage_line_item_group_by` names. That is the same thing the
three analytics rollups call `grouping_field_value`, and this commit makes the
last of them say so, so the column that stores it says so too.

**HAND-WRITTEN, AND `RenameField` RATHER THAN AN ADD PLUS A REMOVE.** ADR-0007 §1
refuses the shape `makemigrations` produces here: run without a TTY it never asks
"did you rename this?", and emits `AddField` plus `RemoveField`, which on a
populated table adds an empty column beside the full one and then drops the full
one — every line label on every pushed invoice, gone. `RenameField` is a rename
in the database's own terms (`ALTER TABLE ... RENAME COLUMN`), reversible by
construction, and carries the rows with it.

**Nothing published moves.** The column is internal: written in one place —
`PostpaidUsageService.push_customer_period`'s Phase 3, where the Stripe line
items are recorded — read by this app's own tests, and by nothing else. It is
declared in no schema and returned by no route, so `openapi/v1.json` regenerates
byte-identical and the contract's drift and breaking gates have nothing to see.
That is the whole reason a real column could be renamed in a commit that
otherwise moves only prose.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("invoicing", "0007_consolidated_postpaid"),
    ]

    operations = [
        migrations.RenameField(
            model_name="usageinvoicelineitem",
            old_name="dimension",
            new_name="grouping_field_value",
        ),
    ]
