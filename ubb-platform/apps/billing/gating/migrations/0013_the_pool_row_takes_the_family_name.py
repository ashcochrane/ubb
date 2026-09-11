"""The pool row takes the family's name (#456, slice 6 §4 and §20).

`BudgetConfig` becomes `CustomerSpendPool`: ADR-0007 §1's `RenameModel`,
carrying every row, then the table follows the model (`AlterModelTable` — the
`0028` pricing precedent: the model, then the table, never a rebuild), the two
partial unique constraints are dropped and re-added under the new names (they
carry no data), and the two reverse accessors take the noun (state only — the
columns do not move). `enforce_mode`'s choices are unchanged in value and in
label: the model now holds them by reference from `core.vocabulary`, which is
a fact about the source and not about the column, so no `AlterField` is owed
for it and `makemigrations --check` agrees.

Historical audit rows written under the retired action are neither relabelled
nor migrated here: ADR-0006's Consequences hand every retired audit action to
the cutover reset (#154 §4.2), and doing it twice would be a second mechanism.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gating", "0012_the_per_owner_cap_on_running_work_is_deleted"),
    ]

    operations = [
        # THE MODEL, THEN THE TABLE.
        migrations.RenameModel(old_name="BudgetConfig", new_name="CustomerSpendPool"),
        migrations.AlterModelTable(name="customerspendpool", table="ubb_customer_spend_pool"),
        # The two partial unique constraints carry no data: dropped and
        # re-added under the family's name.
        migrations.RemoveConstraint(model_name="customerspendpool",
                                    name="uq_budget_config_tenant_default"),
        migrations.RemoveConstraint(model_name="customerspendpool",
                                    name="uq_budget_config_tenant_customer"),
        migrations.AddConstraint(
            model_name="customerspendpool",
            constraint=models.UniqueConstraint(
                fields=("tenant",), condition=models.Q(customer__isnull=True),
                name="uq_customer_spend_pool_tenant_default"),
        ),
        migrations.AddConstraint(
            model_name="customerspendpool",
            constraint=models.UniqueConstraint(
                fields=("tenant", "customer"), condition=models.Q(customer__isnull=False),
                name="uq_customer_spend_pool_tenant_customer"),
        ),
        # The reverse accessors take the noun — migration state only.
        migrations.AlterField(
            model_name="customerspendpool",
            name="customer",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="customer_spend_pools", to="customers.customer"),
        ),
        migrations.AlterField(
            model_name="customerspendpool",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="customer_spend_pools", to="tenants.tenant"),
        ),
    ]
