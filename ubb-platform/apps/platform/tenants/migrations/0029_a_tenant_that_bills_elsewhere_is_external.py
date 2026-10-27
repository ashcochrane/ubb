"""A tenant that meters and bills elsewhere is `external` (slice 8, R10-W3).

The registry's `customer_billing_mode` has always named this value `external`
(`domain-vocabulary/concepts/economics.yaml`): it says where the billing
happens, which is the fact a tenant chooses between, where the retired word
said only what UBB does not do. The rename was owned by slice 8 and is free
before admission (ADR-0007 §5).

Three steps, in the order the database needs them:

1. **The stored rows move first.** Every tenant holding the retired value is
   rewritten to `external` — the same mode under its final name, so this is a
   rename of a value, not a change of posture. Nothing reads the old spelling
   afterwards.
2. **The field's default and choices** take the registry's three values.
3. **`ck_tenant_billing_mode_known`** holds the closed set at the database
   (ADR-0002): the admin form and `QuerySet.update()` never pass `choices=`.

No trigger on `ubb_tenant` names `billing_mode` at this migration, so the
rewrite needs none lifted.

**The reverse is exact**: drop the constraint, restore the field, and move the
rows back to the old spelling.
"""

from django.db import migrations, models

#: The spelling slice 8 retires, as the rows before this migration carry it.
RETIRED = "meter_only"
EXTERNAL = "external"


def to_external(apps, schema_editor):
    apps.get_model("tenants", "Tenant").objects.filter(
        billing_mode=RETIRED).update(billing_mode=EXTERNAL)


def back_to_the_retired_spelling(apps, schema_editor):
    apps.get_model("tenants", "Tenant").objects.filter(
        billing_mode=EXTERNAL).update(billing_mode=RETIRED)


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0028_a_tenant_holds_usd_only"),
    ]

    operations = [
        migrations.RunPython(to_external, back_to_the_retired_spelling),
        migrations.AlterField(
            model_name="tenant",
            name="billing_mode",
            field=models.CharField(
                choices=[("external", "External billing"),
                         ("prepaid", "Prepaid credits"),
                         ("postpaid", "Postpaid")],
                db_index=True, default="external", max_length=20)),
        migrations.AddConstraint(
            model_name="tenant",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    billing_mode__in=["external", "postpaid", "prepaid"]),
                name="ck_tenant_billing_mode_known")),
    ]
