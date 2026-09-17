"""WHAT THE ALERTING RECORD REMEMBERS, AND THE ONE DOOR ONTO IT (#502, §8).

`CustomerEconomics` is the margin snapshot **demoted**: margin is derived at read
time from postings, Charges and revenue records, and a closed period's reported
cost and margin move when its facts resolve. What a derivation cannot do is
remember, and the evaluator needs memory of exactly three things — whether this
period is already flagged, what the last few periods' margins were, and what the
period before this one cost — so that a webhook fires **once per transition** and
a consecutive-periods rule has something to look back at.

**That memory is this module, and nothing else may read the record for it.**
Before this commit the evaluator and the alerting list each reached for the rows
themselves, which meant nothing in the tree could tell an alerting read from a
reporting one; the two webhooks were sourced from a margin snapshot rather than
from an alerting record, and severing the reporting reads around them would have
turned a tenant's alerting off silently. One door makes the difference
mechanical, and `apps/subscriptions/tests/test_the_snapshot_is_an_alerting_record.py`
walks production for it in both directions.

⚠ **IT RETURNS PLAIN DATA, AND A MARGIN FIGURE THAT LEAVES HERE IS A FACT ABOUT
AN ALARM.** It is what the flag was raised on — the number the tenant was sent —
and not what the period's margin reads today. Anything asking the second question
is a report, and reports ask `GET /metering/analytics/economics`.

⚠ **THE PERCENTAGE STAYS A `Decimal`.** The threshold comparison is an exact
one against a `DecimalField`, and rendering it as a float here would move a
customer sitting exactly on its tenant's threshold onto the wrong side of it.
Callers float it at the wire, where the precision question is a different one.

**This module reads; it never writes.** The flag's write stays with the evaluator
that decides it (`services.py`), beside the transition rule that is the only
reason the column exists.

⚠ **AND THIS MODULE IS ITSELF GUARDED**, because a door that re-publishes the
columns it was built to enclose is the obvious way round the rule: a reporting
surface importing `state_of` would read a stored margin without ever naming
`CustomerEconomics`. The test module walks production for who imports from here
as well as for who names the record, so widening this seam is a line in a diff
rather than something nobody notices.

⚠ **THE ROW SHAPES ARE NOT THE COLUMN'S.** `customer_id` is a `str` because
every consumer of it — a webhook payload, a JSON body — wants one, while
`period_start` stays a `date` because its consumers do arithmetic on it before
anything renders it. And the percentage is `margin_pct` rather than the column's
name, because what leaves here is a fact about an alarm rather than a copy of a
column, and the payloads have always called it that.
"""
from apps.subscriptions.economics.models import CustomerEconomics
from core.cost_totals import UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY


def state_of(record) -> dict:
    """One period's alerting state, as plain data.

    The two counts travel with the figures rather than being fetched beside
    them, because every one of these numbers is a bound rather than a total: an
    excluded supplier cost makes the margin a CEILING and an excluded price
    makes it a FLOOR, and a consumer handed the margin without them cannot tell
    which way the real answer lies (#328, #351).
    """
    return {
        "customer_id": str(record.customer_id),
        "period_start": record.period_start,
        "is_unprofitable": record.is_unprofitable,
        "gross_margin_micros": record.gross_margin_micros,
        "margin_pct": record.margin_percentage,
        "provider_cost_micros": record.provider_cost_micros,
        UNRESOLVED_EVENT_COUNT_KEY: record.unresolved_event_count,
        UNPRICED_EVENT_COUNT_KEY: record.unpriced_event_count,
    }


def look_back(tenant_id, customer_id, period_start, *, periods) -> list[dict]:
    """The *periods* most recent states ending at *period_start*, newest first.

    Inclusive of *period_start* itself: the consecutive-periods rule asks
    whether this period and the ones before it have all been below the
    threshold, and this period is one of them. A caller gets fewer than it asked
    for when the customer has not existed that long, which is the honest answer
    — "below for three periods running" is not true of a customer with two.
    """
    rows = CustomerEconomics.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        period_start__lte=period_start).order_by("-period_start")[:periods]
    return [state_of(row) for row in rows]


def period_before(tenant_id, customer_id, period_start) -> dict | None:
    """The state of the period immediately preceding *period_start*, or None.

    The cost-spike comparison's denominator. `None` is not a zero and must not
    be read as one: a customer with no earlier period has no rise to compute,
    and dividing by a cost UBB never held would invent one.
    """
    row = (CustomerEconomics.objects
           .filter(tenant_id=tenant_id, customer_id=customer_id,
                   period_start__lt=period_start)
           .order_by("-period_start").first())
    return state_of(row) if row else None


def flagged_in(tenant_id, period_start) -> list[dict]:
    """Every customer the evaluator has NAMED unprofitable in *period_start*.

    Keyed off the flag and never off the arithmetic, which is the whole
    distinction the list exists to publish: a customer is on it because a
    threshold rule named them and a webhook went out, not because a margin
    computed now happens to read badly. A count derived from the arithmetic
    instead would disagree with what the tenant was sent.

    Each row carries the tenant's own word for the customer beside UBB's id,
    because the surface is read by somebody who is about to go and talk to them.
    """
    rows = CustomerEconomics.objects.filter(
        tenant_id=tenant_id, period_start=period_start, is_unprofitable=True
    ).select_related("customer").order_by("period_start")
    return [{**state_of(row), "external_id": row.customer.external_id}
            for row in rows]
