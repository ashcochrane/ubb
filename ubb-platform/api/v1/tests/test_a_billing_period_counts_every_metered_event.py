"""A billing period counts every metered event, and names the money it sums
(#563, #516).

**The count (#563, the owner's ruling and §0.4 D).** `event_count` is every
real `metered_usage` event recorded in the period, whatever it was priced at —
unpriced and zero-priced included — and never a synthetic Task Charge. Both
writers decide it from the canonical `Posting.kind` and from nothing else: the
live accumulator, as each posting reaches the billing rails, and the close's
reconcile, from the read contract (`get_period_totals`). They agree, so a drift
warning means an accumulator failure again rather than two definitions.

**The money (#516).** `total_billed_cost_micros` is Σ `billed_cost_micros` over
the period's postings, placed by arrival — Task Charges INCLUDED, because
fixed-price revenue is revenue and UBB's platform fee is a percentage of it.
So on one schema the count excludes what the money includes, and both field
descriptions say so.

**THE FIXTURE IS ASYMMETRIC ON PURPOSE.** Two unpriced metered events (one of
them under a running unit of work), one priced at zero, and one Task Charge:
the right count is 3, and every proxy a writer might reach for instead gives
something else — the pricing status counts the zero and the charge (2), a Task
link counts only the two with none (2), and every posting is 4. A fixture of
one each would let the pricing-status proxy pass with the right number.

**"Unpriced" means a DECLARED Event Type no rule prices** (§0.1): an undeclared
name is held, and a held name refuses the close, which is a different
condition entirely.
"""
import logging
from datetime import timedelta

import pytest
from django.utils import timezone

from api.v1.tests.test_the_charge_reaches_the_rails_as_one_marked_posting import (
    SOLD_PER_EVENT, THE_AGREED_PRICE, ProjectionTestBase,
)
from apps.billing.tenant_billing.models import TenantBillingPeriod
from apps.billing.tenant_billing.services import TenantBillingService
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, rate_in_default_book,
)
from apps.metering.queries import get_period_totals
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from core.vocabulary import (
    PRICING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN, USAGE_EVENT_KIND_METERED_USAGE,
    USAGE_EVENT_KIND_TASK_CHARGE,
)

UNPRICED = "unpriced-call"
FREE = "free-call"
QUANTITY = "calls"


@pytest.mark.django_db
class TestThePeriodCountsMeteredEventsByKind(ProjectionTestBase):

    def _declares(self, event_type, *, price_micros):
        """A published Event Type costed at nothing, priced at `price_micros`
        — or priced by no rule at all where that is None."""
        cost_rate_in_default_book(self.tenant, event_type=event_type,
                                  measurement_key=QUANTITY,
                                  rate_per_unit_micros=0, unit_quantity=1)
        if price_micros is not None:
            rate_in_default_book(self.tenant, event_type=event_type,
                                 measurement_key=QUANTITY,
                                 rate_per_unit_micros=price_micros,
                                 unit_quantity=1)

    def _records(self, key, event_type, **fields):
        recorded = UsageService.record_usage(
            self.tenant, self.customer, key, event_type=event_type,
            measurements={QUANTITY: "1"}, **fields)
        return Posting.objects.get(id=recorded["event_id"])

    def _the_month(self):
        """Two unpriced metered events (one under running work), one priced at
        zero, and one Task Charge — and the rails run as production runs them."""
        self._declares(UNPRICED, price_micros=None)
        self._declares(FREE, price_micros=0)
        running = self._start(task_type=SOLD_PER_EVENT)
        postings = [
            self._records("unpriced-1", UNPRICED),
            self._records("unpriced-2", UNPRICED, task_id=running),
            self._records("free-1", FREE),
        ]
        delivered = self._priced_work()
        assert self._close(delivered).status_code == 200
        postings.append(self._projection_of(delivered))
        self._drain_the_rails()
        return postings

    def test_the_fixture_is_the_month_it_claims_to_be(self):
        """Read off the rows, so the counts below are about these four."""
        postings = self._the_month()

        assert [(p.kind, p.pricing_status, p.task_id is not None)
                for p in postings] == [
            (USAGE_EVENT_KIND_METERED_USAGE, PRICING_STATUS_UNKNOWN, False),
            (USAGE_EVENT_KIND_METERED_USAGE, PRICING_STATUS_UNKNOWN, True),
            (USAGE_EVENT_KIND_METERED_USAGE, PRICING_STATUS_KNOWN, False),
            (USAGE_EVENT_KIND_TASK_CHARGE, PRICING_STATUS_KNOWN, True),
        ]
        assert postings[2].billed_cost_micros == 0

    def test_the_live_count_is_every_metered_event_and_no_charge(self):
        self._the_month()

        period = TenantBillingPeriod.objects.get(tenant=self.tenant)
        assert period.event_count == 3

    def test_the_money_includes_the_charge_the_count_excludes(self):
        """#516's pin: the column is Σ `billed_cost_micros` over the period's
        postings, placed by arrival — the charge's money included."""
        postings = self._the_month()

        period = TenantBillingPeriod.objects.get(tenant=self.tenant)
        assert period.total_billed_cost_micros == sum(
            p.billed_cost_micros or 0 for p in postings) == THE_AGREED_PRICE

    def test_the_reconcile_agrees_and_rewrites_nothing(self, caplog):
        self._the_month()
        period = TenantBillingPeriod.objects.get(tenant=self.tenant)
        live = (period.event_count, period.total_billed_cost_micros)

        with caplog.at_level(logging.WARNING,
                             logger="apps.billing.tenant_billing.services"):
            totals = TenantBillingService.reconcile_period(period)

        assert (totals["event_count"], totals["total_billed_cost_micros"]) == live
        assert not [r for r in caplog.records if "drift" in r.getMessage()]
        period.refresh_from_db()
        assert (period.event_count, period.total_billed_cost_micros) == live

    def test_the_read_contract_counts_the_same_way(self):
        self._the_month()
        today = timezone.now().date()

        totals = get_period_totals(self.tenant.id, today.replace(day=1),
                                   _first_of_next_month(today), basis="arrival")

        assert (totals["event_count"], totals["total_billed_cost_micros"]) == (
            3, THE_AGREED_PRICE)


def _first_of_next_month(day):
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)
