from django.db import migrations


def populate_billing_tenant_config(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    BillingTenantConfig = apps.get_model("tenant_billing", "BillingTenantConfig")

    for tenant in Tenant.objects.all():
        BillingTenantConfig.objects.get_or_create(
            tenant=tenant,
            defaults={
                "stripe_customer_id": tenant.stripe_customer_id,
                "platform_fee_percentage": tenant.platform_fee_percentage,
                "min_balance_micros": tenant.min_balance_micros,
                "run_cost_limit_micros": tenant.run_cost_limit_micros,
                "hard_stop_balance_micros": tenant.hard_stop_balance_micros,
            },
        )


def populate_customer_billing_profile(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    CustomerBillingProfile = apps.get_model("wallets", "CustomerBillingProfile")

    for customer in Customer.objects.filter(min_balance_micros__isnull=False):
        CustomerBillingProfile.objects.get_or_create(
            customer=customer,
            defaults={
                "min_balance_micros": customer.min_balance_micros,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_billing", "0006_billing_tenant_config"),
        ("wallets", "0003_customer_billing_profile"),
        ("tenants", "0007_rename_arrears_to_min_balance"),
        ("customers", "0009_rename_arrears_to_min_balance"),
    ]

    operations = [
        migrations.RunPython(
            populate_billing_tenant_config,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            populate_customer_billing_profile,
            migrations.RunPython.noop,
        ),
    ]
