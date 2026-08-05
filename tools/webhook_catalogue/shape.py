"""ADR-0006 §5's shape, stated against the vocabulary registry.

> A webhook event is named for the state entered.
>
>     <domain owner>.<past-tense state transition>
>
>     resource lifecycle transition → the resource owns the namespace
>     control's own state change    → the declared control family owns the namespace
>
> Cause and mechanism belong in structured payload fields, never in the event
> name.

**The oracle is `domain-vocabulary/`, and the rules decompose it.** The registry
declares the complete end-state catalogue (#202); this gate takes it apart into
the two halves ADR-0006 §5 names and checks a live event name against each. That
distinction is the whole design, and it is what keeps this gate from being G2
under another number:

- G2 asks *is this exact name in the set?* — a membership question, over every
  surface, and it is what #207 installs once the console and SDK constants exist.
- G8 asks *is this name the right SHAPE?* — so a name the registry has never
  seen can still be judged. `wallet.suspended` is not a declared event and this
  gate passes it, because `wallet` is a domain owner and `suspended` is a state
  UBB names elsewhere. `billing.balance_low` is refused even though its
  transition is impeccable, because `billing` is a product.

**What this gate does not prove, said plainly.** Three things, and none of them
is an oversight — each is the price of being a shape rule rather than a
membership one.

1. **Tense.** ADR-0006 §5 spells the second token as *past tense*, and no oracle
   in this repository settles whether a word is a past-tense form. What the gate
   proves is that the token is one the registry declares as a state entered — so
   the tense judgement happens once, in review, when a name is declared, and is
   mechanically enforced from then on. ADR-0008 §1's line between machine-proved
   and human-judged, and ADR-0008 §9's sentence applies without softening:
   consistency with a declaration is not proof the declaration was right.
2. **The two halves are checked independently**, so their cross-product passes.
   `wallet.api_key_created` has a declared owner and a declared transition and
   this gate admits it, though no such event exists and the pairing is
   meaningless. Refusing it would need a per-owner state model that no oracle
   holds; what closes it is the membership check, which is G2's whole statement
   and which #207 installs over every surface at once.
3. **That an event SHOULD exist.** A catalogue missing an event entirely is
   nothing this rule can see. That belongs to the slice that lands the state.

The honest summary is that G8 refuses names of the wrong shape and G2 refuses
names that are not in the set; neither alone is the whole of ADR-0006 §5, and
this file is the first half.

A literal past-tense rule was tried and rejected rather than skipped. Requiring
the transition's final word to end in `-ed` condemns nine of the thirty-seven
names the registry declares as the agreed end state — `wallet.balance_low`,
`credit_grant.expiring`, `referral.payout_due`, `customer.unprofitable`,
`provider.cost_spike` and four more. A rule that refuses a quarter of the answer
it is checking against is the wrong rule, not a strict one.
"""

import re
from dataclasses import dataclass

from . import errors as E
from .errors import CatalogueError, listed

#: The concepts the rules below are stated in terms of. Named as a constant
#: because a missing one is reported by name rather than raising a KeyError from
#: a dict lookup somewhere further in.
REQUIRED_CONCEPTS = ("webhook_event_type", "task_status", "control_family",
                     "tenant_product")

#: The one non-terminal Task state, from `task_status`'s own summary: *"`active`
#: is the only non-terminal one."* Named here because the registry states it in
#: prose rather than as data — and checked below, so a vocabulary change that
#: retired the word would fail loudly instead of silently promoting it to a
#: terminal state this gate would then accept in an event name.
NON_TERMINAL_TASK_STATUS = "active"

#: The surface whose declared consumer path IS the live catalogue.
BACKEND = "backend"


@dataclass(frozen=True)
class Vocabulary:
    """The registry, reduced to what ADR-0006 §5's two halves are stated over."""
    #: Where the live catalogue lives, from the registry's own declaration.
    catalogue_path: str
    #: The registry file `webhook_event_type` is declared in, so a fault found
    #: in the END STATE names the file to open. Carried here rather than looked
    #: up through the registry at the point of use: this type exists so that
    #: nothing downstream has to reach back past it.
    declared_in: str
    #: `<owner>.<transition>` — the registry's own pattern for these names.
    name_pattern: str
    #: Every namespace the end-state catalogue uses: resources and control
    #: families, and nothing else.
    owners: frozenset
    #: Every transition token it uses — the states UBB has agreed it names.
    transitions: frozenset
    declared_events: frozenset
    retired_events: frozenset
    #: The Task states a `task.*` or `subtask.*` event may name.
    task_statuses: frozenset
    terminal_task_statuses: frozenset
    #: Retired spend-control family spellings — a namespace naming one is a
    #: mechanism, which ADR-0006 §5 puts in `control_family`, not in the name.
    retired_families: frozenset
    #: The tenant's products. A product is the commonest wrong namespace in the
    #: catalogue today — `billing` owns the wallet's levels, the grant's
    #: lifecycle and the customer's suspension across eight events — and naming
    #: it as such turns a generic refusal into one that says what went wrong.
    products: frozenset


def load_vocabulary(registry):
    """Reduce a compiled registry to a :class:`Vocabulary`.

    Returns ``(vocabulary, errors)``. ``vocabulary`` is None when the registry
    cannot answer the questions this gate asks — which is an error about the
    oracle, never a quietly empty rule set that every name then satisfies.
    """
    errors = []
    missing = [name for name in REQUIRED_CONCEPTS if name not in registry.concepts]
    for name in missing:
        errors.append(CatalogueError(
            E.CONCEPT_MISSING, "domain-vocabulary",
            f"`{name}` is not in the registry, and ADR-0006 §5's shape is "
            f"stated in terms of it"))
    if missing:
        return None, errors

    events = registry.concepts["webhook_event_type"]
    statuses = registry.concepts["task_status"]
    families = registry.concepts["control_family"]

    backend = [consumer.path for consumer in events.consumers
               if consumer.surface == BACKEND]
    if not backend:
        errors.append(CatalogueError(
            E.CATALOGUE_UNDECLARED, "domain-vocabulary",
            f"`webhook_event_type` declares no `{BACKEND}` consumer, so this "
            f"gate has no live catalogue to read"))
        return None, errors

    declared = frozenset(statuses.values)
    if NON_TERMINAL_TASK_STATUS not in declared:
        errors.append(CatalogueError(
            E.NON_TERMINAL_STATUS_UNKNOWN, "domain-vocabulary",
            f"`task_status` no longer declares `{NON_TERMINAL_TASK_STATUS}`, "
            f"which this gate treats as the one non-terminal state. Until that "
            f"is settled it would treat a renamed initial state as terminal and "
            f"accept it in an event name"))
        return None, errors

    owners, transitions = set(), set()
    for value in events.values:
        split = value.split(".")
        if len(split) == 2:
            owners.add(split[0])
            transitions.add(split[1])

    return Vocabulary(
        catalogue_path=backend[0],
        declared_in=events.source,
        name_pattern=events.token_pattern,
        owners=frozenset(owners),
        transitions=frozenset(transitions),
        declared_events=frozenset(events.values),
        retired_events=frozenset(events.retired_aliases),
        task_statuses=declared,
        terminal_task_statuses=declared - {NON_TERMINAL_TASK_STATUS},
        retired_families=frozenset(families.retired_aliases),
        products=frozenset(registry.concepts["tenant_product"].values),
    ), errors


#: The namespaces a Task or Subtask lifecycle event may use. Both, because a
#: Subtask is the same record with a parent and shares the one status set
#: (ADR-0006's vocabulary table, #154 §3.1).
TASK_OWNERS = frozenset({"task", "subtask"})


def faults(name, location, vocabulary):
    """Every way ``name`` disagrees with ADR-0006 §5. Empty means it complies.

    All of them, not the first: an event whose namespace is a product AND whose
    transition carries a cause has two separate things wrong with it, and a
    reader fixing one at a time would need two runs to learn that.
    """
    found = []
    if not re.fullmatch(vocabulary.name_pattern, name):
        return [CatalogueError(
            E.NAME_MALFORMED, location,
            f"`{name}` is not `<owner>.<state entered>` — ADR-0006 §5 names one "
            f"domain owner and one transition, joined by a single dot, both "
            f"lower snake_case (`{vocabulary.name_pattern}`)")]

    owner, transition = name.split(".")
    retired = " The registry retires this name outright." if (
        name in vocabulary.retired_events) else ""

    if owner not in vocabulary.owners:
        if owner in vocabulary.products:
            why = (f"`{owner}` is one of the tenant's PRODUCTS, not a domain "
                   f"owner. A product is a bundle UBB sells; the namespace "
                   f"belongs to the thing whose state changed")
        elif owner in vocabulary.retired_families:
            why = (f"`{owner}` is a retired spend-control spelling. A control "
                   f"event belongs to the family that fired it, and the "
                   f"mechanism travels in the `control_family` payload field")
        else:
            why = (f"`{owner}` is not a domain owner. ADR-0006 §5 gives the "
                   f"namespace to the resource whose lifecycle moved, or to the "
                   f"declared control family whose own state changed — never to "
                   f"a product and never to the mechanism that fired")
        found.append(CatalogueError(
            E.OWNER_NOT_A_DOMAIN_OWNER, location,
            f"`{name}`: {why}. The owners this catalogue declares are "
            f"{listed(sorted(vocabulary.owners))}.{retired}"))

    if transition not in vocabulary.transitions:
        found.append(CatalogueError(
            E.TRANSITION_NOT_A_DECLARED_STATE, location,
            f"`{name}`: `{transition}` is not a state this catalogue enters. "
            f"An event is named for the state entered; the specific business "
            f"cause travels as `reason_code` and the mechanism that applied it "
            f"as `trigger_source`, so a subscriber classifies by subscribing "
            f"rather than by parsing.{retired}"))

    if owner in TASK_OWNERS and transition not in vocabulary.task_statuses:
        found.append(CatalogueError(
            E.TASK_EVENT_WITHOUT_A_STATUS, location,
            f"`{name}`: `{transition}` is not a `task_status` value, so this "
            f"event announces a Task state that a Task cannot be in. The "
            f"terminal ones are "
            f"{listed(sorted(vocabulary.terminal_task_statuses))}."))

    return found
