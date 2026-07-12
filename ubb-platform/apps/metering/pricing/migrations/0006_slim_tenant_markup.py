from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0005_delete_providerrate"),
        ("customers", "0009_rename_arrears_to_min_balance"),
    ]
    operations = [
        migrations.RemoveIndex(model_name="tenantmarkup", name="idx_markup_tenant_lookup"),
        migrations.RemoveField(model_name="tenantmarkup", name="event_type"),
        migrations.RemoveField(model_name="tenantmarkup", name="provider"),
        migrations.RemoveField(model_name="tenantmarkup", name="valid_from"),
        migrations.RemoveField(model_name="tenantmarkup", name="valid_to"),
        migrations.AddField(
            model_name="tenantmarkup", name="customer",
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="markups", to="customers.customer",
            ),
        ),
        migrations.AddConstraint(
            model_name="tenantmarkup",
            constraint=models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(customer__isnull=True),
                name="uq_markup_tenant_default"),
        ),
        migrations.AddConstraint(
            model_name="tenantmarkup",
            constraint=models.UniqueConstraint(
                fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                name="uq_markup_tenant_customer"),
        ),
    ]
