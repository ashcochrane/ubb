from django.db import migrations


def clear_orphan_invoices(apps, schema_editor):
    """Delete existing invoices that reference billing periods (legacy data)."""
    Invoice = apps.get_model("usage", "Invoice")
    # These invoices were for period-based billing and have no top_up_attempt
    Invoice.objects.filter(top_up_attempt__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("usage", "0007_remove_billingperiod_idx_billing_period_status_end_and_more"),
    ]

    operations = [
        migrations.RunPython(clear_orphan_invoices, migrations.RunPython.noop),
    ]
