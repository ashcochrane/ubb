"""Tests for the 0010 backfill (#52): Tenant.min_balance_micros -> config row.

The tenant-config API historically wrote Tenant.min_balance_micros while floor
resolution read BillingTenantConfig.min_balance_micros. The backfill applies
the decided reconciliation semantics before the Tenant column is dropped:

- config row untouched at the default 0, Tenant non-zero -> copy (the tenant's
  expressed intent finally takes effect);
- both non-zero and disagreeing -> the config value wins (it is what
  enforcement has actually been doing), logged loudly;
- a copy that would put the hard floor below an existing soft floor on the
  row -> skipped, logged loudly (the migration never changes two knobs to
  make one copy fit).

The migration's forwards() reads the historical Tenant model (the column no
longer exists on the live one), so these tests drive apply_backfill directly
with the plain rows forwards() extracts.
"""
import pytest

from apps.billing.tenant_billing.migrations._min_balance_backfill import apply_backfill
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.platform.tenants.models import Tenant

pytestmark = pytest.mark.django_db


def _rows(tenant, value):
    return [{"id": tenant.id, "name": tenant.name, "min_balance_micros": value}]


def test_untouched_default_config_gets_the_tenant_value(capsys):
    t = Tenant.objects.create(name="copy-me", products=["metering", "billing"])
    BillingTenantConfig.objects.create(tenant=t)  # untouched default 0
    apply_backfill(BillingTenantConfig, _rows(t, 5_000_000))
    bc = BillingTenantConfig.objects.get(tenant=t)
    assert bc.min_balance_micros == 5_000_000
    out = capsys.readouterr().out
    assert "COPY" in out and "0 -> 5000000" in out  # per-tenant before/after


def test_missing_config_row_is_created_with_the_tenant_value():
    t = Tenant.objects.create(name="lazy-row", products=["metering", "billing"])
    assert not BillingTenantConfig.objects.filter(tenant=t).exists()
    apply_backfill(BillingTenantConfig, _rows(t, 3_000_000))
    assert BillingTenantConfig.objects.get(tenant=t).min_balance_micros == 3_000_000


def test_conflict_keeps_the_config_value_and_logs_loudly(capsys):
    t = Tenant.objects.create(name="conflicted", products=["metering", "billing"])
    BillingTenantConfig.objects.create(tenant=t, min_balance_micros=3_000_000)
    apply_backfill(BillingTenantConfig, _rows(t, 5_000_000))
    bc = BillingTenantConfig.objects.get(tenant=t)
    assert bc.min_balance_micros == 3_000_000  # what enforcement has been doing
    out = capsys.readouterr().out
    assert "CONFLICT" in out and "3000000" in out and "5000000" in out


def test_copy_violating_soft_invariant_is_skipped_and_logged(capsys):
    # An existing soft floor above the incoming hard value would break
    # soft <= hard if the copy went through. Such rows can exist — write-time
    # validation goes stale (e.g. the hard floor lowered after the soft was
    # set; the resolver clamps at read time) — and the guard is deliberate:
    # the migration never changes two knobs to make one copy fit, so skip + log.
    t = Tenant.objects.create(name="soft-clash", products=["metering", "billing"])
    BillingTenantConfig.objects.create(tenant=t, soft_min_balance_micros=2_000_000)
    apply_backfill(BillingTenantConfig, _rows(t, 1_000_000))
    bc = BillingTenantConfig.objects.get(tenant=t)
    assert bc.min_balance_micros == 0  # copy skipped
    assert bc.soft_min_balance_micros == 2_000_000  # soft untouched
    out = capsys.readouterr().out
    assert "SKIP" in out and "2000000" in out and "1000000" in out


def test_agreeing_and_zero_tenant_values_are_left_alone(capsys):
    agree = Tenant.objects.create(name="agree", products=["metering", "billing"])
    BillingTenantConfig.objects.create(tenant=agree, min_balance_micros=4_000_000)
    unset = Tenant.objects.create(name="unset", products=["metering", "billing"])
    BillingTenantConfig.objects.create(tenant=unset, min_balance_micros=6_000_000)
    apply_backfill(
        BillingTenantConfig,
        _rows(agree, 4_000_000) + _rows(unset, 0))
    assert BillingTenantConfig.objects.get(tenant=agree).min_balance_micros == 4_000_000
    assert BillingTenantConfig.objects.get(tenant=unset).min_balance_micros == 6_000_000
    assert capsys.readouterr().out == ""  # nothing copied or skipped -> silent
