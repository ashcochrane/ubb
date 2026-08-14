"""Declarations a test needs to make, without transcribing them each time.

`cost_rate_in_default_book`'s shape one product along
(`apps/metering/pricing/tests/_helpers.py`): a caller says what it wants
declared and never learns which fields carry it.
"""
from apps.platform.event_types.models import EventType, ReportedCostMapping
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MICROS,
    COSTING_METHOD_REPORTED,
    SOURCE_KIND_CALLER_SUPPLIED,
)


#: The Event Type key a fixture names when all it needs is somewhere the
#: supplier's own cost is admissible (#324). One string, imported, because a
#: dozen modules wanted the same nothing-in-particular and a dozen copies of a
#: literal is a dozen places to drift.
DECLARED = "declared.call"


def declares_a_caller_supplied_cost(tenant, key, *, currency="usd"):
    """The ONE declaration under which a caller may state the supplier's cost.

    Two records saying one thing: this Event Type's supplier cost is the figure
    the supplier itself reports, and the caller's own code passes it in on the
    call. Anything less than the pair is a 422 on `provider_cost_micros`
    (#324), so a test that wants the figure accepted wants exactly this.

    **THE COMMONEST REASON A TEST NEEDS IT is that it predates the registry.**
    Recording a supplier cost against no declaration at all was how every
    fixture in this repository did it, and each one now has to say which Event
    Type it means. Where the figure is incidental to what the test asserts, the
    cheaper fix is to stop sending it — a posting costed from Cost Rates needs
    no declaration.
    """
    event_type = EventType.objects.create(
        tenant=tenant, key=key, costing_method=COSTING_METHOD_REPORTED)
    ReportedCostMapping.objects.create(
        event_type=event_type, source_kind=SOURCE_KIND_CALLER_SUPPLIED,
        amount_representation=AMOUNT_REPRESENTATION_MICROS, currency=currency)
    return event_type
