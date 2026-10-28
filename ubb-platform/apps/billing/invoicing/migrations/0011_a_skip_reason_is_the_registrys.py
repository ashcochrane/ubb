"""A usage invoice's skip reason is the registry's closed `skip_reason` (R10-W4).

It was a bare string written as literals by the postpaid service, and every
invoice that was NOT skipped held `""` — a value the declared set does not
hold, which the read translated into null. Stored as what it means now:

1. **The column admits null and defaults to it**, with the registry's six as
   its `choices=`.
2. **Every stored `""` becomes null** — the invoices that were never skipped.
   Reversed, null goes back to `""`.
3. **`ck_usage_invoice_skip_reason_known`** admits null or one of the six, so
   the empty string, or any other spelling, is refused at the table.
"""
from django.db import migrations, models

#: The registry's six, as this migration knew them (`core.vocabulary`'s
#: `SKIP_REASON_VALUES` at R10-W4): a migration does not import a set that may
#: later grow, because replaying it must apply the rule it applied then.
SKIP_REASONS = [
    ("no_usage", "No usage recorded"),
    ("nothing_to_bill", "Nothing to bill"),
    ("seat_superseded", "Superseded by a newer seat"),
    ("no_stripe_customer", "No Stripe customer yet"),
    ("not_charge_ready", "Account cannot take charges yet"),
    ("payment_rail_closed", "Payment rail closed"),
]


def no_reason_is_null(apps, schema_editor):
    invoices = apps.get_model("invoicing", "CustomerUsageInvoice")
    invoices.objects.filter(skip_reason="").update(skip_reason=None)


def no_reason_is_blank(apps, schema_editor):
    invoices = apps.get_model("invoicing", "CustomerUsageInvoice")
    invoices.objects.filter(skip_reason__isnull=True).update(skip_reason="")


class Migration(migrations.Migration):

    dependencies = [
        ("invoicing", "0010_a_usage_invoice_is_usd_only"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customerusageinvoice",
            name="skip_reason",
            field=models.CharField(
                blank=True, choices=SKIP_REASONS, default=None,
                max_length=50, null=True),
        ),
        migrations.RunPython(no_reason_is_null, no_reason_is_blank),
        migrations.AddConstraint(
            model_name="customerusageinvoice",
            constraint=models.CheckConstraint(
                condition=(models.Q(skip_reason__isnull=True)
                           | models.Q(skip_reason__in=sorted(
                               value for value, _ in SKIP_REASONS))),
                name="ck_usage_invoice_skip_reason_known"),
        ),
    ]
