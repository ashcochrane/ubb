"""A billing period states the currency its money is in (#565).

The platform fee is a percentage of a period's billed money and is invoiced to
the tenant on UBB's own Stripe account. Its currency was a literal at the
invoice call; now it is read off this row, which a fact about money must carry
(#145 §7.2), and the row is held to UBB v1's one currency like every other
economic column (ADR-0023).

**Every existing period is stamped `usd`, and that is a statement, not a
default.** A period's money is the sum of its tenant's postings, and this
migration runs after the two that make that true for every row there is: no
tenant holds another currency (`tenants/0028`) and no posting is in one
(`usage/0051`), each of which refused rather than relabelled.

**The reverse is exact**: drop the constraint and the column.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_billing", "0012_platformfeecarry"),
        ("tenants", "0028_a_tenant_holds_usd_only"),
        ("usage", "0051_a_posting_is_usd_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantbillingperiod",
            name="currency",
            field=models.CharField(default="usd", max_length=3)),
        migrations.AddConstraint(
            model_name="tenantbillingperiod",
            constraint=models.CheckConstraint(
                condition=models.Q(currency="usd"),
                name="ck_billing_period_currency_usd")),
    ]
