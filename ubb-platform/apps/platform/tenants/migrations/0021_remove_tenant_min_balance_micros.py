from django.db import migrations


class Migration(migrations.Migration):
    """Remove Tenant.min_balance_micros (#52).

    The tenant-default hard floor's single source of truth is
    BillingTenantConfig.min_balance_micros — the row get_customer_min_balance
    reads and (as of #52) the tenant-config API writes. Mirrors
    customers/0013, which removed Customer.min_balance_micros when the
    customer level made this same move.
    """

    dependencies = [
        ("tenants", "0020_tenant_arrival_signals_enabled"),
        # The #52 backfill (and, transitively, the historical 0007 populate)
        # reads this column in a RunPython data migration; the removal must
        # run after it.
        ("tenant_billing", "0010_backfill_tenant_min_balance"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="tenant",
            name="min_balance_micros",
        ),
    ]
