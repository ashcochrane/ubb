"""#199: the platform fee reaches the minor unit once, and carries its remainder.

Before this, the fee floored to whole cents per line and DROPPED the remainder,
while usage-invoice lines floored and carefully carried theirs
(``PostpaidResidualLedger``). #142 §5.2's R3 settles the disagreement in favour
of carrying, and this file is the proof: the minor unit is reached exactly once,
at the money boundary, and nothing is ever thrown away.

The invariant every test here serves is the last one:

    banked minor units + the remainder still carried == the exact micros accrued

which is the only statement that distinguishes a carry from a rounding that
happens to look tidy over one period.
"""
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.billing.stripe.services.stripe_service import micros_to_cents
from apps.billing.tenant_billing.models import (
    BillingTenantConfig, PlatformFeeCarry, ProductFeeConfig, TenantBillingPeriod)
from apps.billing.tenant_billing.services import TenantBillingService
from apps.billing.tenant_billing.tasks import generate_tenant_platform_invoices
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox

# A cent in micros. Spelled here rather than imported so a change to
# core.money's table cannot silently redefine what these tests assert.
CENT = 10_000

# Twelve month boundaries, so a test can close consecutive periods without
# arithmetic in the middle of the assertion it is making.
MONTHS = [date(2026, m, 1) for m in range(1, 13)] + [date(2027, 1, 1)]


class FeeCarryTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Live Co", products=["metering", "billing"],
            platform_fee_percentage=Decimal("1.00"))
        BillingTenantConfig.objects.create(
            tenant=self.tenant, platform_fee_percentage=Decimal("1.00"))

    def close_month(self, index, usage_micros=0, tenant=None):
        """Open month ``index`` for the tenant, close it, return it refreshed.

        Only one period per tenant may be open at a time
        (``uq_one_open_period_per_tenant``), so periods are necessarily created
        and closed in sequence — which is what makes "the following period"
        well defined.
        """
        period = TenantBillingPeriod.objects.create(
            tenant=tenant or self.tenant,
            period_start=MONTHS[index], period_end=MONTHS[index + 1],
            status="open", total_usage_cost_micros=usage_micros,
            # Non-zero so reconcile_period does not zero the cost: this test DB
            # holds no Postings to recompute from.
            event_count=1)
        TenantBillingService.close_period(period)
        period.refresh_from_db()
        return period

    def flat_fee(self, amount_micros, product="metering", tenant=None):
        return ProductFeeConfig.objects.create(
            tenant=tenant or self.tenant, product=product, fee_type="flat",
            config={"amount_micros": amount_micros})

    def percentage_fee(self, percentage, product="metering"):
        return ProductFeeConfig.objects.create(
            tenant=self.tenant, product=product, fee_type="percentage",
            config={"percentage": percentage})

    def carry_for(self, period):
        carry = PlatformFeeCarry.objects.get(billing_period=period)
        # The bound the CheckConstraint deliberately cannot express — it is
        # minor_units(currency), and hard-coding it in the schema would restore
        # the bare literal core/money.py exists to delete. Asserted on every
        # read instead, where the currency is in scope.
        self.assertGreaterEqual(carry.carried_out_micros, 0)
        self.assertLess(carry.carried_out_micros, CENT)
        return carry


class RemainderIsCarriedNotDroppedTest(FeeCarryTestBase):
    """AC 1 + 2: the floor carries, and the carry lands on the next period."""

    def setUp(self):
        super().setUp()
        # $1.234567 — deliberately not a whole number of cents, and flat so the
        # expected accrual is a constant rather than a re-derivation of the
        # percentage arithmetic under test elsewhere.
        self.flat_fee(1_234_567)

    def test_first_period_banks_whole_cents_and_records_the_remainder(self):
        period = self.close_month(0)

        self.assertEqual(period.platform_fee_micros, 123 * CENT)
        carry = self.carry_for(period)
        self.assertEqual(carry.carried_in_micros, 0)
        self.assertEqual(carry.carried_out_micros, 4_567)

    def test_the_remainder_is_applied_to_the_following_period(self):
        self.close_month(0)                       # carries out 4_567
        second = self.close_month(1)

        # 1_234_567 + 4_567 = 1_239_134 -> 123 cents, 9_134 carried on.
        self.assertEqual(self.carry_for(second).carried_in_micros, 4_567)
        self.assertEqual(second.platform_fee_micros, 123 * CENT)
        self.assertEqual(self.carry_for(second).carried_out_micros, 9_134)

    def test_an_accumulated_carry_eventually_bills_a_whole_extra_cent(self):
        """The point of the whole exercise: the fraction is not lost, it is
        deferred, and a later period is larger by exactly one minor unit."""
        self.close_month(0)                       # 123c, carries 4_567
        self.close_month(1)                       # 123c, carries 9_134
        third = self.close_month(2)

        # 1_234_567 + 9_134 = 1_243_701 -> 124 cents. One cent more than the
        # other months, funded entirely by the two dropped fractions.
        self.assertEqual(third.platform_fee_micros, 124 * CENT)
        self.assertEqual(self.carry_for(third).carried_out_micros, 3_701)

    def test_every_banked_fee_is_a_whole_number_of_minor_units(self):
        """R3's other half: whatever is banked can reach Stripe. A flat fee
        stated in un-aligned micros used to reach ``micros_to_cents`` intact
        and be refused there; the single floor is what makes it payable."""
        for index in range(4):
            period = self.close_month(index)
            micros_to_cents(period.platform_fee_micros)  # raises if unaligned


class MinorUnitIsReachedOnceTest(FeeCarryTestBase):
    """R3: 'the minor unit is reached exactly once'. Two sub-cent fee lines
    that each floored to nothing under per-line flooring are worth a cent
    together, because the sum is what meets the boundary."""

    def test_two_sub_cent_lines_sum_before_the_floor(self):
        for product in ("metering", "billing"):
            self.percentage_fee("0.005", product=product)

        # 0.005% of $100 = 5_000 micros = half a cent, twice.
        period = self.close_month(0, usage_micros=100_000_000)

        self.assertEqual(period.platform_fee_micros, 1 * CENT)
        self.assertEqual(self.carry_for(period).carried_out_micros, 0)


class UnpushedPeriodDoesNotStrandItsCarryTest(FeeCarryTestBase):
    """AC 3: the carry is banked against the TENANT at close, not against the
    act of pushing an invoice. A period billing nothing never reaches Stripe at
    all — its fraction must still survive."""

    def setUp(self):
        super().setUp()
        self.flat_fee(5_000)                     # half a cent per period

    def test_a_period_that_never_pushes_still_banks_its_remainder(self):
        first = self.close_month(0)
        self.assertEqual(first.platform_fee_micros, 0)
        self.assertEqual(self.carry_for(first).carried_out_micros, 5_000)

        # The zero-fee period is marked invoiced with no Stripe call whatsoever
        # (tasks.py's `platform_fee_micros <= 0` branch). Nothing was pushed, so
        # a carry banked at push time would be lost here.
        generate_tenant_platform_invoices()
        first.refresh_from_db()
        self.assertEqual(first.status, "invoiced")

        second = self.close_month(1)
        self.assertEqual(self.carry_for(second).carried_in_micros, 5_000)
        # Two half-cents make the cent that neither period could bill alone.
        self.assertEqual(second.platform_fee_micros, 1 * CENT)


class SandboxGetsNoCarryRecordTest(FeeCarryTestBase):
    """AC 4: sandbox tenants never accrue a platform fee (F4.4), so they get no
    carry record AT ALL — not one created at zero. #142 §11 called this out
    specifically: a row at zero would assert a fee relationship that does not
    exist."""

    def test_sandbox_period_closes_with_no_carry_row(self):
        sandbox = get_or_create_sandbox(self.tenant)
        self.flat_fee(1_234_567, tenant=sandbox)

        period = self.close_month(0, tenant=sandbox)

        self.assertEqual(period.status, "closed")
        self.assertEqual(period.platform_fee_micros, 0)
        self.assertFalse(PlatformFeeCarry.objects.filter(tenant=sandbox).exists())
        self.assertFalse(
            PlatformFeeCarry.objects.filter(billing_period=period).exists())

    def test_a_live_tenant_gets_a_row_even_when_nothing_is_carried(self):
        """The contrast that gives the sandbox rule its meaning: a live period
        whose fee lands exactly on a cent still records the period, at zero."""
        self.flat_fee(50_000_000)

        period = self.close_month(0)

        self.assertEqual(self.carry_for(period).carried_out_micros, 0)


class CarryInvariantTest(FeeCarryTestBase):
    """AC 5: over consecutive periods, nothing is created and nothing is lost.

    banked + still-carried == accrued. This is the statement that a rounding
    bug of any sign breaks, in either direction.
    """

    PER_PERIOD_MICROS = 1_234_567
    PERIODS = 5

    def test_banked_plus_carried_equals_accrued_over_five_periods(self):
        self.flat_fee(self.PER_PERIOD_MICROS)

        periods = [self.close_month(i) for i in range(self.PERIODS)]

        banked = sum(p.platform_fee_micros for p in periods)
        still_carried = self.carry_for(periods[-1]).carried_out_micros
        accrued = self.PER_PERIOD_MICROS * self.PERIODS

        self.assertEqual(banked + still_carried, accrued)
        # Not a vacuous pass: the carry must actually be doing work, and the
        # banked total must not have swallowed the fraction whole.
        self.assertGreater(still_carried, 0)
        self.assertLess(still_carried, CENT)
        self.assertLess(banked, accrued)

    def test_each_period_carries_in_exactly_what_the_last_carried_out(self):
        """The chain has no gaps — which is what makes the sum above telescope
        rather than merely happen to balance."""
        self.flat_fee(self.PER_PERIOD_MICROS)

        periods = [self.close_month(i) for i in range(self.PERIODS)]
        carries = [self.carry_for(p) for p in periods]

        self.assertEqual(carries[0].carried_in_micros, 0)
        for previous, current in zip(carries, carries[1:]):
            self.assertEqual(
                current.carried_in_micros, previous.carried_out_micros)

    def test_the_invariant_holds_across_varying_usage(self):
        """The same statement where the accrual is a percentage of a usage
        total that changes every period — so the carry is never the same size
        twice and no period's remainder is a repeat of the last."""
        self.percentage_fee("1.5")
        usages = [100_000_123, 250_000_777, 33_333_333, 987_654_321, 1_000_005]

        periods = [self.close_month(i, usage_micros=u)
                   for i, u in enumerate(usages)]

        accrued = sum(int(Decimal(u) * Decimal("1.5") / Decimal(100))
                      for u in usages)
        banked = sum(p.platform_fee_micros for p in periods)
        still_carried = self.carry_for(periods[-1]).carried_out_micros

        self.assertEqual(banked + still_carried, accrued)
        self.assertGreater(still_carried, 0)


class CarryRecordShapeTest(FeeCarryTestBase):
    """The record is per tenant per period — the grain the fee is computed at,
    which is why it is a sibling of PostpaidResidualLedger rather than a reuse
    of it (that one is per customer)."""

    def _closed_period(self):
        return TenantBillingPeriod.objects.create(
            tenant=self.tenant, period_start=MONTHS[0], period_end=MONTHS[1],
            status="closed")

    def test_one_carry_per_period_is_enforced_by_the_database(self):
        period = self._closed_period()
        PlatformFeeCarry.objects.create(tenant=self.tenant, billing_period=period)

        with self.assertRaises(IntegrityError), transaction.atomic():
            PlatformFeeCarry.objects.create(
                tenant=self.tenant, billing_period=period)

    def test_a_negative_carry_is_refused_by_the_database(self):
        """A carry is a remainder, so it is never negative whatever the
        currency — the one half of to_minor's range a CheckConstraint can
        state without hard-coding a minor unit."""
        period = self._closed_period()

        with self.assertRaises(IntegrityError), transaction.atomic():
            PlatformFeeCarry.objects.create(
                tenant=self.tenant, billing_period=period,
                carried_out_micros=-1)
