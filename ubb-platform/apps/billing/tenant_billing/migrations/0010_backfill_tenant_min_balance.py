from django.db import migrations

from apps.billing.tenant_billing.migrations import _min_balance_backfill


class Migration(migrations.Migration):
    """Backfill Tenant.min_balance_micros into BillingTenantConfig (#52).

    The tenant-config API wrote the Tenant column while floor resolution
    (get_customer_min_balance) read the config row; the two forked after the
    one-time 0007 populate. This applies the decided reconciliation semantics
    (copy-unless-conflict, config wins on conflict, skip a copy that would
    break soft <= hard) before tenants/0021 drops the Tenant column.
    """

    dependencies = [
        ("tenant_billing", "0009_billingtenantconfig_soft_min_balance_micros"),
        # Reads Tenant.min_balance_micros — must run while the column exists.
        ("tenants", "0020_tenant_arrival_signals_enabled"),
    ]

    operations = [
        migrations.RunPython(
            _min_balance_backfill.forwards,
            migrations.RunPython.noop,
        ),
    ]
