"""A closed period's reported cost and margin move when its facts do (#502, §8).

**Margin is derived at read time from postings, Charges and revenue records.**
This module is the other half of the demotion: `apps/subscriptions/tests/
test_the_snapshot_is_an_alerting_record.py` says no reporting surface reads a
margin figure off the stored record, and this says what a caller gets instead.

⚠ **THE DEFECT THIS CLOSES WAS LIVE ON `main` UNTIL THIS COMMIT, AND IT IS AN
ARGUMENT FOR THE READ-TIME RULE RATHER THAN A BUG TO FILE.** Compose three
things that are each correct on their own — the hourly cache repair covering the
current calendar month and the two before it, a supplier cost UBB learns long
after the call and settles at the instant the call happened (#146 §3.1), and a
remediation completing a cost inside a period that has closed (#148 §7.3) — and
a March figure UBB knows to be wrong is published forever. **Caches survive;
authorities do not.**

**The window is six months back, computed from today rather than written down.**
A fixed date would drift into the repair horizon as the calendar moved and the
case would start passing for the wrong reason, which is the quietest way for a
test like this to stop being about anything. The invoices and Charges of such a
period do not move and nothing here says they do: what moves is the REPORT.

⚠ **AND THE INVERSE IS ASSERTED TOO.** A figure that moves when a fact resolves
proves the derivation only if it would otherwise have stayed still — so the same
period is read before the settlement as well as after, and the answer says
`incomplete` with its count rather than a total the tenant could have banked.
"""
import datetime

import pytest
from django.utils import timezone

from api.v1.tests._helpers import a_tenant, ask, measure_of
from apps.metering.pricing.services.cost_settlement import (
    Settlement, settle_provider_cost)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from core.cost_totals import UNRESOLVED_EVENT_COUNT_KEY
from core.vocabulary import (
    ANALYTICS_MEASURE_GROSS_MARGIN, ANALYTICS_MEASURE_SUPPLIER_COGS,
    COSTING_STATUS_UNRESOLVED, MEASURE_STATUS_INCOMPLETE, MEASURE_STATUS_KNOWN,
    PRICING_STATUS_KNOWN, UNRESOLVED_REASON_COST_RATE_MISSING)

#: The three money measures this module asks for. The count measure is left out
#: deliberately: a number of records does not move when a cost resolves, so
#: including it would put a figure in every answer that is the same before and
#: after and reads like a control it is not.
MONEY = [ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_MEASURE_GROSS_MARGIN]

BILLED = 1_000_000
RESOLVED_COST = 400_000


def six_months_back(today):
    """The calendar month six closes before the one containing *today*.

    Stepped month by month rather than by a day count, so it lands on a calendar
    boundary whatever the day of the month is and whatever February did.
    """
    opens = today.replace(day=1)
    for _ in range(6):
        opens = (opens - datetime.timedelta(days=1)).replace(day=1)
    return opens


@pytest.mark.django_db
class TestAPeriodOutsideTheRepairHorizon:

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant("Long ago")
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        self.opens = six_months_back(timezone.now().date())
        self.closes = (self.opens + datetime.timedelta(days=32)).replace(day=1)
        self.posting = Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="i1",
            event_type="chat.completion", provider="openai",
            billed_cost_micros=BILLED, pricing_status=PRICING_STATUS_KNOWN,
            provider_cost_micros=None,
            costing_status=COSTING_STATUS_UNRESOLVED,
            unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING,
            effective_at=datetime.datetime(
                self.opens.year, self.opens.month, 15, 12,
                tzinfo=datetime.timezone.utc))

    def _answer(self):
        response = ask(self.key, measures=MONEY,
                       start_date=self.opens.isoformat(),
                       end_date=self.closes.isoformat(),
                       contributed_revenue=None)
        assert response.status_code == 200, response.content
        return response.json()

    def test_before_the_cost_resolves_the_margin_is_withheld(self):
        """The control, and it is the half that makes the other half mean
        something.

        The cost is a floor and says so with its count; the margin over a floor
        is a ceiling, so it reads `incomplete` rather than publishing the
        subtraction as though the supplier had charged nothing.
        """
        body = self._answer()

        cost = measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS)
        assert cost["status"] == MEASURE_STATUS_INCOMPLETE
        assert cost[UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["status"] == MEASURE_STATUS_INCOMPLETE

    def test_the_reported_margin_moves_when_the_cost_resolves(self):
        """AC 2, end to end and through the published route.

        Nothing re-snapshots anything between the two reads and nothing needs
        to: the second answer is computed from the postings as they stand, which
        is the whole content of "derived at read time". A stored copy would
        still be reading zero here, six months after the month closed, with no
        scheduled repair that would ever reach it.
        """
        before = self._answer()
        assert measure_of(before, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["amount_micros"] == 0
        # ⚠ THE MARGIN'S OWN BEFORE-VALUE IS CAPTURED, not inferred from the
        # cost beside it. "It moved" is a claim about two readings of the SAME
        # figure, and asserting only the after-value would pass against an
        # implementation that had answered 600,000 all along.
        #
        # It is a FIGURE and not a null, which is the distinction `incomplete`
        # draws against `unavailable_at_requested_grain`: UBB can attribute this
        # margin to this window, and what it cannot do is promise the cost side
        # is whole — so the number stands with its count beside it, as a bound
        # rather than a total. The bound is the revenue, because the cost total
        # it was taken against was a floor of nothing.
        margin_before = measure_of(before, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert margin_before["amount_micros"] == BILLED
        assert margin_before["status"] == MEASURE_STATUS_INCOMPLETE

        assert settle_provider_cost(
            posting_id=self.posting.pk,
            provider_cost_micros=RESOLVED_COST) is Settlement.SETTLED

        after = self._answer()
        cost = measure_of(after, ANALYTICS_MEASURE_SUPPLIER_COGS)
        assert cost["status"] == MEASURE_STATUS_KNOWN
        assert cost["amount_micros"] == RESOLVED_COST
        assert cost[UNRESOLVED_EVENT_COUNT_KEY] == 0
        margin = measure_of(after, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert margin["status"] == MEASURE_STATUS_KNOWN
        assert margin["amount_micros"] == BILLED - RESOLVED_COST
        # The figure MOVED, by exactly the cost that resolved into a month
        # closed six months ago. This is the assertion the whole module is for.
        assert margin["amount_micros"] != margin_before["amount_micros"]
