"""Which declared quantity a name is the name of (#326).

`costing.py` beside this answers what an Event Type declares about COST. This
answers the question one layer earlier and for a different caller: a tenant has
written a name on a Cost Rate, and before that rate may exist UBB has to find
the record the name is a name *of*. Until slice 3 there was nothing to find —
the rate held the name as free text and a typo sat there costing nothing and
looking configured.

**Why this lives beside the declaration rather than in the pricer.** *"Has this
tenant declared a quantity called X"* is a statement about the tenant's own
catalogue, not about how a rate is resolved, and a copy of the query in metering
would be a second definition of a kernel fact (ADR-0006 §4). `Measurement`'s own
docstring has said since the table was created that a rate would hold this by
reference in its own slice. The pricer asks; this answers.

**IT ANSWERS `None` RATHER THAN REFUSING, and that is the same division of
labour `admits_a_caller_supplied_cost` draws.** A refusal has a wording, a
status code and an audience; those belong to the edge the caller is standing at
— `api/v1/metering_endpoints.py` for a rate written over HTTP — and the
database's own check is what holds the line for every other door. This says only
what the catalogue contains.

**DECLARATIONS ARE EVENT-TYPE-LOCAL AND A RATE IS NOT, which is the one thing
about this lookup that is not obvious.** Two Event Types may each declare
`prompt_tokens`; a Cost Rate that leaves `event_type` unpinned prices the
quantity under both, and has done since selectors were introduced. So the name
can match more than one declaration, and the reference names one of them.

That is a claim about the CATALOGUE — the tenant declared this name — and never
a claim about which Event Type's copy a rate meant, because resolution has never
asked: it matches on the name, and it still does (`PricingService.
_resolve_rate_within`). Picking is therefore invisible to what a rate prices,
and it is not invisible to the unique constraint over the reference, which is
why the pick below is DETERMINISTIC rather than arbitrary. Two rates written for
one name in one book resolve to the same declaration and the second is refused,
exactly as it was when both held the name as text. `apps/metering/pricing/tests/
test_a_rate_names_a_declared_quantity.py` drives that case with the name
declared twice.
"""
from .models import Measurement


def declaration_named(*, tenant, measurement_key):
    """The declared quantity `tenant` calls `measurement_key`, or `None`.

    `None` means no declaration of this tenant's carries that name, which is
    what makes a rate naming it unwritable. It is never "the quantity does not
    exist" — a tenant may meter a quantity they have never declared and every
    such posting costs the way this repository has always costed; what they may
    not do is write a priced rule against a name their own catalogue does not
    carry.

    **The earliest declaration wins where several carry the name.** Not the
    newest: a reference that moved every time a tenant declared the same
    spelling under one more Event Type would make the unique constraint over it
    stop refusing what it refuses today, and it would do so silently, one
    declaration at a time. `created_at` is tie-broken by `id` because nothing
    stops two rows sharing a stamp — `bulk_create` and a clock coarser than the
    gap between two inserts both produce it — and a pick that is only usually
    deterministic is not one.
    """
    if not measurement_key:
        return None
    return (Measurement.objects
            .filter(event_type__tenant=tenant, code=measurement_key)
            .order_by("created_at", "id")
            .first())
