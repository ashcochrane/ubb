"""Which analytical heading each of a tenant's own identities sits under (#498).

A **declared semantic rollup** is the second of slice 7 §6's two grouping kinds:
a controlled mapping from an identity the tenant already declared to a broader
heading they also declared. `costing.py` and `quantities.py` beside this answer
what a declaration says about cost and which record a name is the name of; this
answers the one remaining question a reporting surface asks of the catalogue —
what does this roll up to — and it answers it in **plain data**, as they do.

**Why it lives beside the declaration rather than in the reporting module, and
why that is a rule rather than a preference here.** *"Which heading has this
tenant filed this Event Type under"* is a statement about the tenant's own
catalogue, so a copy of the query in metering would be a second definition of a
kernel fact (ADR-0006 §4). And `apps/platform/tests/test_event_type_satellite
_invariants.py` makes it structural: a module where a cost, a price or a spend
ceiling is decided **may not name a catalogue class at all**, because money code
does not hold catalogue rows. `apps/metering/queries.py` is exactly such a
module — it is metering's read contract — so the grouping contract reaches these
records through this function or not at all. The reporter asks; this answers.

⚠ **AND THE FENCE IS SHARPEST FOR THE MEASUREMENT HEADING.** That one is on the
invariant's list precisely because *"the grouping is analytics-only and a rating
path that can see it has made an analytics heading into a costing input"*. This
module is not a rating path and never becomes one: it returns strings keyed by
strings, holds no amount, and nothing it answers can reach a rate.

**Read live, and that is the whole behaviour.** Nothing here is cached and
nothing is stored: a rollup is resolved when it is read, which is what makes
moving an identity to another heading **reclassify history**. That is safe
precisely because a rollup touches no money — it alters no original event, no
cost, no Charge, no receipt and no historical monetary amount — and it is the
property the reporting surface states at the point of change.

**An identity with no heading is ABSENT rather than present under a sentinel.**
Both sides of each mapping are opt-in — an Event Type with no category is a
normal Event Type, and a declaration with no concept is a normal declaration —
so *"nobody has filed this"* and *"this is filed under nothing"* are the same
fact, and a sentinel key would be the unattributed bucket slice 7 §5 forbids,
one layer down.

Keyed by the tenant's own spelling on BOTH sides, because those are the words
the tenant reads on the surfaces that carry the answer: an Event Type's key and
a declared quantity's code on one side, their heading's key on the other.
"""
from .models import EventType, Measurement


def event_types_by_category(tenant_id) -> dict:
    """``{Event Type key: category key}`` for one tenant.

    One level, current, and never effective-dated — `EventCategory`'s own
    docstring rules that out, because dating a value that reaches no money
    reproduces nothing.
    """
    return dict(EventType.objects
                .filter(tenant_id=tenant_id, category__isnull=False)
                .values_list("key", "category__key"))


def measurements_by_concept(tenant_id) -> dict:
    """``{(Event Type key, quantity code): concept key}`` for one tenant.

    ⚠ **KEYED BY THE PAIR AND NOT BY THE CODE, BECAUSE A DECLARATION IS
    EVENT-TYPE-LOCAL.** That locality is the correctness boundary `Measurement`'s
    own docstring draws: two Event Types may each declare `prompt_tokens`, they
    are independent records that happen to share a spelling, and **a tenant may
    file them under different headings** — which is the whole point of an opt-in
    grouping, since a matching name never proves equivalence.

    A map keyed by the code alone would therefore have to drop one of the two,
    and whichever it dropped would be a plausible wrong answer: a chart would
    quietly file one Event Type's quantity under the other's heading. The pair
    is the identity the tenant actually declared, so nothing is lost and nothing
    has to be picked.
    """
    return {(event_type, code): concept
            for event_type, code, concept
            in Measurement.objects
            .filter(event_type__tenant_id=tenant_id, concept__isnull=False)
            .values_list("event_type__key", "code", "concept__key")}
