"""A usage invoice's skip reason is the registry's closed `skip_reason` (R10-W4).

It was a bare string written as literals by the postpaid service. The field
gains `choices=` from the registry's six; no stored value moves, and the empty
string every invoice that was not skipped holds stays legal (`blank=True`).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoicing", "0010_a_usage_invoice_is_usd_only"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customerusageinvoice",
            name="skip_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("no_usage", "No usage recorded"),
                    ("nothing_to_bill", "Nothing to bill"),
                    ("seat_superseded", "Superseded by a newer seat"),
                    ("no_stripe_customer", "No Stripe customer yet"),
                    ("not_charge_ready", "Account cannot take charges yet"),
                    ("payment_rail_closed", "Payment rail closed"),
                ],
                default="",
                max_length=50,
            ),
        ),
    ]
