# #52: Tenant.min_balance_micros (the column the tenant-config API wrote) and
# BillingTenantConfig.min_balance_micros (the column floor resolution reads)
# forked after the one-time 0007 populate. Before the Tenant column drops
# (tenants/0021), reconcile the two under the decided semantics:
#
# - config row untouched at the default 0, Tenant non-zero -> copy Tenant ->
#   config (the tenant's expressed intent finally takes effect);
# - both non-zero and disagreeing -> config wins (it is what enforcement has
#   actually been doing); the conflict is logged loudly for operator review;
# - a copy that would leave an existing soft floor above the hard value
#   (breaking soft <= hard) -> skip and log loudly — the migration never
#   changes two knobs to make one copy fit.
#
# apply_backfill takes plain rows so tests can drive it after the Tenant
# column no longer exists on the live model.


def apply_backfill(BillingTenantConfig, tenant_rows):
    """tenant_rows: iterable of {"id", "name", "min_balance_micros"} dicts."""
    for row in tenant_rows:
        tenant_value = row["min_balance_micros"]
        if not tenant_value:
            continue  # 0 is the column default — no expressed intent to carry
        config, _created = BillingTenantConfig.objects.get_or_create(
            tenant_id=row["id"])
        label = f"tenant {row['id']} ({row['name']})"
        if config.min_balance_micros == tenant_value:
            continue
        if config.min_balance_micros != 0:
            print(f"[#52 backfill] CONFLICT {label}: keeping config "
                  f"min_balance_micros={config.min_balance_micros} (what "
                  f"enforcement has been using); discarding Tenant column "
                  f"value {tenant_value}")
            continue
        soft = config.soft_min_balance_micros
        if soft is not None and soft > tenant_value:
            print(f"[#52 backfill] SKIP {label}: copying Tenant "
                  f"min_balance_micros={tenant_value} would put the hard "
                  f"floor below the row's soft floor ({soft}); left at 0 "
                  f"for operator review")
            continue
        print(f"[#52 backfill] COPY {label}: min_balance_micros "
              f"0 -> {tenant_value}")
        config.min_balance_micros = tenant_value
        config.save(update_fields=["min_balance_micros", "updated_at"])


def forwards(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    BillingTenantConfig = apps.get_model("tenant_billing", "BillingTenantConfig")
    apply_backfill(
        BillingTenantConfig,
        Tenant.objects.values("id", "name", "min_balance_micros").iterator())
