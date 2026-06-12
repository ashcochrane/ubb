"""Tiered pricing x prepaid drawdown: marginal amounts debit exactly-once and
sum to the closed form; zero-marginal events never touch the wallet."""
import uuid

import pytest

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.metering.pricing.models import RateCard
from apps.metering.usage.services.usage_service import UsageService

TIERS = [
    {"up_to": 100, "rate_per_unit_micros": 10, "unit_quantity": 1},
    {"up_to": None, "rate_per_unit_micros": 5, "unit_quantity": 1},
]


def _setup(card_kwargs):
    tenant = Tenant.objects.create(
        name="T", products=["metering", "billing"], billing_mode="prepaid",
        stripe_connected_account_id="acct_test")
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    wallet = Wallet.objects.create(customer=customer)
    wallet.balance_micros = 100_000_000
    wallet.save(update_fields=["balance_micros"])
    card = RateCard.objects.create(tenant=tenant, card_type="price", **card_kwargs)
    return tenant, customer, wallet, card


def _record_and_drawdown(tenant, customer, request_id, key, metrics):
    from apps.billing.handlers import handle_usage_recorded_billing
    result = UsageService.record_usage(tenant, customer, request_id, key,
                                       usage_metrics=metrics)
    handle_usage_recorded_billing(str(uuid.uuid4()), {
        "tenant_id": str(tenant.id),
        "customer_id": str(customer.id),
        "event_id": result["event_id"],
        "cost_micros": result["billed_cost_micros"],
        "billing_owner_id": str(customer.id),
    })
    return result


@pytest.mark.django_db
class TestTieredDrawdown:
    def test_graduated_drawdowns_sum_to_cumulative_closed_form(self):
        tenant, customer, wallet, card = _setup(
            dict(metric_name="tok", pricing_model="graduated", tiers=TIERS))
        total_units = 0
        for i, units in enumerate([60, 50, 40]):  # third event crosses the band
            _record_and_drawdown(tenant, customer, f"r{i}", f"k{i}", {"tok": units})
            total_units += units
        deductions = WalletTransaction.objects.filter(
            wallet=wallet, transaction_type="USAGE_DEDUCTION")
        assert deductions.count() == 3
        debited = sum(-d.amount_micros for d in deductions)
        assert debited == card.compute_cumulative(total_units) == 1_250
        wallet.refresh_from_db()
        assert wallet.balance_micros == 100_000_000 - 1_250

    def test_zero_marginal_package_event_creates_no_wallet_txn(self):
        tenant, customer, wallet, card = _setup(
            dict(metric_name="calls", pricing_model="package",
                 rate_per_unit_micros=2_000_000, unit_quantity=1_000, tiers=[]))
        r1 = _record_and_drawdown(tenant, customer, "r1", "k1", {"calls": 1})
        assert r1["billed_cost_micros"] == 2_000_000
        r2 = _record_and_drawdown(tenant, customer, "r2", "k2", {"calls": 500})
        assert r2["billed_cost_micros"] == 0  # inside the purchased block
        deductions = WalletTransaction.objects.filter(
            wallet=wallet, transaction_type="USAGE_DEDUCTION")
        assert deductions.count() == 1  # the > 0 guard skipped the zero event
        wallet.refresh_from_db()
        assert wallet.balance_micros == 100_000_000 - 2_000_000
