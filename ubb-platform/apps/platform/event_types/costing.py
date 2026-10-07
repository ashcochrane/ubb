"""What an Event Type's last publication declares about cost, for the paths
that act on it (#320, #605).

``Measurement``'s own docstring has said *"nothing rates against these ... slice
3 wires it"* since the table was created. This is that wire, and it is
deliberately one function returning plain data rather than an ORM row handed
across: its callers need four facts about a declaration and have no business
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

**Draft changes do not affect production recording (#605).** Production uses
the Event Type's last published declaration; changes take effect when they are
published. Every fact below is read off the copy ``publish`` keeps on the
Event Type's row (#573), through ``publication.last_published_declaration``,
and none of them off the draft — the four are one unit, and a read that took
one from each would let an unpublished edit change half of what production
does.

**One query, and it stays one.** The recording path is the hottest write in the
system, and the published copy is one column on one row, read on the
``uq_event_type_key`` unique index with no join: the quantities and the mapping
beneath the Event Type are not consulted, because they are the draft. Nothing
is cached: a publication must take effect on the next call, and the rate-card
cache next door exists because rates are read once per *quantity* per event,
which this is not.
"""
from typing import NamedTuple

from core.vocabulary import COSTING_METHOD_REPORTED, SOURCE_KIND_CALLER_SUPPLIED

from .publication import last_published_declaration


class CostDeclaration(NamedTuple):
    """The four facts about a published declaration that a cost decision
    turns on."""

    #: How this Event Type's supplier cost is arrived at — held by reference
    #: from `core.vocabulary`, never re-spelled here.
    costing_method: str
    #: Whether this Event Type carries no cost at all — a design decision the
    #: tenant made, and the one thing that makes a posting `not_applicable`
    #: rather than merely uncosted.
    declares_no_cost: bool
    #: WHERE the supplier's reported figure comes from, or `None` where the
    #: publication declares no mapping at all. The rating path reads only the
    #: PRESENCE of a mapping (#320); this is the one question that needs the
    #: kind itself, and it is answered off the same publication rather than by
    #: a second query.
    reported_cost_source_kind: str | None
    #: WHICH quantity codes this Event Type declares (#428) — the set a name on
    #: a report is measured against, so the compute spine can tell a quantity
    #: nobody declared from one nobody wrote a rate for. Declarations are
    #: Event-Type-local (#193 §C2), so this is THIS declaration's set and never
    #: the tenant's catalogue: a name declared beneath another Event Type is
    #: not declared here. Empty for a publication carrying no quantity, which
    #: is a different answer from the `None` the whole record is for an Event
    #: Type with no publication — the first is a tenant's statement, the second
    #: is the registry's opt-in.
    declared_quantity_codes: frozenset[str]


def cost_declaration(*, tenant, key):
    """What `key`'s last publication declares about cost for `tenant`, or
    `None` if nothing is published.

    `None` is not "no cost" — it is *no production declaration*, which is a
    different answer and the commoner one. The Event Type registry is opt-in,
    and reading absence as `not_applicable` would report a design decision
    nobody made.

    **THE LAST PUBLICATION GOVERNS, AND THE DRAFT NEVER DOES (#605).** Until
    #605 this read joined the live rows, and its docstring said *"a draft
    declaration counts, and that is a choice"*: slice 3's #320 made it so a
    tenant who corrected a declaration would see the correction on the next
    call. The owner and consultant ruled the other way (comment `6041500996`
    on #605). A deployed integration was generated against the publication,
    and a read of the draft let an unpublished edit to the mapping switch which
    figure production admits — refusing every call that integration makes,
    with nobody having published anything. Draft changes do not affect
    production recording. Production uses the Event Type's last published
    declaration; changes take effect when they are published.

    **NEVER PUBLISHED IS UNDECLARED, BY DELEGATION.** An Event Type declared
    and never published has no production declaration, so this answers the
    same `None` a key nobody declared does — and so does one published before
    copies were kept and revised since (#573), whose content is gone until it
    is published again. One answer, so a recording against any of them takes
    the one path an undeclared key takes, with no refusal and no path of its
    own. What that path does is not this read's to say (#568 owns it).

    **A `reported` declaration always carries a cost, mapping or no mapping.**
    The method itself is the statement that a supplier reports a figure; a
    missing mapping means the figure has nowhere to come *from*, which is
    `reported_cost_missing` — an outstanding task — and not "this call is free".
    So `declares_no_cost` asks the spec's *"no rate axis and no cost mapping"*
    question only of the declarations where both halves can honestly be absent:
    a costing method other than `reported`, no published quantity and no
    published mapping.
    """
    published = last_published_declaration(tenant=tenant, key=key)
    if published is None:
        return None
    mapping = published.reported_cost_mapping
    declared_codes = frozenset(quantity.code
                               for quantity in published.measurements)
    return CostDeclaration(
        costing_method=published.costing_method,
        declares_no_cost=(
            published.costing_method != COSTING_METHOD_REPORTED
            and not declared_codes
            and mapping is None),
        reported_cost_source_kind=(None if mapping is None
                                   else mapping.source_kind),
        declared_quantity_codes=declared_codes,
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

    `None` — no published declaration — is a **no**. The Event Type registry is
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
