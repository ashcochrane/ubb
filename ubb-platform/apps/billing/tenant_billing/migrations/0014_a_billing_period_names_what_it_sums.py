"""A billing period's money is named for what it sums (#516).

`TenantBillingPeriod.total_usage_cost_micros` held Σ `billed_cost_micros` over
the period's postings, placed by arrival — what the tenant's customers were
billed, Task Charges included. "Usage cost" said neither: it read like a
supplier cost, and it hid that fixed-price revenue is inside it. The ruling
names the aggregate after what it aggregates: `total_billed_cost_micros`, the
same name and meaning the stop payload already gives the same sum over one
unit of work (`events/schemas.py`).

One operation, `RenameField` (ADR-0007 §1): the column moves with every stored
value intact, and the reverse is exact.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_billing", "0013_a_billing_period_states_its_currency"),
    ]

    operations = [
        migrations.RenameField(
            model_name="tenantbillingperiod",
            old_name="total_usage_cost_micros",
            new_name="total_billed_cost_micros",
        ),
    ]
