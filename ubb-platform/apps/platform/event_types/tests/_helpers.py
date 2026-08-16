"""Declarations a test needs to make, without transcribing them each time.

`cost_rate_in_default_book`'s shape one product along
(`apps/metering/pricing/tests/_helpers.py`): a caller says what it wants
declared and never learns which fields carry it.
"""
from apps.platform.event_types.models import (
    EventType, Measurement, ReportedCostMapping)
from apps.platform.event_types.quantities import declaration_named
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MICROS,
    COSTING_METHOD_CALCULATED,
    COSTING_METHOD_REPORTED,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
)


#: The Event Type key a fixture names when all it needs is somewhere the
#: supplier's own cost is admissible (#324). One string, imported, because a
#: dozen modules wanted the same nothing-in-particular and a dozen copies of a
#: literal is a dozen places to drift.
DECLARED = "declared.call"

#: The Event Type a declared quantity hangs from when the fixture cares only
#: that the quantity IS declared (#326). Distinct from `DECLARED` above so that
#: declaring a quantity never quietly makes a supplier's own cost admissible —
#: two fixtures asking for different things must not collide on one key.
MEASURES = "measured.call"


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


def declares_a_quantity(tenant, measurement_key, *, key=MEASURES):
    """The declaration a rate must name before it may price that quantity (#326).

    **THE COMMONEST REASON A TEST NEEDS IT is that it predates the reference.**
    Writing a Cost Rate against no declaration at all was how every rate fixture
    in this repository did it, and a rate now names the declared record rather
    than a spelling of it — so a fixture that wants a rate wants a declaration
    behind it first.

    It answers the declaration ALREADY carrying the name where one exists,
    which is what `quantities.declaration_named` does and what the route does:
    a fixture that declared the quantity itself, under its own Event Type,
    must not end up with a rate pointing at a second declaration this helper
    invented beside it. `get_or_create` on the pair would not be enough —
    locality means the same name under another Event Type is a different
    record, and creating one is exactly the divergence the unique constraint
    over the reference would then stop refusing.

    The costing method is the CALCULATED one on purpose. `declares_a_caller_
    supplied_cost` above is what a test asks for when it wants a supplier's own
    figure admitted; declaring a quantity says nothing about where its cost
    comes from, and a helper that quietly said both would make every rate
    fixture in the tree a `reported` one.
    """
    declaration = declaration_named(tenant=tenant,
                                    measurement_key=measurement_key)
    if declaration is not None:
        return declaration
    event_type, _ = EventType.objects.get_or_create(
        tenant=tenant, key=key,
        defaults={"costing_method": COSTING_METHOD_CALCULATED})
    return Measurement.objects.create(
        event_type=event_type, code=measurement_key, unit=UNIT_TOKEN,
        source_kind=SOURCE_KIND_CALLER_SUPPLIED)
