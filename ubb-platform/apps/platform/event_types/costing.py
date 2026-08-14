"""What an Event Type declares about cost, for the paths that act on it (#320).

``Measurement``'s own docstring has said *"nothing rates against these ... slice
3 wires it"* since the table was created. This is that wire, and it is
deliberately one function returning plain data rather than an ORM row handed
across: its callers need three facts about a declaration and have no business
holding a record they could accidentally save.

**Two callers, one query each, asking different questions of the same record.**
The compute spine asks what a posting's cost status should be. The recording
edge asks whether the caller may state the supplier's figure at all (#324) —
and only ever when one arrived, which is precisely the branch on which the
spine never looks the declaration up.

**Why this lives beside the declaration rather than in the pricer.** *"This
Event Type carries no cost at all"* is a statement about what the tenant
declared, not about how a cost is computed, and a copy of it in metering would
be a second definition of a kernel fact (ADR-0006 §4) — one that would go stale
the day a third way to declare a cost arrives. The pricer asks; this answers.

**One query, and it stays one.** The recording path is the hottest write in the
system, so the count of declared quantities is annotated and the reported-cost
mapping is joined rather than each being fetched on access — three round trips
collapsed into one, on the ``uq_event_type_key`` unique index. Nothing is
cached: a declaration a tenant edited must take effect on the next call, and the
rate-card cache next door exists because rates are read once per *quantity* per
event, which this is not.
"""
from typing import NamedTuple

from django.db.models import Count

from core.vocabulary import COSTING_METHOD_REPORTED, SOURCE_KIND_CALLER_SUPPLIED

from .models import REPORTED_COST_MAPPING, EventType


class CostDeclaration(NamedTuple):
    """The three facts about a declaration that a cost decision turns on."""

    #: How this Event Type's supplier cost is arrived at — held by reference
    #: from `core.vocabulary`, never re-spelled here.
    costing_method: str
    #: Whether this Event Type carries no cost at all — a design decision the
    #: tenant made, and the one thing that makes a posting `not_applicable`
    #: rather than merely uncosted.
    declares_no_cost: bool
    #: WHERE the supplier's reported figure comes from, or `None` where this
    #: Event Type declares no mapping at all. The rating path reads only the
    #: PRESENCE of a mapping (#320); this is the one question that needs the
    #: kind itself, and it is answered off the row already joined below rather
    #: than by a second query.
    reported_cost_source_kind: str | None


def cost_declaration(*, tenant, key):
    """What `key` declares about cost for `tenant`, or `None` if it declares nothing.

    `None` is not "no cost" — it is *no declaration*, which is a different
    answer and the commoner one. The Event Type registry is opt-in: a tenant may
    record against a key they never declared, and every such posting costs the
    way this repository has always costed, against Cost Rates. Reading absence
    as `not_applicable` would report a design decision nobody made.

    **A DRAFT DECLARATION COUNTS, AND THAT IS A CHOICE.** `declaration_status`
    is not filtered on here. Publication governs what a generated integration
    was built against — that is what `published_revision` counts — and it is not
    a claim about what the tenant means today. A tenant who corrects a
    declaration sees the correction on the next call rather than after a
    publish, and a draft `reported` declaration is answered `reported_cost_
    missing` rather than being costed against rate cards it has disowned, which
    is the truer of the two available answers.

    **A `reported` declaration always carries a cost, mapping or no mapping.**
    The method itself is the statement that a supplier reports a figure; a
    missing mapping means the figure has nowhere to come *from*, which is
    `reported_cost_missing` — an outstanding task — and not "this call is free".
    So `declares_no_cost` asks the spec's *"no rate axis and no cost mapping"*
    question only of the declarations where both halves can honestly be absent.
    """
    if not key:
        return None
    row = (EventType.objects
           .filter(tenant=tenant, key=key)
           .select_related(REPORTED_COST_MAPPING)
           .annotate(declared_quantities=Count("measurements"))
           .first())
    if row is None:
        return None
    # A missing reverse one-to-one answers None through getattr's default, the
    # same read `EventType.publication_blockers` makes.
    mapping = getattr(row, REPORTED_COST_MAPPING, None)
    return CostDeclaration(
        costing_method=row.costing_method,
        declares_no_cost=(
            row.costing_method != COSTING_METHOD_REPORTED
            and row.declared_quantities == 0
            and mapping is None),
        reported_cost_source_kind=(None if mapping is None
                                   else mapping.source_kind),
    )


def admits_a_caller_supplied_cost(declaration):
    """May a caller state the supplier's own cost on a call against this key?

    Exactly one declaration says yes: the **reported** costing method with a
    mapping whose source kind is the **caller-supplied** one. That pair is the
    tenant saying "the supplier reports this number and my own code passes it
    in", and it is the only shape under which UBB will read the figure as COGS.

    **BOTH HALVES, AND THE SECOND IS THE ONE THAT BITES.** `reported` alone
    says a supplier reports a figure, not that it arrives on the call — a
    mapping declaring `provider_response` says the generated integration reads
    it out of the supplier's own response, and a check that stopped at the
    method would admit a number that came from somewhere the tenant never
    declared.

    `None` — no declaration at all — is a **no**. The Event Type registry is
    opt-in and most postings still have no declaration, so this is the commonest
    answer rather than an error case; what a tenant may not do is assert the
    supplier's own number against nothing. The refusal itself is the caller's
    edge to render (`api/v1/metering_endpoints.py`), which is where a 422 and
    its wording belong; this answers only what the declaration permits.
    """
    return (declaration is not None
            and declaration.costing_method == COSTING_METHOD_REPORTED
            and declaration.reported_cost_source_kind
            == SOURCE_KIND_CALLER_SUPPLIED)
