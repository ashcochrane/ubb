# ADR-0003: the MVP launches without tiered pricing — graduated/package are
# deleted end to end, not gated. After this migration every arrival-time
# estimate equals the settled price by construction.

from django.db import migrations, models


def assert_no_tiered_rates(apps, schema_editor):
    """Data guard: there is no production tenant yet, so no graduated/package
    Rate rows should exist anywhere. Fail loudly if any appear — deleting the
    tiers column under a live tiered rate would silently mis-price it."""
    Rate = apps.get_model("pricing", "Rate")
    tiered = Rate.objects.filter(pricing_model__in=("graduated", "package"))
    count = tiered.count()
    if count:
        ids = list(tiered.values_list("id", flat=True)[:20])
        raise RuntimeError(
            f"Cannot delete tiered pricing: {count} Rate row(s) still use "
            f"pricing_model graduated/package (first ids: {ids}). "
            f"Re-price or delete them before applying this migration "
            f"(ADR-0003 assumed none existed).")


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0013_rate_book_unique_constraint'),
    ]

    operations = [
        migrations.RunPython(assert_no_tiered_rates, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='pricingperiodcounter',
            name='uq_pricing_period_counter',
        ),
        migrations.RemoveField(
            model_name='rate',
            name='tiers',
        ),
        migrations.AlterField(
            model_name='rate',
            name='pricing_model',
            field=models.CharField(choices=[('per_unit', 'Per unit'), ('flat', 'Flat')], default='per_unit', max_length=20),
        ),
        migrations.DeleteModel(
            name='PricingPeriodCounter',
        ),
    ]
