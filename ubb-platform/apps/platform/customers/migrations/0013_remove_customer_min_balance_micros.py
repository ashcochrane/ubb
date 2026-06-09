from django.db import migrations


class Migration(migrations.Migration):
    """Remove orphaned Customer.min_balance_micros field.

    The live suspension threshold is read exclusively from
    CustomerBillingProfile.min_balance_micros (via get_customer_min_balance in
    apps/billing/queries.py).  The field on Customer itself has had zero
    production readers since the billing-profile model was introduced and the
    data was migrated (customers/0007_populate_billing_tenant_config).
    """

    dependencies = [
        ("customers", "0012_remove_customer_uq_customer_tenant_external_and_more"),
        # tenant_billing/0007 reads Customer.min_balance_micros in a RunPython
        # data migration; our removal must happen after that data migration runs.
        ("tenant_billing", "0007_populate_billing_tenant_config"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="customer",
            name="min_balance_micros",
        ),
    ]
